from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt

from app.core.config import settings
from app.services.google_auth import GoogleProfile


class GoogleOAuthError(Exception):
    """Erro genérico do fluxo OAuth do Google."""


class GoogleOAuthConfigError(GoogleOAuthError):
    """Configuração do Google OAuth ausente ou inválida."""


class GoogleOAuthStateError(GoogleOAuthError):
    """State inválido, expirado ou adulterado."""


class GoogleOAuthExchangeError(GoogleOAuthError):
    """Falha na troca do code pelo perfil do Google."""


@dataclass(frozen=True)
class GoogleOAuthStartResult:
    authorization_url: str
    state: str


@dataclass(frozen=True)
class GoogleOAuthStateData:
    redirect_uri: str
    origin: str | None = None


class GoogleOAuthService:
    """
    Serviço responsável por:
    - gerar state assinado
    - montar a URL de autorização do Google
    - trocar code por access_token
    - buscar o profile do usuário no Google
    - transformar o retorno em GoogleProfile

    Não cria rota, não gera JWT da aplicação e não mexe no front.
    """

    def __init__(self) -> None:
        self.client_id = settings.google_client_id
        self.client_secret = settings.google_client_secret
        self.authorize_url = settings.google_authorize_url
        self.token_url = settings.google_token_url
        self.userinfo_url = settings.google_userinfo_url
        self.scopes = settings.google_scopes
        self.state_ttl_minutes = settings.google_oauth_state_ttl_minutes
        self.state_secret = settings.jwt_access_secret_key
        self.jwt_algorithm = settings.jwt_algorithm

    def ensure_configured(self) -> None:
        if not self.client_id or not self.client_secret:
            raise GoogleOAuthConfigError(
                "Google OAuth não configurado. Defina GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET."
            )

    def build_authorization_url(
        self,
        *,
        redirect_uri: str,
        origin: str | None = None,
    ) -> GoogleOAuthStartResult:
        self.ensure_configured()

        redirect_uri = (redirect_uri or "").strip()
        if not redirect_uri:
            raise GoogleOAuthConfigError("redirect_uri ausente para o Google OAuth.")

        state = self._encode_state(redirect_uri=redirect_uri, origin=origin)

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.scopes,
            "access_type": "online",
            "include_granted_scopes": "true",
            "prompt": "select_account",
            "state": state,
        }

        return GoogleOAuthStartResult(
            authorization_url=f"{self.authorize_url}?{urlencode(params)}",
            state=state,
        )

    def parse_state(self, state: str, *, redirect_uri: str) -> GoogleOAuthStateData:
        state = (state or "").strip()
        redirect_uri = (redirect_uri or "").strip()

        if not state:
            raise GoogleOAuthStateError("State ausente.")
        if not redirect_uri:
            raise GoogleOAuthStateError("redirect_uri ausente.")

        try:
            payload = jwt.decode(
                state,
                self.state_secret,
                algorithms=[self.jwt_algorithm],
            )
        except JWTError as exc:
            raise GoogleOAuthStateError("State inválido ou expirado.") from exc

        expected_redirect_uri = str(payload.get("redirect_uri") or "").strip()
        origin = payload.get("origin")

        if expected_redirect_uri != redirect_uri:
            raise GoogleOAuthStateError("State não corresponde ao redirect_uri informado.")

        return GoogleOAuthStateData(
            redirect_uri=expected_redirect_uri,
            origin=origin if isinstance(origin, str) and origin.strip() else None,
        )

    def exchange_code_for_profile(
        self,
        *,
        code: str,
        redirect_uri: str,
    ) -> GoogleProfile:
        self.ensure_configured()

        code = (code or "").strip()
        redirect_uri = (redirect_uri or "").strip()

        if not code:
            raise GoogleOAuthExchangeError("Code ausente.")
        if not redirect_uri:
            raise GoogleOAuthExchangeError("redirect_uri ausente.")

        token_payload = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        try:
            with httpx.Client(timeout=20.0) as client:
                token_response = client.post(
                    self.token_url,
                    data=token_payload,
                    headers={"Accept": "application/json"},
                )
                token_response.raise_for_status()
                token_data = token_response.json()

                access_token = token_data.get("access_token")
                if not access_token:
                    raise GoogleOAuthExchangeError("Google não retornou access_token.")

                userinfo_response = client.get(
                    self.userinfo_url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
                userinfo_response.raise_for_status()
                userinfo = userinfo_response.json()

        except httpx.HTTPError as exc:
            raise GoogleOAuthExchangeError("Falha ao comunicar com o Google OAuth.") from exc

        provider_sub = str(userinfo.get("sub") or "").strip()
        if not provider_sub:
            raise GoogleOAuthExchangeError("Google não retornou 'sub' do usuário.")

        email = self._normalize_email(userinfo.get("email"))
        email_verified = bool(userinfo.get("email_verified"))
        full_name = self._normalize_name(userinfo.get("name"))
        avatar_url = self._normalize_avatar(userinfo.get("picture"))

        return GoogleProfile(
            provider_sub=provider_sub,
            email=email,
            email_verified=email_verified,
            full_name=full_name,
            avatar_url=avatar_url,
        )

    def _encode_state(self, *, redirect_uri: str, origin: str | None = None) -> str:
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self.state_ttl_minutes)

        payload: dict[str, Any] = {
            "type": "google_oauth_state",
            "redirect_uri": redirect_uri,
            "origin": origin,
            "iat": now,
            "exp": expires_at,
        }
        return jwt.encode(
            payload,
            self.state_secret,
            algorithm=self.jwt_algorithm,
        )

    @staticmethod
    def _normalize_email(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        return normalized or None

    @staticmethod
    def _normalize_name(value: Any) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).strip().split())
        return normalized or None

    @staticmethod
    def _normalize_avatar(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

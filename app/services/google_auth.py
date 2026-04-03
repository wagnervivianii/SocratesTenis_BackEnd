from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_identity import UserIdentity

GoogleProvider = Literal["google"]


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalize_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().split())
    return normalized or None


@dataclass(frozen=True)
class GoogleProfile:
    provider_sub: str
    email: str | None
    email_verified: bool
    full_name: str | None
    avatar_url: str | None = None


@dataclass(frozen=True)
class GoogleAuthResult:
    user: User
    identity: UserIdentity
    created_user: bool
    linked_existing_user: bool
    created_identity: bool
    auth_provider: str = "google"
    avatar_url: str | None = None


class GoogleAuthError(Exception):
    """Erro genérico no vínculo/autenticação Google."""


class GoogleAuthInvalidProfile(GoogleAuthError):
    """Perfil do Google inválido ou incompleto."""


class GoogleAuthService:
    """
    Serviço responsável por:
    - localizar identidade Google existente por provider_sub
    - localizar usuário por e-mail
    - vincular conta Google a usuário já existente
    - criar usuário + identidade quando necessário

    Não cria rota, não gera token JWT e não mexe no front.
    """

    provider: GoogleProvider = "google"

    def resolve_or_create_user(
        self,
        db: Session,
        profile: GoogleProfile,
        *,
        default_role: str = "staff",
    ) -> GoogleAuthResult:
        provider_sub = (profile.provider_sub or "").strip()
        if not provider_sub:
            raise GoogleAuthInvalidProfile("Google provider_sub ausente.")

        normalized_email = _normalize_email(profile.email)
        normalized_name = _normalize_name(profile.full_name)
        now = _now_utc()

        identity = db.execute(
            select(UserIdentity).where(
                UserIdentity.provider == self.provider,
                UserIdentity.provider_sub == provider_sub,
            )
        ).scalar_one_or_none()

        if identity is not None:
            user = db.execute(select(User).where(User.id == identity.user_id)).scalar_one()

            changed = False

            if normalized_email and identity.provider_email != normalized_email:
                identity.provider_email = normalized_email
                changed = True

            if identity.email_verified is not profile.email_verified:
                identity.email_verified = profile.email_verified
                changed = True

            if normalized_name and not getattr(user, "full_name", None):
                user.full_name = normalized_name
                changed = True

            if profile.email_verified and getattr(user, "email_verified_at", None) is None:
                user.email_verified_at = now
                changed = True

            if changed:
                db.commit()
                db.refresh(user)
                db.refresh(identity)

            return GoogleAuthResult(
                user=user,
                identity=identity,
                created_user=False,
                linked_existing_user=False,
                created_identity=False,
                avatar_url=profile.avatar_url,
            )

        user = None
        linked_existing_user = False

        if normalized_email:
            user = db.execute(
                select(User).where(User.email == normalized_email)
            ).scalar_one_or_none()

        created_user = False
        if user is None:
            if not normalized_email:
                raise GoogleAuthInvalidProfile(
                    "Perfil Google sem e-mail; não é possível criar usuário local."
                )

            user = User(
                email=normalized_email,
                full_name=normalized_name or normalized_email.split("@", 1)[0],
                password_hash=None,
                role=default_role,
                is_active=True,
                email_verified_at=now if profile.email_verified else None,
            )
            db.add(user)
            db.flush()
            created_user = True
        else:
            linked_existing_user = True

            changed = False
            if normalized_name and not getattr(user, "full_name", None):
                user.full_name = normalized_name
                changed = True

            if profile.email_verified and getattr(user, "email_verified_at", None) is None:
                user.email_verified_at = now
                changed = True

            if changed:
                db.flush()

        identity = UserIdentity(
            user_id=user.id,
            provider=self.provider,
            provider_sub=provider_sub,
            provider_email=normalized_email,
            email_verified=profile.email_verified,
        )
        db.add(identity)
        db.commit()
        db.refresh(user)
        db.refresh(identity)

        return GoogleAuthResult(
            user=user,
            identity=identity,
            created_user=created_user,
            linked_existing_user=linked_existing_user,
            created_identity=True,
            avatar_url=profile.avatar_url,
        )

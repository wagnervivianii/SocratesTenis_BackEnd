from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EmailVerificationIssueResult:
    token: str
    token_hash: str
    expires_at: datetime


class EmailVerificationError(Exception):
    """Erro genérico de validação de e-mail."""


class EmailVerificationExpired(EmailVerificationError):
    """Token expirado."""


class EmailVerificationInvalid(EmailVerificationError):
    """Token inválido ou já utilizado."""


class EmailVerificationService:
    """
    Serviço reutilizável:
    - emite token (salva apenas hash no banco)
    - invalida tokens antigos pendentes do mesmo usuário
    - verifica token (marca email_verified_at e is_active)

    Não envia e-mail (isso fica no próximo bloco).
    """

    def __init__(self, ttl_minutes: int = 30) -> None:
        self.ttl_minutes = ttl_minutes

    def issue_for_user(
        self,
        db: Session,
        user_id: UUID,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> EmailVerificationIssueResult:
        """
        Gera token e salva no banco. Retorna token puro (para montar link).
        """
        token = secrets.token_urlsafe(32)  # alto entropy
        token_hash = _sha256_hex(token)
        now = _now_utc()
        expires_at = now + timedelta(minutes=self.ttl_minutes)

        # Invalida tokens antigos pendentes do mesmo usuário (opcional, mas recomendado)
        db.execute(
            text(
                """
                UPDATE public.email_verifications
                   SET expires_at = :now,
                       updated_at = :now
                 WHERE user_id = :user_id
                   AND verified_at IS NULL
                   AND expires_at > :now
                """
            ),
            {"now": now, "user_id": str(user_id)},
        )

        # Insere novo token
        db.execute(
            text(
                """
                INSERT INTO public.email_verifications (
                    user_id, token_hash, expires_at,
                    attempts, last_sent_at, ip, user_agent,
                    created_at, updated_at
                )
                VALUES (
                    :user_id, :token_hash, :expires_at,
                    0, :now, :ip, :user_agent,
                    :now, :now
                )
                """
            ),
            {
                "user_id": str(user_id),
                "token_hash": token_hash,
                "expires_at": expires_at,
                "now": now,
                "ip": ip,
                "user_agent": user_agent,
            },
        )

        db.commit()

        return EmailVerificationIssueResult(
            token=token,
            token_hash=token_hash,
            expires_at=expires_at,
        )

    def verify_token(self, db: Session, token: str) -> UUID:
        """
        Valida token:
        - existe e não foi usado
        - não expirou
        - marca verified_at
        - marca users.email_verified_at e is_active=true

        Retorna user_id se OK.
        """
        token = (token or "").strip()
        if not token:
            raise EmailVerificationInvalid("Token ausente.")

        token_hash = _sha256_hex(token)
        now = _now_utc()

        row = (
            db.execute(
                text(
                    """
                SELECT id, user_id, expires_at, verified_at, attempts
                  FROM public.email_verifications
                 WHERE token_hash = :token_hash
                 LIMIT 1
                """
                ),
                {"token_hash": token_hash},
            )
            .mappings()
            .first()
        )

        if not row:
            raise EmailVerificationInvalid("Token inválido.")

        if row["verified_at"] is not None:
            raise EmailVerificationInvalid("Token já utilizado.")

        if row["expires_at"] < now:
            raise EmailVerificationExpired("Token expirado.")

        # incrementa attempts (telemetria/anti-abuso)
        db.execute(
            text(
                """
                UPDATE public.email_verifications
                   SET attempts = attempts + 1,
                       updated_at = :now
                 WHERE id = :id
                """
            ),
            {"id": str(row["id"]), "now": now},
        )

        # marca verificação como concluída
        db.execute(
            text(
                """
                UPDATE public.email_verifications
                   SET verified_at = :now,
                       updated_at = :now
                 WHERE id = :id
                """
            ),
            {"id": str(row["id"]), "now": now},
        )

        user_id = UUID(str(row["user_id"]))

        # ativa usuário + marca verificação
        db.execute(
            text(
                """
                UPDATE public.users
                   SET email_verified_at = :now,
                       is_active = TRUE,
                       updated_at = :now
                 WHERE id = :user_id
                """
            ),
            {"user_id": str(user_id), "now": now},
        )

        db.commit()
        return user_id

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
class PasswordResetIssueResult:
    token: str
    token_hash: str
    expires_at: datetime


class PasswordResetError(Exception):
    """Erro genérico do fluxo de redefinição de senha."""


class PasswordResetExpired(PasswordResetError):
    """Token expirado."""


class PasswordResetInvalid(PasswordResetError):
    """Token inválido, já utilizado, invalidado ou ausente."""


class PasswordResetService:
    """
    Serviço reutilizável de recovery de senha:
    - emite token (salva apenas hash no banco)
    - invalida tokens antigos pendentes do mesmo usuário
    - valida token sem consumi-lo
    - consome token e atualiza a senha do usuário

    O envio de e-mail e os endpoints ficam fora deste serviço.
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
    ) -> PasswordResetIssueResult:
        token = secrets.token_urlsafe(32)
        token_hash = _sha256_hex(token)
        now = _now_utc()
        expires_at = now + timedelta(minutes=self.ttl_minutes)

        db.execute(
            text(
                """
                UPDATE public.password_reset_tokens
                   SET used_at = :now,
                       expires_at = :now,
                       updated_at = :now
                 WHERE user_id = :user_id
                   AND used_at IS NULL
                   AND expires_at > :now
                """
            ),
            {"now": now, "user_id": str(user_id)},
        )

        db.execute(
            text(
                """
                INSERT INTO public.password_reset_tokens (
                    user_id,
                    token_hash,
                    expires_at,
                    attempts,
                    last_sent_at,
                    ip,
                    user_agent,
                    created_at,
                    updated_at
                )
                VALUES (
                    :user_id,
                    :token_hash,
                    :expires_at,
                    0,
                    :now,
                    :ip,
                    :user_agent,
                    :now,
                    :now
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

        return PasswordResetIssueResult(
            token=token,
            token_hash=token_hash,
            expires_at=expires_at,
        )

    def validate_token(self, db: Session, token: str) -> UUID:
        row = self._get_pending_row(db, token)
        return UUID(str(row["user_id"]))

    def consume_token(self, db: Session, token: str, *, password_hash: str) -> UUID:
        if not password_hash:
            raise PasswordResetInvalid("Hash de senha ausente.")

        row = self._get_pending_row(db, token)
        now = _now_utc()
        row_id = str(row["id"])
        user_id = UUID(str(row["user_id"]))

        db.execute(
            text(
                """
                UPDATE public.password_reset_tokens
                   SET attempts = attempts + 1,
                       used_at = :now,
                       updated_at = :now
                 WHERE id = :id
                """
            ),
            {"id": row_id, "now": now},
        )

        db.execute(
            text(
                """
                UPDATE public.users
                   SET password_hash = :password_hash,
                       updated_at = :now
                 WHERE id = :user_id
                """
            ),
            {
                "password_hash": password_hash,
                "now": now,
                "user_id": str(user_id),
            },
        )

        db.execute(
            text(
                """
                UPDATE public.password_reset_tokens
                   SET used_at = :now,
                       expires_at = :now,
                       updated_at = :now
                 WHERE user_id = :user_id
                   AND id <> :id
                   AND used_at IS NULL
                   AND expires_at > :now
                """
            ),
            {"now": now, "user_id": str(user_id), "id": row_id},
        )

        db.commit()
        return user_id

    def _get_pending_row(self, db: Session, token: str):
        token = (token or "").strip()
        if not token:
            raise PasswordResetInvalid("Token ausente.")

        token_hash = _sha256_hex(token)
        now = _now_utc()

        row = (
            db.execute(
                text(
                    """
                    SELECT id, user_id, expires_at, used_at, attempts
                      FROM public.password_reset_tokens
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
            raise PasswordResetInvalid("Token inválido.")

        if row["used_at"] is not None:
            raise PasswordResetInvalid("Token já utilizado ou invalidado.")

        if row["expires_at"] < now:
            raise PasswordResetExpired("Token expirado.")

        return row

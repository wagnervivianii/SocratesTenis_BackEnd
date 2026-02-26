from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Hash de senha (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _encode_token(
    payload: dict[str, Any],
    secret_key: str,
    expires_delta: timedelta,
) -> str:
    to_encode = payload.copy()
    expire = _now_utc() + expires_delta

    # Claims padrão úteis
    to_encode.update(
        {
            "exp": expire,
            "iat": _now_utc(),
        }
    )

    return jwt.encode(to_encode, secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> str:
    """
    Access token: curto, usado no header Authorization: Bearer <token>
    """
    minutes = expires_minutes or settings.access_token_expire_minutes
    claims: dict[str, Any] = {"sub": subject, "type": "access"}
    if extra_claims:
        claims.update(extra_claims)

    return _encode_token(
        payload=claims,
        secret_key=settings.jwt_access_secret_key,
        expires_delta=timedelta(minutes=minutes),
    )


def create_refresh_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
    expires_days: int | None = None,
) -> str:
    """
    Refresh token: longo, vai em cookie httpOnly.
    """
    days = expires_days or settings.refresh_token_expire_days
    claims: dict[str, Any] = {"sub": subject, "type": "refresh"}
    if extra_claims:
        claims.update(extra_claims)

    return _encode_token(
        payload=claims,
        secret_key=settings.jwt_refresh_secret_key,
        expires_delta=timedelta(days=days),
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decodifica e valida assinatura/expiração do ACCESS token.
    Retorna claims se ok; levanta JWTError se inválido/expirado.
    """
    return jwt.decode(
        token,
        settings.jwt_access_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require_sub": True},
    )


def decode_refresh_token(token: str) -> dict[str, Any]:
    """
    Decodifica e valida assinatura/expiração do REFRESH token.
    """
    return jwt.decode(
        token,
        settings.jwt_refresh_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require_sub": True},
    )


def safe_get_subject(claims: dict[str, Any]) -> str:
    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        raise JWTError("Token sem subject (sub) válido")
    return sub

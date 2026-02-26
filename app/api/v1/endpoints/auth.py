from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_password_hash,
    safe_get_subject,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginIn, MessageOut, TokenOut

router = APIRouter(prefix="/auth")

DBSession = Annotated[Session, Depends(get_db)]


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
    )


def _only_digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def _normalize_instagram(s: str | None) -> str | None:
    if not s:
        return None
    v = s.strip()
    if not v:
        return None
    while v.startswith("@"):
        v = v[1:]
    v = v.strip()
    return v or None


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    whatsapp: str = Field(min_length=10, max_length=20)
    instagram: str | None = Field(default=None, max_length=60)
    intent: str = Field(pattern="^(lesson|rental|student)$")


class RegisterOut(BaseModel):
    user_id: str
    created: bool
    intent_added: bool
    intent: str
    email: EmailStr


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, response: Response, db: DBSession):
    user = db.scalar(select(User).where(User.email == str(data.email)))

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas"
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuário inativo")

    access = create_access_token(subject=str(user.id))
    refresh = create_refresh_token(subject=str(user.id))

    _set_refresh_cookie(response, refresh)

    return TokenOut(
        access_token=access,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, db: DBSession):
    email = str(data.email).strip().lower()
    whatsapp_digits = _only_digits(data.whatsapp)

    if len(whatsapp_digits) not in (10, 11):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="WhatsApp inválido")

    instagram = _normalize_instagram(data.instagram)
    full_name = data.full_name.strip()

    user = db.scalar(select(User).where((User.email == email) | (User.whatsapp == whatsapp_digits)))

    created = False

    if not user:
        user = User(
            email=email,
            password_hash=get_password_hash(data.password),
            full_name=full_name,
            role="staff",
            is_active=True,
            whatsapp=whatsapp_digits,
            instagram=instagram,
        )
        db.add(user)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Usuário já cadastrado",
            ) from None
        db.refresh(user)
        created = True

    intent_added = False
    try:
        res = db.execute(
            text(
                """
                INSERT INTO user_intents (user_id, intent)
                VALUES (:user_id, :intent)
                ON CONFLICT (user_id, intent) DO NOTHING
                """
            ),
            {"user_id": str(user.id), "intent": data.intent},
        )
        db.commit()
        intent_added = bool(getattr(res, "rowcount", 0))
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao registrar intenção",
        ) from None

    return RegisterOut(
        user_id=str(user.id),
        created=created,
        intent_added=intent_added,
        intent=data.intent,
        email=email,
    )


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, db: DBSession):
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token ausente"
        )

    try:
        claims = decode_refresh_token(token)
        if claims.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

        user_id_str = safe_get_subject(claims)
        user_id = UUID(user_id_str)

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido",
        ) from None

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inválido")

    new_access = create_access_token(subject=str(user.id))
    new_refresh = create_refresh_token(subject=str(user.id))
    _set_refresh_cookie(response, new_refresh)

    return TokenOut(
        access_token=new_access,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout", response_model=MessageOut)
def logout(response: Response):
    _clear_refresh_cookie(response)
    return MessageOut(message="ok")


@router.get("/me")
def me(user_id: str = Depends(get_current_user_id)):
    return {"user_id": user_id}

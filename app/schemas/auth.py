from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MessageOut(BaseModel):
    message: str


class MeOut(BaseModel):
    user_id: str
    email: EmailStr
    full_name: str | None = None
    role: str
    is_active: bool
    email_verified: bool = False
    auth_provider: Literal["password", "google"] = "password"
    avatar_url: str | None = None
    has_password: bool = True


class ForgotPasswordRequestIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=20, max_length=1024)
    password: str = Field(min_length=8, max_length=255)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=8, max_length=255)
    new_password: str = Field(min_length=8, max_length=255)


class GoogleAuthStartOut(BaseModel):
    authorization_url: str
    state: str


class GoogleAuthCallbackIn(BaseModel):
    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=1, max_length=512)
    redirect_uri: str = Field(min_length=1, max_length=2048)


class GoogleAuthExchangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    auth_provider: Literal["google"] = "google"
    avatar_url: str | None = None

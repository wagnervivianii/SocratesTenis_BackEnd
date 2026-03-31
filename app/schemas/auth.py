from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

AuthProvider = Literal["password", "google"]


class LoginIn(BaseModel):
    email: EmailStr
    password: str


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
    auth_provider: AuthProvider | None = None
    avatar_url: str | None = None
    has_password: bool | None = None


class ForgotPasswordRequestIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=32, max_length=512)
    password: str = Field(min_length=6, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=6, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)

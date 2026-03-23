from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class StudentCreateIn(BaseModel):
    full_name: str = Field(..., min_length=3, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=1000)
    profession: str | None = Field(default=None, max_length=150)
    instagram_handle: str | None = Field(default=None, max_length=100)
    share_profession: bool = False
    share_instagram: bool = False
    is_active: bool = True


class StudentUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=1000)
    profession: str | None = Field(default=None, max_length=150)
    instagram_handle: str | None = Field(default=None, max_length=100)
    share_profession: bool | None = None
    share_instagram: bool | None = None
    is_active: bool | None = None


class StudentStatusChangeIn(BaseModel):
    reason_code: str | None = Field(default=None, max_length=60)
    reason_note: str | None = Field(default=None, max_length=1000)


class StudentOut(BaseModel):
    id: UUID
    user_id: UUID | None = None
    full_name: str
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
    profession: str | None = None
    instagram_handle: str | None = None
    share_profession: bool
    share_instagram: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class StudentListItemOut(StudentOut):
    pass


class StudentStatusHistoryItemOut(BaseModel):
    id: UUID
    student_id: UUID
    status: str
    reason_code: str | None = None
    reason_note: str | None = None
    changed_by_user_id: UUID | None = None
    created_at: datetime

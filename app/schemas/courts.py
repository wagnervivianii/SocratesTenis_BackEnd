from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CourtCreateIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    is_active: bool = True


class CourtUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    is_active: bool | None = None


class CourtStatusChangeIn(BaseModel):
    reason_code: str | None = Field(default=None, max_length=60)
    reason_note: str | None = Field(default=None, max_length=1000)


class CourtOut(BaseModel):
    id: UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CourtListItemOut(CourtOut):
    pass


class CourtStatusHistoryItemOut(BaseModel):
    id: UUID
    court_id: UUID
    status: str
    reason_code: str | None = None
    reason_note: str | None = None
    changed_by_user_id: UUID | None = None
    created_at: datetime

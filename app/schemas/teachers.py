from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class TeacherCreateIn(BaseModel):
    full_name: str = Field(..., min_length=3, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=1000)
    is_active: bool = True


class TeacherUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None


class TeacherStatusChangeIn(BaseModel):
    reason_code: str | None = Field(default=None, max_length=60)
    reason_note: str | None = Field(default=None, max_length=1000)


class TeacherOut(BaseModel):
    id: UUID
    user_id: UUID | None = None
    full_name: str
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TeacherListItemOut(TeacherOut):
    pass


class TeacherStatusHistoryItemOut(BaseModel):
    id: UUID
    teacher_id: UUID
    status: str
    reason_code: str | None = None
    reason_note: str | None = None
    changed_by_user_id: UUID | None = None
    created_at: datetime


class TeacherAvailabilityRuleOut(BaseModel):
    id: UUID
    teacher_id: UUID
    weekday: int
    start_time: time
    end_time: time
    starts_on: date
    ends_on: date | None = None
    modality: str | None = None
    court_id: UUID | None = None
    is_active: bool
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class TeacherAvailabilityExceptionOut(BaseModel):
    id: UUID
    teacher_id: UUID
    start_at: datetime
    end_at: datetime
    exception_type: str
    modality: str | None = None
    court_id: UUID | None = None
    is_active: bool
    reason: str | None = None
    created_at: datetime
    updated_at: datetime


class TeacherAgendaWeekItemOut(BaseModel):
    event_id: UUID
    kind: str
    status: str | None = None
    start_at: datetime
    end_at: datetime
    notes: str | None = None
    court_id: UUID | None = None
    court_name: str | None = None
    teacher_id: UUID | None = None
    teacher_name: str | None = None
    student_id: UUID | None = None
    student_name: str | None = None
    class_group_id: UUID | None = None
    class_group_name: str | None = None

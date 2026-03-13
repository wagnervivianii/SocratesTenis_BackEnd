from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ClassGroupLevel = Literal["iniciante", "intermediario", "avancado"]
ClassGroupEnrollmentStatus = Literal["active", "inactive", "cancelled"]


class ClassGroupCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    level: ClassGroupLevel
    teacher_id: UUID | None = None
    court_id: UUID | None = None
    capacity: int = Field(default=4, ge=1)
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=1000)


class ClassGroupUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    level: ClassGroupLevel | None = None
    teacher_id: UUID | None = None
    court_id: UUID | None = None
    capacity: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)


class ClassGroupOut(BaseModel):
    id: UUID
    name: str
    level: str
    teacher_id: UUID | None = None
    court_id: UUID | None = None
    capacity: int
    is_active: bool
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ClassGroupListItemOut(ClassGroupOut):
    teacher_name: str | None = None
    court_name: str | None = None


class ClassGroupScheduleCreateIn(BaseModel):
    weekday: int = Field(..., ge=1, le=7, description="1=segunda ... 7=domingo")
    start_time: time
    end_time: time
    starts_on: date
    ends_on: date | None = None
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=1000)


class ClassGroupScheduleUpdateIn(BaseModel):
    weekday: int | None = Field(default=None, ge=1, le=7, description="1=segunda ... 7=domingo")
    start_time: time | None = None
    end_time: time | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)


class ClassGroupScheduleOut(BaseModel):
    id: UUID
    class_group_id: UUID
    weekday: int
    start_time: time
    end_time: time
    starts_on: date
    ends_on: date | None = None
    is_active: bool
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ClassGroupEnrollmentCreateIn(BaseModel):
    student_id: UUID
    status: ClassGroupEnrollmentStatus = "active"
    starts_on: date
    ends_on: date | None = None


class ClassGroupEnrollmentUpdateIn(BaseModel):
    status: ClassGroupEnrollmentStatus | None = None
    starts_on: date | None = None
    ends_on: date | None = None


class ClassGroupEnrollmentOut(BaseModel):
    id: UUID
    class_group_id: UUID
    student_id: UUID
    status: str
    starts_on: date
    ends_on: date | None = None
    created_at: datetime
    updated_at: datetime


class ClassGroupEnrollmentListItemOut(ClassGroupEnrollmentOut):
    student_name: str
    student_email: str | None = None
    student_phone: str | None = None

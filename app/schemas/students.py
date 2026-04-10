from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

StudentMakeupRequestStatus = Literal["pending", "scheduled", "rejected", "cancelled"]
StudentMakeupRequestSource = Literal["student_portal", "admin_manual"]


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


class StudentHomeProfileOut(BaseModel):
    id: UUID
    user_id: UUID | None = None
    full_name: str
    email: str | None = None
    phone: str | None = None
    profession: str | None = None
    instagram_handle: str | None = None
    share_profession: bool
    share_instagram: bool
    is_active: bool
    avatar_url: str | None = None


class StudentHomeClassmateOut(BaseModel):
    student_id: UUID
    full_name: str
    avatar_url: str | None = None


class StudentHomeScheduleOut(BaseModel):
    schedule_id: UUID
    weekday: int
    weekday_label: str
    start_time: time
    end_time: time
    starts_on: date
    ends_on: date | None = None
    is_active: bool
    notes: str | None = None


class StudentHomeClassGroupOut(BaseModel):
    enrollment_id: UUID
    class_group_id: UUID
    class_group_name: str
    class_type: str
    level: str
    enrollment_status: str
    enrollment_starts_on: date
    enrollment_ends_on: date | None = None
    teacher_id: UUID | None = None
    teacher_name: str | None = None
    court_id: UUID | None = None
    court_name: str | None = None
    classmates: list[StudentHomeClassmateOut] = Field(default_factory=list)
    schedules: list[StudentHomeScheduleOut] = Field(default_factory=list)


class StudentHomeRentalOut(BaseModel):
    rental_id: UUID
    court_id: UUID | None = None
    court_name: str | None = None
    start_at: datetime
    end_at: datetime
    status: str
    payment_status: str
    payment_evidence_status: str | None = None
    pricing_profile: str
    billing_mode: str
    origin: str
    total_amount: Decimal | None = None
    price_per_hour: Decimal | None = None
    requested_at: datetime
    scheduled_at: datetime | None = None
    confirmed_at: datetime | None = None
    cancelled_at: datetime | None = None
    payment_expires_at: datetime | None = None


class StudentHomeOut(BaseModel):
    profile: StudentHomeProfileOut
    class_groups: list[StudentHomeClassGroupOut] = Field(default_factory=list)
    upcoming_rentals: list[StudentHomeRentalOut] = Field(default_factory=list)
    recent_rental_history: list[StudentHomeRentalOut] = Field(default_factory=list)


class StudentMakeupRequestCreateIn(BaseModel):
    class_group_enrollment_id: UUID
    original_event_id: UUID | None = None
    student_note: str | None = Field(default=None, max_length=1000)


class StudentMakeupRequestAdminCreateIn(BaseModel):
    student_id: UUID
    class_group_enrollment_id: UUID
    original_event_id: UUID | None = None
    original_lesson_date: date | None = None
    original_start_at: datetime | None = None
    original_end_at: datetime | None = None
    student_note: str | None = Field(default=None, max_length=1000)
    admin_note: str | None = Field(default=None, max_length=1000)


class StudentMakeupRequestScheduleIn(BaseModel):
    replacement_event_id: UUID | None = None
    replacement_class_group_id: UUID | None = None
    admin_note: str | None = Field(default=None, max_length=1000)


class StudentMakeupRequestReviewIn(BaseModel):
    status: Literal["scheduled", "rejected", "cancelled"]
    admin_note: str | None = Field(default=None, max_length=1000)
    replacement_event_id: UUID | None = None
    replacement_class_group_id: UUID | None = None


class StudentMakeupRequestOut(BaseModel):
    id: UUID
    student_id: UUID
    class_group_enrollment_id: UUID
    requested_by_user_id: UUID | None = None
    processed_by_user_id: UUID | None = None
    source: StudentMakeupRequestSource
    status: StudentMakeupRequestStatus

    original_event_id: UUID | None = None
    original_class_group_id: UUID | None = None
    original_teacher_id: UUID | None = None
    original_court_id: UUID | None = None
    original_lesson_date: date | None = None
    original_start_at: datetime | None = None
    original_end_at: datetime | None = None

    replacement_event_id: UUID | None = None
    replacement_class_group_id: UUID | None = None
    replacement_teacher_id: UUID | None = None
    replacement_court_id: UUID | None = None
    replacement_lesson_date: date | None = None
    replacement_start_at: datetime | None = None
    replacement_end_at: datetime | None = None

    student_note: str | None = None
    admin_note: str | None = None
    requested_at: datetime
    processed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StudentMakeupRequestListItemOut(StudentMakeupRequestOut):
    student_name: str | None = None
    original_class_group_name: str | None = None
    original_teacher_name: str | None = None
    replacement_class_group_name: str | None = None
    replacement_teacher_name: str | None = None

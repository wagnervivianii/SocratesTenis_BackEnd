from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

TrialLessonStatus = Literal[
    "requested",
    "scheduled",
    "attendance_validation_pending",
    "completed",
    "cancelled",
    "no_show",
]

TrialLessonTeacherPeriod = Literal["morning", "afternoon", "evening"]

TrialLessonExtraordinaryRequestStatus = Literal[
    "open",
    "in_progress",
    "resolved",
    "cancelled",
]

TrialLessonExtraordinaryReasonCode = Literal[
    "NO_TEACHER_WINDOW",
    "NO_TEACHER_AVAILABILITY",
    "NO_COURT_AVAILABILITY",
    "NO_AUTOMATIC_SLOT",
]


class TrialLessonEligibilityOut(BaseModel):
    eligible: bool
    reason_code: str | None = None
    message: str
    current_status: str | None = None


class TrialLessonSlotOut(BaseModel):
    start_at: datetime
    end_at: datetime
    teacher_id: UUID
    teacher_name: str
    court_id: UUID
    court_name: str
    teacher_image_url: str | None = None


class TrialLessonScheduleIn(BaseModel):
    start_at: datetime
    end_at: datetime
    teacher_id: UUID
    court_id: UUID
    notes: str | None = Field(default=None, max_length=1000)


class TrialLessonScheduleOut(BaseModel):
    trial_lesson_id: UUID
    event_id: UUID
    status: str
    start_at: datetime
    end_at: datetime
    teacher_id: UUID
    teacher_name: str
    court_id: UUID
    court_name: str
    message: str
    email_sent: bool = False


class TrialLessonCurrentOut(BaseModel):
    scheduled: bool
    message: str
    trial_lesson_id: UUID | None = None
    event_id: UUID | None = None
    status: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    court_id: UUID | None = None
    court_name: str | None = None
    teacher_id: UUID | None = None
    teacher_name: str | None = None
    teacher_image_url: str | None = None
    notes: str | None = None
    can_cancel: bool = False
    can_reschedule: bool = False
    change_deadline_at: datetime | None = None
    change_rule_message: str | None = None
    change_status_message: str | None = None


class TrialLessonCancelOut(BaseModel):
    trial_lesson_id: UUID
    event_id: UUID
    status: str
    message: str


class TrialLessonRescheduleIn(BaseModel):
    start_at: datetime
    end_at: datetime
    teacher_id: UUID
    court_id: UUID
    notes: str | None = Field(default=None, max_length=1000)


class TrialLessonRescheduleOut(BaseModel):
    trial_lesson_id: UUID
    old_event_id: UUID
    new_event_id: UUID
    status: str
    start_at: datetime
    end_at: datetime
    teacher_id: UUID
    teacher_name: str
    court_id: UUID
    court_name: str
    message: str
    email_sent: bool = False


class TrialLessonAdminPendingAttendanceItemOut(BaseModel):
    trial_lesson_id: UUID
    user_id: UUID
    event_id: UUID | None = None
    status: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    teacher_id: UUID | None = None
    teacher_name: str | None = None
    court_id: UUID | None = None
    court_name: str | None = None
    student_name: str | None = None
    student_email: str | None = None
    student_whatsapp: str | None = None
    change_status_message: str | None = None


class TrialLessonAdminPendingAttendanceListOut(BaseModel):
    items: list[TrialLessonAdminPendingAttendanceItemOut]
    total: int
    message: str


class TrialLessonAttendanceReviewIn(BaseModel):
    outcome: Literal["completed", "no_show"]
    notes: str | None = Field(default=None, max_length=1000)


class TrialLessonAttendanceReviewOut(BaseModel):
    trial_lesson_id: UUID
    status: str
    message: str


class TrialLessonTeacherWindowBase(BaseModel):
    teacher_id: UUID
    weekday: int = Field(..., ge=1, le=7)
    period: TrialLessonTeacherPeriod
    start_time: time
    end_time: time
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=1000)


class TrialLessonTeacherWindowCreateIn(TrialLessonTeacherWindowBase):
    pass


class TrialLessonTeacherWindowUpdateIn(BaseModel):
    weekday: int | None = Field(default=None, ge=1, le=7)
    period: TrialLessonTeacherPeriod | None = None
    start_time: time | None = None
    end_time: time | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)


class TrialLessonTeacherWindowOut(TrialLessonTeacherWindowBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class TrialLessonTeacherWindowListOut(BaseModel):
    items: list[TrialLessonTeacherWindowOut]
    total: int
    message: str


class TrialLessonExtraordinaryRequestCreateIn(BaseModel):
    desired_week_start: date | None = None
    desired_period: TrialLessonTeacherPeriod | None = None
    user_notes: str | None = Field(default=None, max_length=1000)
    reason_code: TrialLessonExtraordinaryReasonCode


class TrialLessonExtraordinaryRequestUpdateIn(BaseModel):
    status: TrialLessonExtraordinaryRequestStatus | None = None
    admin_notes: str | None = Field(default=None, max_length=1000)


class TrialLessonExtraordinaryRequestOut(BaseModel):
    id: UUID
    user_id: UUID
    status: str
    reason_code: str
    desired_week_start: date | None = None
    desired_period: str | None = None
    requester_name: str | None = None
    requester_email: str | None = None
    requester_whatsapp: str | None = None
    user_notes: str | None = None
    admin_notes: str | None = None
    requested_at: datetime
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TrialLessonExtraordinaryRequestListOut(BaseModel):
    items: list[TrialLessonExtraordinaryRequestOut]
    total: int
    message: str


class TrialLessonExtraordinaryRequestCreateOut(BaseModel):
    id: UUID
    status: str
    reason_code: str
    message: str

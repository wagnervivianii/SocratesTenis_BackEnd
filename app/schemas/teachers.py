from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

TeacherEventReportStatus = Literal["completed", "issue"]
TeacherEventIssueType = Literal[
    "student_absence",
    "class_not_held",
    "operational_problem",
    "other",
]
TeacherProfileUpdateRequestStatus = Literal["pending", "approved", "rejected"]
TeacherMakeupRequestStatus = Literal["pending", "scheduled", "rejected", "cancelled"]


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


class TeacherAgendaClassGroupStudentOut(BaseModel):
    student_id: UUID
    student_name: str


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
    class_group_student_names: list[str] = Field(default_factory=list)
    class_group_students: list[TeacherAgendaClassGroupStudentOut] = Field(default_factory=list)
    teacher_event_report_id: UUID | None = None
    teacher_event_report_status: TeacherEventReportStatus | None = None
    teacher_event_issue_type: TeacherEventIssueType | None = None
    event_created_at: datetime | None = None
    event_updated_at: datetime | None = None
    has_schedule_change: bool = False
    schedule_changed_at: datetime | None = None


class TeacherEventReportAbsenceOut(BaseModel):
    student_id: UUID
    student_name: str | None = None


class TeacherEventReportUpsertIn(BaseModel):
    report_status: TeacherEventReportStatus
    issue_type: TeacherEventIssueType | None = None
    notes: str | None = Field(default=None, max_length=1000)
    absent_student_ids: list[UUID] = Field(default_factory=list)


class TeacherEventReportOut(BaseModel):
    id: UUID
    event_id: UUID
    report_status: TeacherEventReportStatus
    issue_type: TeacherEventIssueType | None = None
    notes: str | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    absences: list[TeacherEventReportAbsenceOut] = Field(default_factory=list)


class TeacherProfileUpdateRequestCreateIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=1000)
    request_note: str | None = Field(default=None, max_length=1000)


class TeacherProfileUpdateRequestReviewIn(BaseModel):
    status: Literal["approved", "rejected"]
    admin_note: str | None = Field(default=None, max_length=1000)


class TeacherProfileUpdateRequestOut(BaseModel):
    id: UUID
    teacher_id: UUID
    requested_by_user_id: UUID | None = None
    reviewed_by_user_id: UUID | None = None
    status: TeacherProfileUpdateRequestStatus
    current_data: dict[str, str | None] = Field(default_factory=dict)
    proposed_data: dict[str, str | None] = Field(default_factory=dict)
    request_note: str | None = None
    admin_note: str | None = None
    requested_at: datetime
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TeacherMakeupRequestItemOut(BaseModel):
    id: UUID
    student_id: UUID
    student_name: str | None = None
    status: TeacherMakeupRequestStatus
    original_event_id: UUID | None = None
    original_class_group_id: UUID | None = None
    original_class_group_name: str | None = None
    original_teacher_id: UUID | None = None
    original_teacher_name: str | None = None
    original_court_id: UUID | None = None
    original_court_name: str | None = None
    original_lesson_date: date
    original_start_at: datetime
    original_end_at: datetime
    replacement_event_id: UUID | None = None
    replacement_class_group_id: UUID | None = None
    replacement_class_group_name: str | None = None
    replacement_teacher_id: UUID | None = None
    replacement_teacher_name: str | None = None
    replacement_court_id: UUID | None = None
    replacement_court_name: str | None = None
    replacement_lesson_date: date | None = None
    replacement_start_at: datetime | None = None
    replacement_end_at: datetime | None = None
    student_note: str | None = None
    admin_note: str | None = None
    requested_at: datetime
    processed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

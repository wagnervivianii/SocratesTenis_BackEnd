from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

StudentSignupRequestStatus = Literal["pending", "approved", "rejected"]
StudentSignupReviewAction = Literal["approve", "reject"]
EmailConfidenceStatus = Literal[
    "awaiting_review",
    "pending_confirmation",
    "confirmed",
    "rejected",
]


class StudentSignupRequestCreateIn(BaseModel):
    full_name: str = Field(..., min_length=3, max_length=150)
    email: EmailStr
    whatsapp: str = Field(..., min_length=10, max_length=20)
    instagram: str | None = Field(default=None, max_length=60)
    birth_date: date
    zip_code: str = Field(..., min_length=8, max_length=10)
    guardian_full_name: str | None = Field(default=None, min_length=3, max_length=150)
    guardian_whatsapp: str | None = Field(default=None, min_length=10, max_length=20)
    guardian_relationship: str | None = Field(default=None, max_length=60)


class StudentSignupRequestCreateOut(BaseModel):
    request_id: UUID
    status: StudentSignupRequestStatus = "pending"
    message: str = "Recebemos sua solicitação de cadastro. Ela será conferida pela equipe antes da liberação como aluno."


class StudentSignupRequestListItemOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    whatsapp: str
    instagram: str | None = None
    birth_date: date
    zip_code: str
    guardian_full_name: str | None = None
    guardian_whatsapp: str | None = None
    guardian_relationship: str | None = None
    status: StudentSignupRequestStatus
    review_note: str | None = None
    reviewed_at: datetime | None = None
    reviewed_by_user_id: UUID | None = None
    approved_user_id: UUID | None = None
    approved_student_id: UUID | None = None
    email_confidence_status: EmailConfidenceStatus = "awaiting_review"
    email_confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StudentSignupRequestOut(StudentSignupRequestListItemOut):
    pass


class StudentSignupRequestReviewIn(BaseModel):
    action: StudentSignupReviewAction
    review_note: str | None = Field(default=None, max_length=2000)


class StudentSignupRequestReviewOut(BaseModel):
    id: UUID
    status: StudentSignupRequestStatus
    reviewed_at: datetime
    reviewed_by_user_id: UUID
    approved_user_id: UUID | None = None
    approved_student_id: UUID | None = None
    email_confidence_status: EmailConfidenceStatus = "awaiting_review"
    email_confirmed_at: datetime | None = None
    message: str

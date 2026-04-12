from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

StudentSignupRequestStatus = Literal["pending", "approved", "rejected"]
StudentSignupReviewAction = Literal["approve", "reject"]
EmailConfidenceStatus = Literal[
    "awaiting_review",
    "pending_confirmation",
    "confirmed",
    "rejected",
]

_PROFESSION_PATTERN = re.compile(r"^[^\W\d_]+(?: [^\W\d_]+)*$", re.UNICODE)


def _normalize_profession(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = " ".join(value.strip().split())
    if not normalized:
        return None

    normalized = normalized.upper()

    if not _PROFESSION_PATTERN.fullmatch(normalized):
        raise ValueError("Profissão deve conter apenas letras e espaços.")

    return normalized


class StudentSignupRequestCreateIn(BaseModel):
    full_name: str = Field(..., min_length=3, max_length=150)
    email: EmailStr
    whatsapp: str = Field(..., min_length=10, max_length=20)
    instagram: str | None = Field(default=None, max_length=60)
    profession: str | None = Field(default=None, max_length=120)
    share_profession: bool = False
    share_instagram: bool = False
    birth_date: date
    zip_code: str = Field(..., min_length=8, max_length=10)
    guardian_full_name: str | None = Field(default=None, min_length=3, max_length=150)
    guardian_email: EmailStr | None = None
    guardian_whatsapp: str | None = Field(default=None, min_length=10, max_length=20)
    guardian_relationship: str | None = Field(default=None, max_length=60)

    @field_validator("profession", mode="before")
    @classmethod
    def validate_profession(cls, value: str | None) -> str | None:
        return _normalize_profession(value)

    @model_validator(mode="after")
    def validate_shared_fields(self) -> StudentSignupRequestCreateIn:
        if self.share_profession and not self.profession:
            raise ValueError("Informe a profissão antes de autorizar o compartilhamento.")

        if self.share_instagram and not (self.instagram and self.instagram.strip()):
            raise ValueError("Informe o Instagram antes de autorizar o compartilhamento.")

        return self


class StudentSignupRequestAdminUpdateIn(StudentSignupRequestCreateIn):
    pass


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
    profession: str | None = None
    share_profession: bool = False
    share_instagram: bool = False
    birth_date: date
    zip_code: str
    guardian_full_name: str | None = None
    guardian_email: str | None = None
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


class StudentSignupRequestReopenOut(BaseModel):
    id: UUID
    status: StudentSignupRequestStatus
    message: str

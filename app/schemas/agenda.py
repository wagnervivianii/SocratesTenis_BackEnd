from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AgendaItemOut(BaseModel):
    event_id: UUID
    kind: str
    status: str
    start_at: datetime
    end_at: datetime
    notes: str | None = None

    court_id: UUID
    court_name: str

    teacher_id: UUID | None = None
    teacher_name: str | None = None

    student_id: UUID | None = None
    student_name: str | None = None

    created_by_user_id: UUID | None = None
    created_by_email: str | None = None

    created_at: datetime
    updated_at: datetime


class CourtDisponivelOut(BaseModel):
    court_id: UUID
    court_name: str


class ProfessorDisponivelOut(BaseModel):
    teacher_id: UUID
    teacher_name: str

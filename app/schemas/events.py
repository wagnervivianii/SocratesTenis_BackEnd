from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EventCreateIn(BaseModel):
    court_id: UUID
    kind: str = Field(..., description="aula_regular|primeira_aula|locacao|bloqueio")
    start_at: datetime
    end_at: datetime
    notes: str | None = None

    teacher_id: UUID | None = None
    student_id: UUID | None = None

    status: str = "confirmado"


class EventOut(BaseModel):
    id: UUID
    court_id: UUID
    teacher_id: UUID | None = None
    student_id: UUID | None = None
    created_by: UUID | None = None
    kind: str
    status: str
    start_at: datetime
    end_at: datetime
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

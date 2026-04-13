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

    class_group_id: UUID | None = None
    class_group_name: str | None = None
    class_group_student_names: list[str] | None = None

    court_rental_id: UUID | None = None
    court_rental_origin: str | None = None
    court_rental_pricing_profile: str | None = None
    court_rental_payment_status: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_whatsapp: str | None = None

    trial_lesson_id: UUID | None = None
    trial_user_id: UUID | None = None
    trial_user_name: str | None = None
    trial_user_email: str | None = None
    trial_user_whatsapp: str | None = None

    event_group: str | None = None
    event_label: str | None = None
    color_key: str | None = None
    participant_label: str | None = None
    is_recurring: bool | None = None


class CourtDisponivelOut(BaseModel):
    court_id: UUID
    court_name: str


class ProfessorDisponivelOut(BaseModel):
    teacher_id: UUID
    teacher_name: str

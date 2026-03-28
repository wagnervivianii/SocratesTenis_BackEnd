from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CourtRentalPaymentProofOut(BaseModel):
    id: UUID
    court_rental_id: UUID
    uploaded_by_user_id: UUID | None = None
    original_file_name: str
    stored_file_name: str
    storage_path: str
    mime_type: str
    file_size_bytes: int
    notes: str | None = None
    created_at: datetime


class CourtRentalPaymentProofListItemOut(CourtRentalPaymentProofOut):
    pass


class CourtRentalPaymentProofUploadOut(BaseModel):
    rental_id: UUID
    status: str
    payment_status: str
    payment_proof_submitted_at: datetime | None = None
    payment_received_amount: str | None = None
    proof: CourtRentalPaymentProofOut
    message: str
    email_sent: bool


class CourtRentalPaymentProofUploadMetaIn(BaseModel):
    payment_received_amount: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=1000)

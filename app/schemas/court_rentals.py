from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

CourtRentalOrigin = Literal[
    "public_landing",
    "admin_panel",
    "student_portal",
    "admin_for_student",
]

CourtRentalPricingProfile = Literal[
    "student",
    "third_party",
]

CourtRentalStatus = Literal[
    "requested",
    "awaiting_payment",
    "awaiting_proof",
    "awaiting_admin_review",
    "scheduled",
    "confirmed",
    "completed",
    "rejected",
    "cancelled",
]

CourtRentalPaymentStatus = Literal[
    "not_required",
    "pending",
    "proof_sent",
    "under_review",
    "approved",
    "rejected",
    "expired",
]


class CourtRentalEligibilityOut(BaseModel):
    eligible: bool
    message: str


class CourtRentalSlotOut(BaseModel):
    start_at: datetime
    end_at: datetime
    court_id: UUID
    court_name: str


class CourtRentalCourtCardOut(BaseModel):
    court_id: UUID
    court_name: str
    surface_type: str | None = None
    cover_type: str | None = None
    image_url: str | None = None
    short_description: str | None = None
    has_slots_in_range: bool
    available_slots_count: int = 0
    next_available_start_at: datetime | None = None
    next_available_end_at: datetime | None = None
    availability_message: str


class CourtRentalScheduleIn(BaseModel):
    court_id: UUID
    start_at: datetime
    end_at: datetime
    notes: str | None = Field(default=None, max_length=1000)


class CourtRentalPublicCreateIn(BaseModel):
    court_id: UUID
    start_at: datetime
    end_at: datetime
    customer_name: str | None = Field(default=None, min_length=3, max_length=150)
    customer_email: EmailStr | None = None
    customer_whatsapp: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)


class CourtRentalAdminCreateIn(BaseModel):
    court_id: UUID
    start_at: datetime
    end_at: datetime
    origin: CourtRentalOrigin = "admin_panel"
    pricing_profile: CourtRentalPricingProfile = "third_party"
    customer_user_id: UUID | None = None
    customer_student_id: UUID | None = None
    customer_name: str | None = Field(default=None, min_length=3, max_length=150)
    customer_email: EmailStr | None = None
    customer_whatsapp: str | None = Field(default=None, max_length=20)
    price_per_hour: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    total_amount: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    pix_key: str | None = Field(default=None, max_length=500)
    pix_qr_code_payload: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=1000)


class CourtRentalAdminUpdateIn(BaseModel):
    pricing_profile: CourtRentalPricingProfile | None = None
    customer_user_id: UUID | None = None
    customer_student_id: UUID | None = None
    customer_name: str | None = Field(default=None, min_length=3, max_length=150)
    customer_email: EmailStr | None = None
    customer_whatsapp: str | None = Field(default=None, max_length=20)
    price_per_hour: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    total_amount: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    pix_key: str | None = Field(default=None, max_length=500)
    pix_qr_code_payload: str | None = Field(default=None, max_length=5000)
    status: CourtRentalStatus | None = None
    payment_status: CourtRentalPaymentStatus | None = None
    notes: str | None = Field(default=None, max_length=1000)


class CourtRentalAdminPaymentDefinitionIn(BaseModel):
    price_per_hour: Decimal = Field(..., ge=0, max_digits=10, decimal_places=2)
    pix_key: str = Field(..., min_length=3, max_length=500)
    total_amount: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    pix_qr_code_payload: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=1000)


class CourtRentalAdminPaymentDefinitionOut(BaseModel):
    rental_id: UUID
    pricing_profile: CourtRentalPricingProfile | None = None
    status: str
    payment_status: str
    price_per_hour: Decimal | None = None
    total_amount: Decimal | None = None
    pix_key: str | None = None
    pix_qr_code_payload: str | None = None
    message: str
    email_sent: bool = False


class CourtRentalProofSubmissionIn(BaseModel):
    payment_received_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=10,
        decimal_places=2,
    )
    payment_review_notes: str | None = Field(default=None, max_length=1000)


class CourtRentalProofSubmissionOut(BaseModel):
    rental_id: UUID
    pricing_profile: CourtRentalPricingProfile | None = None
    status: str
    payment_status: str
    payment_proof_submitted_at: datetime | None = None
    payment_received_amount: Decimal | None = None
    message: str
    email_sent: bool = False


class CourtRentalPaymentReviewIn(BaseModel):
    payment_status: Literal["approved", "rejected"]
    payment_received_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=10,
        decimal_places=2,
    )
    payment_amount_matches_expected: bool | None = None
    payment_review_notes: str | None = Field(default=None, max_length=1000)


class CourtRentalPaymentReviewOut(BaseModel):
    rental_id: UUID
    pricing_profile: CourtRentalPricingProfile | None = None
    status: str
    payment_status: str
    payment_reviewed_at: datetime | None = None
    payment_amount_matches_expected: bool | None = None
    payment_received_amount: Decimal | None = None
    confirmed_at: datetime | None = None
    message: str
    email_sent: bool = False


class CourtRentalScheduleOut(BaseModel):
    rental_id: UUID
    event_id: UUID
    status: str
    payment_status: str | None = None
    origin: str | None = None
    pricing_profile: CourtRentalPricingProfile | None = None
    start_at: datetime
    end_at: datetime
    court_id: UUID
    message: str
    email_sent: bool = False


class CourtRentalUpcomingItemOut(BaseModel):
    rental_id: UUID
    event_id: UUID
    status: str
    payment_status: str | None = None
    origin: str | None = None
    pricing_profile: CourtRentalPricingProfile | None = None
    start_at: datetime
    end_at: datetime
    court_id: UUID
    court_name: str
    customer_name: str | None = None
    customer_email: str | None = None
    customer_whatsapp: str | None = None
    notes: str | None = None
    can_cancel: bool = False
    can_reschedule: bool = False
    change_deadline_at: datetime | None = None
    change_rule_message: str | None = None
    change_status_message: str | None = None


class CourtRentalUpcomingListOut(BaseModel):
    items: list[CourtRentalUpcomingItemOut]
    message: str


class CourtRentalHistoryItemOut(BaseModel):
    rental_id: UUID
    event_id: UUID | None = None
    status: str
    payment_status: str | None = None
    origin: str | None = None
    pricing_profile: CourtRentalPricingProfile | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    court_id: UUID | None = None
    court_name: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_whatsapp: str | None = None
    total_amount: Decimal | None = None
    payment_received_amount: Decimal | None = None
    payment_proof_submitted_at: datetime | None = None
    payment_reviewed_at: datetime | None = None
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    requested_at: datetime | None = None
    notes: str | None = None
    can_cancel: bool = False
    can_reschedule: bool = False
    change_deadline_at: datetime | None = None
    change_rule_message: str | None = None
    change_status_message: str | None = None


class CourtRentalHistoryListOut(BaseModel):
    items: list[CourtRentalHistoryItemOut]
    total: int
    message: str


class CourtRentalCancelOut(BaseModel):
    rental_id: UUID
    event_id: UUID
    pricing_profile: CourtRentalPricingProfile | None = None
    status: str
    payment_status: str | None = None
    message: str
    email_sent: bool = False


class CourtRentalRescheduleIn(BaseModel):
    court_id: UUID
    start_at: datetime
    end_at: datetime
    notes: str | None = Field(default=None, max_length=1000)


class CourtRentalRescheduleOut(BaseModel):
    rental_id: UUID
    old_event_id: UUID
    new_event_id: UUID
    pricing_profile: CourtRentalPricingProfile | None = None
    status: str
    payment_status: str | None = None
    start_at: datetime
    end_at: datetime
    court_id: UUID
    message: str
    email_sent: bool = False


class CourtRentalPaymentInstructionOut(BaseModel):
    rental_id: UUID
    pricing_profile: CourtRentalPricingProfile | None = None
    payment_status: str
    total_amount: Decimal | None = None
    pix_key: str | None = None
    pix_qr_code_payload: str | None = None
    payment_expires_at: datetime | None = None
    message: str


class CourtRentalOut(BaseModel):
    id: UUID
    user_id: UUID | None = None
    created_by_user_id: UUID | None = None
    customer_user_id: UUID | None = None
    customer_student_id: UUID | None = None
    payment_reviewed_by_user_id: UUID | None = None
    event_id: UUID | None = None
    origin: str
    pricing_profile: CourtRentalPricingProfile
    status: str
    payment_status: str
    customer_name: str | None = None
    customer_email: str | None = None
    customer_whatsapp: str | None = None
    price_per_hour: Decimal | None = None
    total_amount: Decimal | None = None
    payment_received_amount: Decimal | None = None
    pix_key: str | None = None
    pix_qr_code_payload: str | None = None
    requested_at: datetime
    scheduled_at: datetime | None = None
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    payment_expires_at: datetime | None = None
    confirmation_email_sent_at: datetime | None = None
    payment_proof_submitted_at: datetime | None = None
    payment_reviewed_at: datetime | None = None
    payment_amount_matches_expected: bool | None = None
    payment_review_notes: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class CourtRentalAdminListItemOut(BaseModel):
    id: UUID
    origin: str
    pricing_profile: CourtRentalPricingProfile
    status: str
    payment_status: str
    court_id: UUID | None = None
    court_name: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_whatsapp: str | None = None
    total_amount: Decimal | None = None
    payment_amount_matches_expected: bool | None = None
    payment_proof_submitted_at: datetime | None = None
    payment_reviewed_at: datetime | None = None
    confirmed_at: datetime | None = None
    created_at: datetime


class CourtRentalAdminListOut(BaseModel):
    items: list[CourtRentalAdminListItemOut]
    total: int
    from_date: date | None = None
    to_date: date | None = None

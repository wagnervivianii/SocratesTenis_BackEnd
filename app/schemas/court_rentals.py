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

CourtRentalBillingMode = Literal[
    "single_pix",
    "monthly_invoice",
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

CourtRentalPaymentEvidenceStatus = Literal[
    "pending",
    "customer_uploaded",
    "admin_uploaded",
    "not_sent",
    "not_applicable",
]

CourtRentalOutcomeStatus = Literal[
    "pending",
    "ok",
    "issue",
]

CourtRentalOutcomeIssueType = Literal[
    "payment_problem",
    "no_show",
    "bad_behavior",
    "property_damage",
    "late_arrival_or_early_leave",
    "other",
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
    billing_mode: CourtRentalBillingMode = "single_pix"
    customer_user_id: UUID | None = None
    customer_student_id: UUID | None = None
    customer_name: str | None = Field(default=None, min_length=3, max_length=150)
    customer_email: EmailStr | None = None
    customer_whatsapp: str | None = Field(default=None, max_length=20)
    price_per_hour: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    total_amount: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    pix_key: str | None = Field(default=None, max_length=500)
    pix_qr_code_payload: str | None = Field(default=None, max_length=5000)
    payment_evidence_status: CourtRentalPaymentEvidenceStatus | None = None
    payment_evidence_notes: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=1000)


class CourtRentalAdminUpdateIn(BaseModel):
    pricing_profile: CourtRentalPricingProfile | None = None
    billing_mode: CourtRentalBillingMode | None = None
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
    payment_evidence_status: CourtRentalPaymentEvidenceStatus | None = None
    payment_evidence_notes: str | None = Field(default=None, max_length=1000)
    outcome_status: CourtRentalOutcomeStatus | None = None
    outcome_issue_type: CourtRentalOutcomeIssueType | None = None
    outcome_notes: str | None = Field(default=None, max_length=1000)
    deactivation_reason: str | None = Field(default=None, max_length=1000)
    reactivation_reason: str | None = Field(default=None, max_length=1000)
    reschedule_reason: str | None = Field(default=None, max_length=1000)
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
    billing_mode: CourtRentalBillingMode | None = None
    status: str
    payment_status: str
    payment_evidence_status: CourtRentalPaymentEvidenceStatus | None = None
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
    billing_mode: CourtRentalBillingMode | None = None
    status: str
    payment_status: str
    payment_evidence_status: CourtRentalPaymentEvidenceStatus | None = None
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
    billing_mode: CourtRentalBillingMode | None = None
    status: str
    payment_status: str
    payment_evidence_status: CourtRentalPaymentEvidenceStatus | None = None
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
    billing_mode: CourtRentalBillingMode | None = None
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
    billing_mode: CourtRentalBillingMode | None = None
    payment_evidence_status: CourtRentalPaymentEvidenceStatus | None = None
    outcome_status: CourtRentalOutcomeStatus | None = None
    outcome_issue_type: CourtRentalOutcomeIssueType | None = None
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
    billing_mode: CourtRentalBillingMode | None = None
    payment_evidence_status: CourtRentalPaymentEvidenceStatus | None = None
    payment_evidence_notes: str | None = None
    outcome_status: CourtRentalOutcomeStatus | None = None
    outcome_issue_type: CourtRentalOutcomeIssueType | None = None
    outcome_notes: str | None = None
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
    deactivated_at: datetime | None = None
    reactivated_at: datetime | None = None
    rescheduled_at: datetime | None = None
    rescheduled_from_rental_id: UUID | None = None
    rescheduled_to_rental_id: UUID | None = None
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
    billing_mode: CourtRentalBillingMode | None = None
    status: str
    payment_status: str | None = None
    payment_evidence_status: CourtRentalPaymentEvidenceStatus | None = None
    deactivated_at: datetime | None = None
    message: str
    email_sent: bool = False


class CourtRentalRescheduleIn(BaseModel):
    court_id: UUID
    start_at: datetime
    end_at: datetime
    notes: str | None = Field(default=None, max_length=1000)
    reschedule_reason: str | None = Field(default=None, max_length=1000)


class CourtRentalRescheduleOut(BaseModel):
    rental_id: UUID
    old_event_id: UUID
    new_event_id: UUID
    pricing_profile: CourtRentalPricingProfile | None = None
    billing_mode: CourtRentalBillingMode | None = None
    status: str
    payment_status: str | None = None
    start_at: datetime
    end_at: datetime
    court_id: UUID
    rescheduled_at: datetime | None = None
    message: str
    email_sent: bool = False


class CourtRentalPaymentInstructionOut(BaseModel):
    rental_id: UUID
    pricing_profile: CourtRentalPricingProfile | None = None
    billing_mode: CourtRentalBillingMode | None = None
    payment_status: str
    payment_evidence_status: CourtRentalPaymentEvidenceStatus | None = None
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
    payment_evidence_recorded_by_user_id: UUID | None = None
    outcome_recorded_by_user_id: UUID | None = None
    deactivated_by_user_id: UUID | None = None
    reactivated_by_user_id: UUID | None = None
    rescheduled_by_user_id: UUID | None = None
    event_id: UUID | None = None
    rescheduled_from_rental_id: UUID | None = None
    rescheduled_to_rental_id: UUID | None = None
    origin: str
    pricing_profile: CourtRentalPricingProfile
    billing_mode: CourtRentalBillingMode = "single_pix"
    status: str
    payment_status: str
    payment_evidence_status: CourtRentalPaymentEvidenceStatus | None = None
    payment_evidence_notes: str | None = None
    payment_evidence_recorded_at: datetime | None = None
    outcome_status: CourtRentalOutcomeStatus | None = None
    outcome_issue_type: CourtRentalOutcomeIssueType | None = None
    outcome_notes: str | None = None
    outcome_recorded_at: datetime | None = None
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
    deactivated_at: datetime | None = None
    deactivation_reason: str | None = None
    reactivated_at: datetime | None = None
    reactivation_reason: str | None = None
    rescheduled_at: datetime | None = None
    reschedule_reason: str | None = None
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
    billing_mode: CourtRentalBillingMode = "single_pix"
    status: str
    payment_status: str
    payment_evidence_status: CourtRentalPaymentEvidenceStatus | None = None
    outcome_status: CourtRentalOutcomeStatus | None = None
    outcome_issue_type: CourtRentalOutcomeIssueType | None = None
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
    deactivated_at: datetime | None = None
    created_at: datetime


class CourtRentalAdminListOut(BaseModel):
    items: list[CourtRentalAdminListItemOut]
    total: int
    from_date: date | None = None
    to_date: date | None = None

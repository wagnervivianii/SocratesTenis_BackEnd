from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CourtRental(Base):
    __tablename__ = "court_rentals"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    customer_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    customer_student_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    payment_reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    origin: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'public_landing'"),
        index=True,
    )

    pricing_profile: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'third_party'"),
        index=True,
    )

    billing_mode: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'single_pix'"),
        index=True,
    )

    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'requested'"),
        index=True,
    )

    payment_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'not_required'"),
        index=True,
    )

    payment_evidence_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'pending'"),
        index=True,
    )

    payment_evidence_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    payment_evidence_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    payment_evidence_recorded_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    outcome_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'pending'"),
        index=True,
    )

    outcome_issue_type: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        index=True,
    )

    outcome_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    outcome_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    outcome_recorded_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    deactivated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    deactivation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    reactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    reactivated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    reactivation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    rescheduled_from_rental_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("court_rentals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    rescheduled_to_rental_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("court_rentals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    rescheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    rescheduled_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    reschedule_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    customer_name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    customer_email: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    customer_whatsapp: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    price_per_hour: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    total_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    payment_received_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    pix_key: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    pix_qr_code_payload: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    payment_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    confirmation_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    payment_proof_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    payment_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    payment_amount_matches_expected: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    payment_review_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

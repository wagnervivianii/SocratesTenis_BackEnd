from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CourtRentalPaymentSetting(Base):
    __tablename__ = "court_rental_payment_settings"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'Configuração principal'"),
    )

    pix_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    merchant_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'SOCRATES TENIS'"),
    )

    merchant_city: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'SAO PAULO'"),
    )

    student_price_per_hour: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    third_party_price_per_hour: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    proof_whatsapp: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    payment_instructions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

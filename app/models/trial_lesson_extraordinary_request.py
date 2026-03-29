from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TrialLessonExtraordinaryRequest(Base):
    __tablename__ = "trial_lesson_extraordinary_requests"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'open'"),
        index=True,
    )

    reason_code: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    desired_week_start: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    desired_period: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    requester_name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    requester_email: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    requester_whatsapp: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    user_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    admin_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

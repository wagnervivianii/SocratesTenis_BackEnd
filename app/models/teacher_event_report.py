from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TeacherEventReport(Base):
    __tablename__ = "teacher_event_reports"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_teacher_event_reports_event_id"),
        CheckConstraint(
            "report_status IN ('completed', 'issue')",
            name="ck_teacher_event_reports_report_status",
        ),
        CheckConstraint(
            "issue_type IS NULL OR issue_type IN ('student_absence', 'class_not_held', 'operational_problem', 'other')",
            name="ck_teacher_event_reports_issue_type",
        ),
        CheckConstraint(
            "(report_status = 'completed' AND issue_type IS NULL) OR "
            "(report_status = 'issue' AND issue_type IS NOT NULL)",
            name="ck_teacher_event_reports_status_issue_type_match",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    teacher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    report_status: Mapped[str] = mapped_column(Text, nullable=False)
    issue_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
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
    )

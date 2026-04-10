"""create student makeup requests

Revision ID: 9b1e4c7d2f6a
Revises: 8b7d6c5e4f3a
Create Date: 2026-04-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b1e4c7d2f6a"
down_revision: str | Sequence[str] | None = "8b7d6c5e4f3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


STATUS_CHECK = "status IN ('pending', 'scheduled', 'rejected', 'cancelled')"
SOURCE_CHECK = "source IN ('student_portal', 'admin_manual')"


def upgrade() -> None:
    op.create_table(
        "student_makeup_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "student_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "class_group_enrollment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("class_group_enrollments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "processed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'student_portal'"),
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "original_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "original_class_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("class_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "original_teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teachers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "original_court_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("original_lesson_date", sa.Date(), nullable=False),
        sa.Column("original_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("original_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "replacement_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "replacement_class_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("class_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "replacement_teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teachers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "replacement_court_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("replacement_lesson_date", sa.Date(), nullable=True),
        sa.Column("replacement_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replacement_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("student_note", sa.Text(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(STATUS_CHECK, name="ck_student_makeup_requests_status"),
        sa.CheckConstraint(SOURCE_CHECK, name="ck_student_makeup_requests_source"),
    )

    op.create_index(
        "ix_student_makeup_requests_student_id",
        "student_makeup_requests",
        ["student_id"],
    )
    op.create_index(
        "ix_student_makeup_requests_enrollment_id",
        "student_makeup_requests",
        ["class_group_enrollment_id"],
    )
    op.create_index(
        "ix_student_makeup_requests_status",
        "student_makeup_requests",
        ["status"],
    )
    op.create_index(
        "ix_student_makeup_requests_requested_at",
        "student_makeup_requests",
        ["requested_at"],
    )
    op.create_index(
        "ix_student_makeup_requests_original_lesson_date",
        "student_makeup_requests",
        ["original_lesson_date"],
    )
    op.create_index(
        "ix_student_makeup_requests_original_teacher_id",
        "student_makeup_requests",
        ["original_teacher_id"],
    )
    op.create_index(
        "ix_student_makeup_requests_replacement_teacher_id",
        "student_makeup_requests",
        ["replacement_teacher_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_student_makeup_requests_replacement_teacher_id",
        table_name="student_makeup_requests",
    )
    op.drop_index(
        "ix_student_makeup_requests_original_teacher_id",
        table_name="student_makeup_requests",
    )
    op.drop_index(
        "ix_student_makeup_requests_original_lesson_date",
        table_name="student_makeup_requests",
    )
    op.drop_index(
        "ix_student_makeup_requests_requested_at",
        table_name="student_makeup_requests",
    )
    op.drop_index(
        "ix_student_makeup_requests_status",
        table_name="student_makeup_requests",
    )
    op.drop_index(
        "ix_student_makeup_requests_enrollment_id",
        table_name="student_makeup_requests",
    )
    op.drop_index(
        "ix_student_makeup_requests_student_id",
        table_name="student_makeup_requests",
    )
    op.drop_table("student_makeup_requests")

"""add trial lesson teacher windows and extraordinary requests

Revision ID: 9c2d4f1a7b3e
Revises: f4a9c2d7b6e3
Create Date: 2026-03-29 10:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "9c2d4f1a7b3e"
down_revision = "f4a9c2d7b6e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trial_lesson_teacher_windows",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teachers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint("weekday BETWEEN 1 AND 7", name="ck_tltw_weekday_range"),
        sa.CheckConstraint(
            "period IN ('morning', 'afternoon', 'evening')",
            name="ck_tltw_period_allowed",
        ),
        sa.CheckConstraint("start_time < end_time", name="ck_tltw_time_range"),
        sa.UniqueConstraint(
            "teacher_id",
            "weekday",
            "period",
            "start_time",
            "end_time",
            name="uq_tltw_teacher_period_window",
        ),
    )

    op.create_index(
        "ix_tltw_teacher_id",
        "trial_lesson_teacher_windows",
        ["teacher_id"],
        unique=False,
    )
    op.create_index(
        "ix_tltw_weekday_period_active",
        "trial_lesson_teacher_windows",
        ["weekday", "period", "is_active"],
        unique=False,
    )

    op.create_table(
        "trial_lesson_extraordinary_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("desired_week_start", sa.Date(), nullable=True),
        sa.Column("desired_period", sa.Text(), nullable=True),
        sa.Column("requester_name", sa.Text(), nullable=True),
        sa.Column("requester_email", sa.Text(), nullable=True),
        sa.Column("requester_whatsapp", sa.String(length=20), nullable=True),
        sa.Column("user_notes", sa.Text(), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
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
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved', 'cancelled')",
            name="ck_tler_status_allowed",
        ),
        sa.CheckConstraint(
            "reason_code IN ("
            "'NO_TEACHER_WINDOW', "
            "'NO_TEACHER_AVAILABILITY', "
            "'NO_COURT_AVAILABILITY', "
            "'NO_AUTOMATIC_SLOT'"
            ")",
            name="ck_tler_reason_code_allowed",
        ),
        sa.CheckConstraint(
            "desired_period IS NULL OR desired_period IN ('morning', 'afternoon', 'evening')",
            name="ck_tler_desired_period_allowed",
        ),
    )

    op.create_index(
        "ix_tler_user_id",
        "trial_lesson_extraordinary_requests",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_tler_status_requested_at",
        "trial_lesson_extraordinary_requests",
        ["status", "requested_at"],
        unique=False,
    )

    op.create_index(
        "uq_tler_one_open_request_per_user",
        "trial_lesson_extraordinary_requests",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('open', 'in_progress')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_tler_one_open_request_per_user",
        table_name="trial_lesson_extraordinary_requests",
    )
    op.drop_index(
        "ix_tler_status_requested_at",
        table_name="trial_lesson_extraordinary_requests",
    )
    op.drop_index(
        "ix_tler_user_id",
        table_name="trial_lesson_extraordinary_requests",
    )
    op.drop_table("trial_lesson_extraordinary_requests")

    op.drop_index(
        "ix_tltw_weekday_period_active",
        table_name="trial_lesson_teacher_windows",
    )
    op.drop_index(
        "ix_tltw_teacher_id",
        table_name="trial_lesson_teacher_windows",
    )
    op.drop_table("trial_lesson_teacher_windows")

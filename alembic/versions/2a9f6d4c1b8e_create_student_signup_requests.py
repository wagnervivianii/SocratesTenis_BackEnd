"""create student signup requests

Revision ID: 2a9f6d4c1b8e
Revises: c1d2e3f4a5b6
Create Date: 2026-04-04 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "2a9f6d4c1b8e"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


STATUS_CHECK_NAME = "student_signup_requests_status_check"


def upgrade() -> None:
    op.create_table(
        "student_signup_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("whatsapp", sa.String(length=11), nullable=False),
        sa.Column("instagram", sa.String(length=60), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("zip_code", sa.String(length=8), nullable=False),
        sa.Column("guardian_full_name", sa.Text(), nullable=True),
        sa.Column("guardian_whatsapp", sa.String(length=11), nullable=True),
        sa.Column("guardian_relationship", sa.String(length=60), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reviewed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_student_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("students.id", ondelete="SET NULL"),
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
            "status IN ('pending', 'approved', 'rejected')",
            name=STATUS_CHECK_NAME,
        ),
    )

    op.create_index(
        "ix_student_signup_requests_status",
        "student_signup_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_student_signup_requests_email",
        "student_signup_requests",
        ["email"],
        unique=False,
    )
    op.create_index(
        "ix_student_signup_requests_whatsapp",
        "student_signup_requests",
        ["whatsapp"],
        unique=False,
    )
    op.create_index(
        "ix_student_signup_requests_created_at",
        "student_signup_requests",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_student_signup_requests_reviewed_by_user_id",
        "student_signup_requests",
        ["reviewed_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_student_signup_requests_approved_user_id",
        "student_signup_requests",
        ["approved_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_student_signup_requests_approved_student_id",
        "student_signup_requests",
        ["approved_student_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_student_signup_requests_approved_student_id",
        table_name="student_signup_requests",
    )
    op.drop_index(
        "ix_student_signup_requests_approved_user_id",
        table_name="student_signup_requests",
    )
    op.drop_index(
        "ix_student_signup_requests_reviewed_by_user_id",
        table_name="student_signup_requests",
    )
    op.drop_index(
        "ix_student_signup_requests_created_at",
        table_name="student_signup_requests",
    )
    op.drop_index(
        "ix_student_signup_requests_whatsapp",
        table_name="student_signup_requests",
    )
    op.drop_index(
        "ix_student_signup_requests_email",
        table_name="student_signup_requests",
    )
    op.drop_index(
        "ix_student_signup_requests_status",
        table_name="student_signup_requests",
    )
    op.drop_table("student_signup_requests")

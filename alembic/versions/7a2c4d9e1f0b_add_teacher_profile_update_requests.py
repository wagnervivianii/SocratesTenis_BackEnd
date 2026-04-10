"""add teacher profile update requests

Revision ID: 7a2c4d9e1f0b
Revises: 3c5d7e9f1a2b
Create Date: 2026-04-09 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "7a2c4d9e1f0b"
down_revision = "3c5d7e9f1a2b"
branch_labels = None
depends_on = None

REQUEST_STATUS_CHECK = "teacher_profile_update_requests_status_check"


def upgrade() -> None:
    op.create_table(
        "teacher_profile_update_requests",
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
            sa.ForeignKey("public.teachers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reviewed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "current_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "proposed_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("teacher_note", sa.Text(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name=REQUEST_STATUS_CHECK,
        ),
    )

    op.create_index(
        "ix_teacher_profile_update_requests_teacher_id",
        "teacher_profile_update_requests",
        ["teacher_id"],
    )
    op.create_index(
        "ix_teacher_profile_update_requests_status",
        "teacher_profile_update_requests",
        ["status"],
    )
    op.create_index(
        "ix_teacher_profile_update_requests_requested_at",
        "teacher_profile_update_requests",
        ["requested_at"],
    )
    op.create_index(
        "ix_teacher_profile_update_requests_pending_teacher",
        "teacher_profile_update_requests",
        ["teacher_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_teacher_profile_update_requests_pending_teacher",
        table_name="teacher_profile_update_requests",
    )
    op.drop_index(
        "ix_teacher_profile_update_requests_requested_at",
        table_name="teacher_profile_update_requests",
    )
    op.drop_index(
        "ix_teacher_profile_update_requests_status",
        table_name="teacher_profile_update_requests",
    )
    op.drop_index(
        "ix_teacher_profile_update_requests_teacher_id",
        table_name="teacher_profile_update_requests",
    )
    op.drop_table("teacher_profile_update_requests")

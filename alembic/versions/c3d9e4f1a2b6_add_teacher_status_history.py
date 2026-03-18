"""add teacher status history

Revision ID: c3d9e4f1a2b6
Revises: b8e1f0c4d2a7
Create Date: 2026-03-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d9e4f1a2b6"
down_revision: str | Sequence[str] | None = "b8e1f0c4d2a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teacher_status_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("reason_note", sa.Text(), nullable=True),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_teacher_status_history_status",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["teachers.id"],
            name="fk_teacher_status_history_teacher_id_teachers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            name="fk_teacher_status_history_changed_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teacher_status_history"),
    )

    op.create_index(
        "ix_teacher_status_history_teacher_id",
        "teacher_status_history",
        ["teacher_id"],
    )

    op.create_index(
        "ix_teacher_status_history_changed_by_user_id",
        "teacher_status_history",
        ["changed_by_user_id"],
    )

    op.create_index(
        "ix_teacher_status_history_created_at",
        "teacher_status_history",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_teacher_status_history_created_at",
        table_name="teacher_status_history",
    )
    op.drop_index(
        "ix_teacher_status_history_changed_by_user_id",
        table_name="teacher_status_history",
    )
    op.drop_index(
        "ix_teacher_status_history_teacher_id",
        table_name="teacher_status_history",
    )
    op.drop_table("teacher_status_history")

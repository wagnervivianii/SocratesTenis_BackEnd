"""add class group status history

Revision ID: a1b2c3d4e5f6
Revises: f6c2b9a4d1e8
Create Date: 2026-03-23 21:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f6c2b9a4d1e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "class_group_status_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("class_group_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            name="ck_class_group_status_history_status",
        ),
        sa.ForeignKeyConstraint(
            ["class_group_id"],
            ["class_groups.id"],
            name="fk_class_group_status_history_class_group_id_class_groups",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            name="fk_class_group_status_history_changed_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_class_group_status_history"),
    )

    op.create_index(
        "ix_class_group_status_history_class_group_id",
        "class_group_status_history",
        ["class_group_id"],
    )

    op.create_index(
        "ix_class_group_status_history_changed_by_user_id",
        "class_group_status_history",
        ["changed_by_user_id"],
    )

    op.create_index(
        "ix_class_group_status_history_created_at",
        "class_group_status_history",
        ["created_at"],
    )

    op.execute(
        """
        INSERT INTO public.class_group_status_history (
            class_group_id,
            status,
            reason_code,
            reason_note,
            changed_by_user_id
        )
        SELECT
            cg.id,
            CASE WHEN cg.is_active THEN 'active' ELSE 'inactive' END,
            'backfill_current_status',
            'Registro inicial do status atual da turma criado pela migration.',
            NULL
        FROM public.class_groups cg
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_class_group_status_history_created_at",
        table_name="class_group_status_history",
    )
    op.drop_index(
        "ix_class_group_status_history_changed_by_user_id",
        table_name="class_group_status_history",
    )
    op.drop_index(
        "ix_class_group_status_history_class_group_id",
        table_name="class_group_status_history",
    )
    op.drop_table("class_group_status_history")

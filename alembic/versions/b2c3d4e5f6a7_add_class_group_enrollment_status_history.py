"""add class group enrollment status history

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_NAME = "class_group_enrollment_status_history"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "class_group_enrollment_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("reason_note", sa.Text(), nullable=True),
        sa.Column(
            "changed_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_class_group_enrollment_status_history"),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'cancelled')",
            name="ck_cg_enr_status_hist_status",
        ),
        sa.ForeignKeyConstraint(
            ["class_group_enrollment_id"],
            ["class_group_enrollments.id"],
            name="fk_cg_enr_status_hist_enrollment_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            name="fk_cg_enr_status_hist_changed_by_user_id",
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "ix_cg_enr_status_hist_enrollment_id",
        TABLE_NAME,
        ["class_group_enrollment_id"],
    )
    op.create_index(
        "ix_cg_enr_status_hist_changed_by_user_id",
        TABLE_NAME,
        ["changed_by_user_id"],
    )
    op.create_index(
        "ix_cg_enr_status_hist_created_at",
        TABLE_NAME,
        ["created_at"],
    )

    op.execute(
        sa.text(
            """
            insert into class_group_enrollment_status_history (
                class_group_enrollment_id,
                status,
                reason_code,
                reason_note,
                changed_by_user_id,
                created_at
            )
            select
                cge.id,
                cge.status,
                'backfill_current_status',
                'Registro inicial do status atual da matrícula criado pela migration.',
                null,
                now()
            from class_group_enrollments cge
            where cge.status in ('active', 'inactive', 'cancelled')
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_cg_enr_status_hist_created_at", table_name=TABLE_NAME)
    op.drop_index("ix_cg_enr_status_hist_changed_by_user_id", table_name=TABLE_NAME)
    op.drop_index("ix_cg_enr_status_hist_enrollment_id", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)

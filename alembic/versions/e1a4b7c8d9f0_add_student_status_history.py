"""add student status history

Revision ID: e1a4b7c8d9f0
Revises: d4b7a1c9f2e3
Create Date: 2026-03-22 17:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1a4b7c8d9f0"
down_revision: str | Sequence[str] | None = "d4b7a1c9f2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "student_status_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            name="ck_student_status_history_status",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name="fk_student_status_history_student_id_students",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            name="fk_student_status_history_changed_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_student_status_history"),
    )

    op.create_index(
        "ix_student_status_history_student_id",
        "student_status_history",
        ["student_id"],
    )

    op.create_index(
        "ix_student_status_history_changed_by_user_id",
        "student_status_history",
        ["changed_by_user_id"],
    )

    op.create_index(
        "ix_student_status_history_created_at",
        "student_status_history",
        ["created_at"],
    )

    op.execute(
        """
        INSERT INTO public.student_status_history (
            student_id,
            status,
            reason_code,
            reason_note,
            changed_by_user_id
        )
        SELECT
            s.id,
            CASE WHEN s.is_active THEN 'active' ELSE 'inactive' END,
            'backfill_current_status',
            'Registro inicial do status atual do aluno criado pela migration.',
            NULL
        FROM public.students s
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_student_status_history_created_at",
        table_name="student_status_history",
    )
    op.drop_index(
        "ix_student_status_history_changed_by_user_id",
        table_name="student_status_history",
    )
    op.drop_index(
        "ix_student_status_history_student_id",
        table_name="student_status_history",
    )
    op.drop_table("student_status_history")

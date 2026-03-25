"""add court status history

Revision ID: c9d8e7f6a5b4
Revises: b2c3d4e5f6a7
Create Date: 2026-03-24 16:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d8e7f6a5b4"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


STATUS_VALUES = ("active", "inactive")
BACKFILL_REASON_CODE = "backfill_current_status"
BACKFILL_REASON_NOTE = "Registro inicial do status atual da quadra criado pela migration."


def upgrade() -> None:
    op.create_table(
        "court_status_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "court_id",
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
        sa.ForeignKeyConstraint(
            ["court_id"],
            ["courts.id"],
            name="fk_court_status_history_court_id_courts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            name="fk_court_status_history_changed_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_court_status_history_status",
        ),
    )

    op.create_index(
        "ix_court_status_history_court_id",
        "court_status_history",
        ["court_id"],
    )
    op.create_index(
        "ix_court_status_history_changed_by_user_id",
        "court_status_history",
        ["changed_by_user_id"],
    )
    op.create_index(
        "ix_court_status_history_created_at",
        "court_status_history",
        ["created_at"],
    )

    bind = op.get_bind()
    courts = (
        bind.execute(
            sa.text(
                """
            SELECT id, is_active
            FROM public.courts
            """
            )
        )
        .mappings()
        .all()
    )

    if courts:
        bind.execute(
            sa.text(
                """
                INSERT INTO public.court_status_history (
                    id,
                    court_id,
                    status,
                    reason_code,
                    reason_note,
                    changed_by_user_id,
                    created_at
                )
                VALUES (
                    gen_random_uuid(),
                    :court_id,
                    :status,
                    :reason_code,
                    :reason_note,
                    NULL,
                    now()
                )
                """
            ),
            [
                {
                    "court_id": row["id"],
                    "status": "active" if row["is_active"] else "inactive",
                    "reason_code": BACKFILL_REASON_CODE,
                    "reason_note": BACKFILL_REASON_NOTE,
                }
                for row in courts
            ],
        )


def downgrade() -> None:
    op.drop_index(
        "ix_court_status_history_created_at",
        table_name="court_status_history",
    )
    op.drop_index(
        "ix_court_status_history_changed_by_user_id",
        table_name="court_status_history",
    )
    op.drop_index(
        "ix_court_status_history_court_id",
        table_name="court_status_history",
    )
    op.drop_table("court_status_history")

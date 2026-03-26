"""add court rentals table

Revision ID: d8e4c1b7a9f2
Revises: c9d8e7f6a5b4
Create Date: 2026-03-25 08:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8e4c1b7a9f2"
down_revision: str | Sequence[str] | None = "c9d8e7f6a5b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "court_rentals",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.UUID(),
            sa.ForeignKey("events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'requested'"),
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation_email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'scheduled', 'cancelled', 'completed')",
            name="ck_court_rentals_status",
        ),
    )

    op.create_index("ix_court_rentals_user_id", "court_rentals", ["user_id"], unique=False)
    op.create_index("ix_court_rentals_event_id", "court_rentals", ["event_id"], unique=False)
    op.create_index("ix_court_rentals_status", "court_rentals", ["status"], unique=False)
    op.create_index(
        "ix_court_rentals_scheduled_at",
        "court_rentals",
        ["scheduled_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_court_rentals_scheduled_at", table_name="court_rentals")
    op.drop_index("ix_court_rentals_status", table_name="court_rentals")
    op.drop_index("ix_court_rentals_event_id", table_name="court_rentals")
    op.drop_index("ix_court_rentals_user_id", table_name="court_rentals")
    op.drop_table("court_rentals")

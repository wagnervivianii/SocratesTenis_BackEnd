"""add event id to trial lessons

Revision ID: 70cbe0908070
Revises: c1538e2b49af
Create Date: 2026-03-09 23:36:13.048143

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "70cbe0908070"
down_revision: str | Sequence[str] | None = "c1538e2b49af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "trial_lessons",
        sa.Column("event_id", sa.UUID(), nullable=True),
    )

    op.create_index(
        "ix_trial_lessons_event_id",
        "trial_lessons",
        ["event_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_trial_lessons_event_id_events",
        "trial_lessons",
        "events",
        ["event_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "fk_trial_lessons_event_id_events",
        "trial_lessons",
        type_="foreignkey",
    )

    op.drop_index("ix_trial_lessons_event_id", table_name="trial_lessons")

    op.drop_column("trial_lessons", "event_id")

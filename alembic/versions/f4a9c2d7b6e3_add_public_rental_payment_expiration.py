"""add public rental payment expiration controls

Revision ID: f4a9c2d7b6e3
Revises: b1f4d8c9e2a6
Create Date: 2026-03-29 02:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4a9c2d7b6e3"
down_revision: str | Sequence[str] | None = "b1f4d8c9e2a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAYMENT_STATUS_CHECK = (
    "payment_status IN ('not_required', 'pending', 'proof_sent', 'under_review', "
    "'approved', 'rejected', 'expired')"
)


def upgrade() -> None:
    op.add_column(
        "court_rentals",
        sa.Column("payment_expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_court_rentals_payment_expires_at",
        "court_rentals",
        ["payment_expires_at"],
        unique=False,
    )

    op.drop_constraint("ck_court_rentals_payment_status", "court_rentals", type_="check")
    op.create_check_constraint(
        "ck_court_rentals_payment_status",
        "court_rentals",
        PAYMENT_STATUS_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint("ck_court_rentals_payment_status", "court_rentals", type_="check")
    op.create_check_constraint(
        "ck_court_rentals_payment_status",
        "court_rentals",
        "payment_status IN ('not_required', 'pending', 'proof_sent', 'under_review', "
        "'approved', 'rejected')",
    )

    op.drop_index("ix_court_rentals_payment_expires_at", table_name="court_rentals")
    op.drop_column("court_rentals", "payment_expires_at")

"""Split public and admin third-party rental prices.

Revision ID: 8d4f2c1a9b7e
Revises: 7c1a9d4e5b2f
Create Date: 2026-04-06 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "8d4f2c1a9b7e"
down_revision = "7c1a9d4e5b2f"
branch_labels = None
depends_on = None


TABLE = "court_rental_payment_settings"
PUBLIC_COLUMN = "public_third_party_price_per_hour"
ADMIN_COLUMN = "admin_third_party_price_per_hour"
LEGACY_COLUMN = "third_party_price_per_hour"


def upgrade() -> None:
    op.alter_column(
        TABLE,
        LEGACY_COLUMN,
        new_column_name=PUBLIC_COLUMN,
        existing_type=sa.Numeric(10, 2),
        existing_nullable=False,
    )

    op.add_column(
        TABLE,
        sa.Column(ADMIN_COLUMN, sa.Numeric(10, 2), nullable=True),
    )

    op.execute(
        sa.text(
            f"""
            UPDATE public.{TABLE}
            SET {ADMIN_COLUMN} = {PUBLIC_COLUMN}
            WHERE {ADMIN_COLUMN} IS NULL
            """
        )
    )

    op.alter_column(
        TABLE,
        ADMIN_COLUMN,
        existing_type=sa.Numeric(10, 2),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column(TABLE, ADMIN_COLUMN)

    op.alter_column(
        TABLE,
        PUBLIC_COLUMN,
        new_column_name=LEGACY_COLUMN,
        existing_type=sa.Numeric(10, 2),
        existing_nullable=False,
    )

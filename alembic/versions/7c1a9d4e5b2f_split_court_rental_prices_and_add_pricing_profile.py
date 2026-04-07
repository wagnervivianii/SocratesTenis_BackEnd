"""split court rental payment prices and add pricing profile

Revision ID: 7c1a9d4e5b2f
Revises: 6f3a1d2c9b7e
Create Date: 2026-04-06 15:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1a9d4e5b2f"
down_revision: str | Sequence[str] | None = "6f3a1d2c9b7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRICING_PROFILE_CHECK = "pricing_profile IN ('student', 'third_party')"


def upgrade() -> None:
    op.add_column(
        "court_rental_payment_settings",
        sa.Column("student_price_per_hour", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "court_rental_payment_settings",
        sa.Column("third_party_price_per_hour", sa.Numeric(10, 2), nullable=True),
    )

    op.execute(
        """
        UPDATE public.court_rental_payment_settings
           SET student_price_per_hour = default_price_per_hour,
               third_party_price_per_hour = default_price_per_hour
        """
    )

    op.alter_column(
        "court_rental_payment_settings",
        "student_price_per_hour",
        existing_type=sa.Numeric(10, 2),
        nullable=False,
    )
    op.alter_column(
        "court_rental_payment_settings",
        "third_party_price_per_hour",
        existing_type=sa.Numeric(10, 2),
        nullable=False,
    )
    op.drop_column("court_rental_payment_settings", "default_price_per_hour")

    op.add_column(
        "court_rentals",
        sa.Column(
            "pricing_profile",
            sa.Text(),
            nullable=True,
            server_default=sa.text("'third_party'"),
        ),
    )

    op.execute(
        """
        UPDATE public.court_rentals
           SET pricing_profile = CASE
               WHEN customer_student_id IS NOT NULL THEN 'student'
               WHEN origin IN ('student_portal', 'admin_for_student') THEN 'student'
               ELSE 'third_party'
           END
         WHERE pricing_profile IS NULL
        """
    )

    op.alter_column(
        "court_rentals",
        "pricing_profile",
        existing_type=sa.Text(),
        nullable=False,
        server_default=sa.text("'third_party'"),
    )
    op.create_index(
        "ix_court_rentals_pricing_profile",
        "court_rentals",
        ["pricing_profile"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_court_rentals_pricing_profile",
        "court_rentals",
        PRICING_PROFILE_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint("ck_court_rentals_pricing_profile", "court_rentals", type_="check")
    op.drop_index("ix_court_rentals_pricing_profile", table_name="court_rentals")
    op.drop_column("court_rentals", "pricing_profile")

    op.add_column(
        "court_rental_payment_settings",
        sa.Column("default_price_per_hour", sa.Numeric(10, 2), nullable=True),
    )

    op.execute(
        """
        UPDATE public.court_rental_payment_settings
           SET default_price_per_hour = COALESCE(third_party_price_per_hour, student_price_per_hour)
        """
    )

    op.alter_column(
        "court_rental_payment_settings",
        "default_price_per_hour",
        existing_type=sa.Numeric(10, 2),
        nullable=False,
    )
    op.drop_column("court_rental_payment_settings", "third_party_price_per_hour")
    op.drop_column("court_rental_payment_settings", "student_price_per_hour")

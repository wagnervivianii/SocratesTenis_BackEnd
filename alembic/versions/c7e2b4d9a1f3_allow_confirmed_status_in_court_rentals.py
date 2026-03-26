"""Allow confirmed status in court_rentals check constraint

Revision ID: c7e2b4d9a1f3
Revises: ab4d91f6c2e7
Create Date: 2026-03-26 11:05:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c7e2b4d9a1f3"
down_revision = "ab4d91f6c2e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_court_rentals_status", "court_rentals", type_="check")
    op.create_check_constraint(
        "ck_court_rentals_status",
        "court_rentals",
        "status IN ("
        "'requested', "
        "'awaiting_payment', "
        "'awaiting_proof', "
        "'awaiting_admin_review', "
        "'scheduled', "
        "'confirmed', "
        "'completed', "
        "'cancelled', "
        "'rejected'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint("ck_court_rentals_status", "court_rentals", type_="check")
    op.create_check_constraint(
        "ck_court_rentals_status",
        "court_rentals",
        "status IN ("
        "'requested', "
        "'awaiting_payment', "
        "'awaiting_proof', "
        "'awaiting_admin_review', "
        "'scheduled', "
        "'completed', "
        "'cancelled', "
        "'rejected'"
        ")",
    )

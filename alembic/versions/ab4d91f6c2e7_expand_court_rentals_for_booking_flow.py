"""expand court rentals for booking flow

Revision ID: ab4d91f6c2e7
Revises: f2c7a9d4b6e1
Create Date: 2026-03-25 22:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ab4d91f6c2e7"
down_revision: str | Sequence[str] | None = "f2c7a9d4b6e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BOOKING_STATUS_CHECK = (
    "status IN ('requested', 'awaiting_payment', 'awaiting_proof', "
    "'awaiting_admin_review', 'scheduled', 'rejected', 'cancelled', 'completed')"
)

PAYMENT_STATUS_CHECK = (
    "payment_status IN ('not_required', 'pending', 'proof_sent', 'under_review', "
    "'approved', 'rejected')"
)

ORIGIN_CHECK = "origin IN ('public_landing', 'admin_panel', 'student_portal', 'admin_for_student')"


def upgrade() -> None:
    op.drop_constraint("ck_court_rentals_status", "court_rentals", type_="check")

    op.alter_column("court_rentals", "user_id", existing_type=sa.UUID(), nullable=True)

    op.add_column(
        "court_rentals",
        sa.Column(
            "origin",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'public_landing'"),
        ),
    )
    op.add_column(
        "court_rentals",
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("customer_user_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("customer_student_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("customer_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("customer_email", sa.Text(), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("customer_whatsapp", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column(
            "payment_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'not_required'"),
        ),
    )
    op.add_column(
        "court_rentals",
        sa.Column("price_per_hour", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("pix_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("pix_qr_code_payload", sa.Text(), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("payment_proof_submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("payment_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("payment_reviewed_by_user_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("payment_amount_matches_expected", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("payment_received_amount", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "court_rentals",
        sa.Column("payment_review_notes", sa.Text(), nullable=True),
    )

    op.execute(
        """
        UPDATE court_rentals
           SET created_by_user_id = user_id,
               customer_user_id = user_id
         WHERE user_id IS NOT NULL
        """
    )

    op.create_foreign_key(
        "fk_court_rentals_created_by_user_id_users",
        "court_rentals",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_court_rentals_customer_user_id_users",
        "court_rentals",
        "users",
        ["customer_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_court_rentals_customer_student_id_students",
        "court_rentals",
        "students",
        ["customer_student_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_court_rentals_payment_reviewed_by_user_id_users",
        "court_rentals",
        "users",
        ["payment_reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_court_rentals_origin", "court_rentals", ["origin"], unique=False)
    op.create_index(
        "ix_court_rentals_created_by_user_id",
        "court_rentals",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_court_rentals_customer_user_id",
        "court_rentals",
        ["customer_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_court_rentals_customer_student_id",
        "court_rentals",
        ["customer_student_id"],
        unique=False,
    )
    op.create_index(
        "ix_court_rentals_payment_status",
        "court_rentals",
        ["payment_status"],
        unique=False,
    )
    op.create_index(
        "ix_court_rentals_payment_reviewed_by_user_id",
        "court_rentals",
        ["payment_reviewed_by_user_id"],
        unique=False,
    )

    op.create_check_constraint(
        "ck_court_rentals_status",
        "court_rentals",
        BOOKING_STATUS_CHECK,
    )
    op.create_check_constraint(
        "ck_court_rentals_payment_status",
        "court_rentals",
        PAYMENT_STATUS_CHECK,
    )
    op.create_check_constraint(
        "ck_court_rentals_origin",
        "court_rentals",
        ORIGIN_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint("ck_court_rentals_origin", "court_rentals", type_="check")
    op.drop_constraint("ck_court_rentals_payment_status", "court_rentals", type_="check")
    op.drop_constraint("ck_court_rentals_status", "court_rentals", type_="check")

    op.drop_index("ix_court_rentals_payment_reviewed_by_user_id", table_name="court_rentals")
    op.drop_index("ix_court_rentals_payment_status", table_name="court_rentals")
    op.drop_index("ix_court_rentals_customer_student_id", table_name="court_rentals")
    op.drop_index("ix_court_rentals_customer_user_id", table_name="court_rentals")
    op.drop_index("ix_court_rentals_created_by_user_id", table_name="court_rentals")
    op.drop_index("ix_court_rentals_origin", table_name="court_rentals")

    op.drop_constraint(
        "fk_court_rentals_payment_reviewed_by_user_id_users",
        "court_rentals",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_court_rentals_customer_student_id_students",
        "court_rentals",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_court_rentals_customer_user_id_users",
        "court_rentals",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_court_rentals_created_by_user_id_users",
        "court_rentals",
        type_="foreignkey",
    )

    op.drop_column("court_rentals", "payment_review_notes")
    op.drop_column("court_rentals", "payment_received_amount")
    op.drop_column("court_rentals", "payment_amount_matches_expected")
    op.drop_column("court_rentals", "payment_reviewed_by_user_id")
    op.drop_column("court_rentals", "payment_reviewed_at")
    op.drop_column("court_rentals", "payment_proof_submitted_at")
    op.drop_column("court_rentals", "confirmed_at")
    op.drop_column("court_rentals", "pix_qr_code_payload")
    op.drop_column("court_rentals", "pix_key")
    op.drop_column("court_rentals", "total_amount")
    op.drop_column("court_rentals", "price_per_hour")
    op.drop_column("court_rentals", "payment_status")
    op.drop_column("court_rentals", "customer_whatsapp")
    op.drop_column("court_rentals", "customer_email")
    op.drop_column("court_rentals", "customer_name")
    op.drop_column("court_rentals", "customer_student_id")
    op.drop_column("court_rentals", "customer_user_id")
    op.drop_column("court_rentals", "created_by_user_id")
    op.drop_column("court_rentals", "origin")

    op.alter_column("court_rentals", "user_id", existing_type=sa.UUID(), nullable=False)

    op.create_check_constraint(
        "ck_court_rentals_status",
        "court_rentals",
        "status IN ('requested', 'scheduled', 'cancelled', 'completed')",
    )

"""Add court rental business fields for evidence, outcome, and rebooking.

Revision ID: 9e2c4b7a1d3f
Revises: 8d4f2c1a9b7e
Create Date: 2026-04-07 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "9e2c4b7a1d3f"
down_revision = "8d4f2c1a9b7e"
branch_labels = None
depends_on = None


TABLE = "court_rentals"

BILLING_MODE_VALUES = ("single_pix", "monthly_invoice")
EVIDENCE_STATUS_VALUES = (
    "pending",
    "customer_uploaded",
    "admin_uploaded",
    "not_sent",
    "not_applicable",
)
OUTCOME_STATUS_VALUES = ("pending", "ok", "issue")
OUTCOME_ISSUE_VALUES = (
    "payment_problem",
    "no_show",
    "bad_behavior",
    "property_damage",
    "late_arrival_or_early_leave",
    "other",
)


def _create_check_constraint(
    name: str, column_name: str, values: tuple[str, ...], *, nullable: bool
) -> None:
    quoted = ", ".join(f"'{value}'" for value in values)
    expression = f"{column_name} IN ({quoted})"
    if nullable:
        expression = f"{column_name} IS NULL OR ({expression})"
    op.create_check_constraint(name, TABLE, expression)


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "billing_mode",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'single_pix'"),
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "payment_evidence_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column(TABLE, sa.Column("payment_evidence_notes", sa.Text(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column("payment_evidence_recorded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "payment_evidence_recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "outcome_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column(TABLE, sa.Column("outcome_issue_type", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("outcome_notes", sa.Text(), nullable=True))
    op.add_column(
        TABLE, sa.Column("outcome_recorded_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        TABLE,
        sa.Column("outcome_recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(TABLE, sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        TABLE,
        sa.Column("deactivated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(TABLE, sa.Column("deactivation_reason", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("reactivated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        TABLE,
        sa.Column("reactivated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(TABLE, sa.Column("reactivation_reason", sa.Text(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column("rescheduled_from_rental_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column("rescheduled_to_rental_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(TABLE, sa.Column("rescheduled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        TABLE,
        sa.Column("rescheduled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(TABLE, sa.Column("reschedule_reason", sa.Text(), nullable=True))

    op.create_index(
        "ix_court_rentals_payment_evidence_recorded_by_user_id",
        TABLE,
        ["payment_evidence_recorded_by_user_id"],
    )
    op.create_index(
        "ix_court_rentals_outcome_recorded_by_user_id", TABLE, ["outcome_recorded_by_user_id"]
    )
    op.create_index("ix_court_rentals_deactivated_by_user_id", TABLE, ["deactivated_by_user_id"])
    op.create_index("ix_court_rentals_reactivated_by_user_id", TABLE, ["reactivated_by_user_id"])
    op.create_index(
        "ix_court_rentals_rescheduled_from_rental_id", TABLE, ["rescheduled_from_rental_id"]
    )
    op.create_index(
        "ix_court_rentals_rescheduled_to_rental_id", TABLE, ["rescheduled_to_rental_id"]
    )
    op.create_index("ix_court_rentals_rescheduled_by_user_id", TABLE, ["rescheduled_by_user_id"])

    op.create_foreign_key(
        "fk_court_rentals_payment_evidence_recorded_by_user_id",
        TABLE,
        "users",
        ["payment_evidence_recorded_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_court_rentals_outcome_recorded_by_user_id",
        TABLE,
        "users",
        ["outcome_recorded_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_court_rentals_deactivated_by_user_id",
        TABLE,
        "users",
        ["deactivated_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_court_rentals_reactivated_by_user_id",
        TABLE,
        "users",
        ["reactivated_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_court_rentals_rescheduled_from_rental_id",
        TABLE,
        TABLE,
        ["rescheduled_from_rental_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_court_rentals_rescheduled_to_rental_id",
        TABLE,
        TABLE,
        ["rescheduled_to_rental_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_court_rentals_rescheduled_by_user_id",
        TABLE,
        "users",
        ["rescheduled_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _create_check_constraint(
        "ck_court_rentals_billing_mode",
        "billing_mode",
        BILLING_MODE_VALUES,
        nullable=False,
    )
    _create_check_constraint(
        "ck_court_rentals_payment_evidence_status",
        "payment_evidence_status",
        EVIDENCE_STATUS_VALUES,
        nullable=False,
    )
    _create_check_constraint(
        "ck_court_rentals_outcome_status",
        "outcome_status",
        OUTCOME_STATUS_VALUES,
        nullable=False,
    )
    _create_check_constraint(
        "ck_court_rentals_outcome_issue_type",
        "outcome_issue_type",
        OUTCOME_ISSUE_VALUES,
        nullable=True,
    )

    op.execute(
        sa.text(
            """
            UPDATE public.court_rentals
            SET billing_mode = 'single_pix'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE public.court_rentals
            SET payment_evidence_status = CASE
              WHEN payment_status = 'not_required' THEN 'not_applicable'
              WHEN payment_proof_submitted_at IS NOT NULL THEN 'customer_uploaded'
              WHEN payment_status IN ('proof_sent', 'under_review', 'approved', 'rejected') THEN 'customer_uploaded'
              ELSE 'pending'
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE public.court_rentals
            SET payment_evidence_recorded_at = payment_proof_submitted_at
            WHERE payment_proof_submitted_at IS NOT NULL
              AND payment_evidence_recorded_at IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE public.court_rentals
            SET deactivated_at = cancelled_at
            WHERE status = 'cancelled'
              AND cancelled_at IS NOT NULL
              AND deactivated_at IS NULL
            """
        )
    )

    op.alter_column(TABLE, "billing_mode", server_default=None)
    op.alter_column(TABLE, "payment_evidence_status", server_default=None)
    op.alter_column(TABLE, "outcome_status", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_court_rentals_outcome_issue_type", TABLE, type_="check")
    op.drop_constraint("ck_court_rentals_outcome_status", TABLE, type_="check")
    op.drop_constraint("ck_court_rentals_payment_evidence_status", TABLE, type_="check")
    op.drop_constraint("ck_court_rentals_billing_mode", TABLE, type_="check")

    op.drop_constraint("fk_court_rentals_rescheduled_by_user_id", TABLE, type_="foreignkey")
    op.drop_constraint("fk_court_rentals_rescheduled_to_rental_id", TABLE, type_="foreignkey")
    op.drop_constraint("fk_court_rentals_rescheduled_from_rental_id", TABLE, type_="foreignkey")
    op.drop_constraint("fk_court_rentals_reactivated_by_user_id", TABLE, type_="foreignkey")
    op.drop_constraint("fk_court_rentals_deactivated_by_user_id", TABLE, type_="foreignkey")
    op.drop_constraint("fk_court_rentals_outcome_recorded_by_user_id", TABLE, type_="foreignkey")
    op.drop_constraint(
        "fk_court_rentals_payment_evidence_recorded_by_user_id",
        TABLE,
        type_="foreignkey",
    )

    op.drop_index("ix_court_rentals_rescheduled_by_user_id", table_name=TABLE)
    op.drop_index("ix_court_rentals_rescheduled_to_rental_id", table_name=TABLE)
    op.drop_index("ix_court_rentals_rescheduled_from_rental_id", table_name=TABLE)
    op.drop_index("ix_court_rentals_reactivated_by_user_id", table_name=TABLE)
    op.drop_index("ix_court_rentals_deactivated_by_user_id", table_name=TABLE)
    op.drop_index("ix_court_rentals_outcome_recorded_by_user_id", table_name=TABLE)
    op.drop_index("ix_court_rentals_payment_evidence_recorded_by_user_id", table_name=TABLE)

    op.drop_column(TABLE, "reschedule_reason")
    op.drop_column(TABLE, "rescheduled_by_user_id")
    op.drop_column(TABLE, "rescheduled_at")
    op.drop_column(TABLE, "rescheduled_to_rental_id")
    op.drop_column(TABLE, "rescheduled_from_rental_id")
    op.drop_column(TABLE, "reactivation_reason")
    op.drop_column(TABLE, "reactivated_by_user_id")
    op.drop_column(TABLE, "reactivated_at")
    op.drop_column(TABLE, "deactivation_reason")
    op.drop_column(TABLE, "deactivated_by_user_id")
    op.drop_column(TABLE, "deactivated_at")
    op.drop_column(TABLE, "outcome_recorded_by_user_id")
    op.drop_column(TABLE, "outcome_recorded_at")
    op.drop_column(TABLE, "outcome_notes")
    op.drop_column(TABLE, "outcome_issue_type")
    op.drop_column(TABLE, "outcome_status")
    op.drop_column(TABLE, "payment_evidence_recorded_by_user_id")
    op.drop_column(TABLE, "payment_evidence_recorded_at")
    op.drop_column(TABLE, "payment_evidence_notes")
    op.drop_column(TABLE, "payment_evidence_status")
    op.drop_column(TABLE, "billing_mode")

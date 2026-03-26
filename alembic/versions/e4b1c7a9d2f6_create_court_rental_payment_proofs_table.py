"""Create court_rental_payment_proofs table

Revision ID: e4b1c7a9d2f6
Revises: c7e2b4d9a1f3
Create Date: 2026-03-27 09:10:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "e4b1c7a9d2f6"
down_revision = "c7e2b4d9a1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "court_rental_payment_proofs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "court_rental_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("court_rentals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("original_file_name", sa.Text(), nullable=False),
        sa.Column("stored_file_name", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_court_rental_payment_proofs_court_rental_id",
        "court_rental_payment_proofs",
        ["court_rental_id"],
    )
    op.create_index(
        "ix_court_rental_payment_proofs_uploaded_by_user_id",
        "court_rental_payment_proofs",
        ["uploaded_by_user_id"],
    )
    op.create_index(
        "ix_court_rental_payment_proofs_created_at",
        "court_rental_payment_proofs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_court_rental_payment_proofs_created_at",
        table_name="court_rental_payment_proofs",
    )
    op.drop_index(
        "ix_court_rental_payment_proofs_uploaded_by_user_id",
        table_name="court_rental_payment_proofs",
    )
    op.drop_index(
        "ix_court_rental_payment_proofs_court_rental_id",
        table_name="court_rental_payment_proofs",
    )
    op.drop_table("court_rental_payment_proofs")

"""Create global court rental payment settings table

Revision ID: b1f4d8c9e2a6
Revises: e4b1c7a9d2f6
Create Date: 2026-03-27 10:20:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b1f4d8c9e2a6"
down_revision = "e4b1c7a9d2f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "court_rental_payment_settings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "name", sa.Text(), nullable=False, server_default=sa.text("'Configuração principal'")
        ),
        sa.Column("pix_key", sa.Text(), nullable=False),
        sa.Column(
            "merchant_name", sa.Text(), nullable=False, server_default=sa.text("'SOCRATES TENIS'")
        ),
        sa.Column(
            "merchant_city", sa.Text(), nullable=False, server_default=sa.text("'SAO PAULO'")
        ),
        sa.Column("default_price_per_hour", sa.Numeric(10, 2), nullable=False),
        sa.Column("proof_whatsapp", sa.Text(), nullable=True),
        sa.Column("payment_instructions", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_court_rental_payment_settings_created_by_user_id",
        "court_rental_payment_settings",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_court_rental_payment_settings_updated_by_user_id",
        "court_rental_payment_settings",
        ["updated_by_user_id"],
    )
    op.create_index(
        "ix_court_rental_payment_settings_created_at",
        "court_rental_payment_settings",
        ["created_at"],
    )
    op.create_index(
        "ix_court_rental_payment_settings_updated_at",
        "court_rental_payment_settings",
        ["updated_at"],
    )
    op.create_index(
        "uq_court_rental_payment_settings_single_active",
        "court_rental_payment_settings",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_court_rental_payment_settings_single_active",
        table_name="court_rental_payment_settings",
    )
    op.drop_index(
        "ix_court_rental_payment_settings_updated_at",
        table_name="court_rental_payment_settings",
    )
    op.drop_index(
        "ix_court_rental_payment_settings_created_at",
        table_name="court_rental_payment_settings",
    )
    op.drop_index(
        "ix_court_rental_payment_settings_updated_by_user_id",
        table_name="court_rental_payment_settings",
    )
    op.drop_index(
        "ix_court_rental_payment_settings_created_by_user_id",
        table_name="court_rental_payment_settings",
    )
    op.drop_table("court_rental_payment_settings")

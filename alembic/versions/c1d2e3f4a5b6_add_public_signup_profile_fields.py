"""add public signup profile fields

Revision ID: c1d2e3f4a5b6
Revises: f1e2d3c4b5a6
Create Date: 2026-04-02 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "f1e2d3c4b5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("zip_code", sa.String(length=8), nullable=True))
    op.add_column("users", sa.Column("guardian_full_name", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("guardian_whatsapp", sa.String(length=11), nullable=True))
    op.add_column("users", sa.Column("guardian_relationship", sa.String(length=40), nullable=True))

    op.create_index("ix_users_zip_code", "users", ["zip_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_zip_code", table_name="users")

    op.drop_column("users", "guardian_relationship")
    op.drop_column("users", "guardian_whatsapp")
    op.drop_column("users", "guardian_full_name")
    op.drop_column("users", "zip_code")
    op.drop_column("users", "birth_date")

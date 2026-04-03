"""make users.password_hash nullable for google auth

Revision ID: f1e2d3c4b5a6
Revises: a4f9c2d1e7b6
Create Date: 2026-03-31 23:10:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "f1e2d3c4b5a6"
down_revision = "a4f9c2d1e7b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE users
            SET password_hash = :placeholder_hash
            WHERE password_hash IS NULL
            """
        ),
        {
            "placeholder_hash": "__google_auth_placeholder_password_hash__",
        },
    )

    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.Text(),
        nullable=False,
    )

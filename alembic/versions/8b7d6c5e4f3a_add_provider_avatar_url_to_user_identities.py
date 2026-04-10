"""add provider avatar url to user identities

Revision ID: 8b7d6c5e4f3a
Revises: 7a2c4d9e1f0b
Create Date: 2026-04-10 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "8b7d6c5e4f3a"
down_revision = "7a2c4d9e1f0b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_identities",
        sa.Column("provider_avatar_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_identities", "provider_avatar_url")

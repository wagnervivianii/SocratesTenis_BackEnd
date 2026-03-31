"""add password reset tokens

Revision ID: a4f9c2d1e7b6
Revises: 9c2d4f1a7b3e
Create Date: 2026-03-30 18:20:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "a4f9c2d1e7b6"
down_revision = "9c2d4f1a7b3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
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
        "ix_password_reset_tokens_user_id",
        "password_reset_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_password_reset_tokens_expires_at",
        "password_reset_tokens",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_reset_tokens_expires_at",
        table_name="password_reset_tokens",
    )
    op.drop_index(
        "ix_password_reset_tokens_token_hash",
        table_name="password_reset_tokens",
    )
    op.drop_index(
        "ix_password_reset_tokens_user_id",
        table_name="password_reset_tokens",
    )
    op.drop_table("password_reset_tokens")

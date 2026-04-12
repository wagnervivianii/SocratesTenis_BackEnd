"""add profile fields to student signup requests

Revision ID: ae12f4c9d8b3
Revises: 9b1e4c7d2f6a
Create Date: 2026-04-11 12:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ae12f4c9d8b3"
down_revision: str | Sequence[str] | None = "9b1e4c7d2f6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "student_signup_requests",
        sa.Column("profession", sa.Text(), nullable=True),
    )
    op.add_column(
        "student_signup_requests",
        sa.Column(
            "share_profession",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "student_signup_requests",
        sa.Column(
            "share_instagram",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("student_signup_requests", "share_instagram")
    op.drop_column("student_signup_requests", "share_profession")
    op.drop_column("student_signup_requests", "profession")

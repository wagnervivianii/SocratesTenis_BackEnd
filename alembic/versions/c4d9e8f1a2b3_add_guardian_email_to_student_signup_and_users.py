"""add guardian email to student signup requests and users

Revision ID: c4d9e8f1a2b3
Revises: ae12f4c9d8b3
Create Date: 2026-04-11 23:59:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d9e8f1a2b3"
down_revision: str | None = "ae12f4c9d8b3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "student_signup_requests",
        sa.Column("guardian_email", sa.Text(), nullable=True),
        schema="public",
    )
    op.add_column(
        "users",
        sa.Column("guardian_email", sa.Text(), nullable=True),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("users", "guardian_email", schema="public")
    op.drop_column("student_signup_requests", "guardian_email", schema="public")

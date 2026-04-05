"""allow student role in users

Revision ID: 6f3a1d2c9b7e
Revises: 2a9f6d4c1b8e
Create Date: 2026-04-05 11:15:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f3a1d2c9b7e"
down_revision: str | None = "2a9f6d4c1b8e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("users_role_check", "users", type_="check")
    op.create_check_constraint(
        "users_role_check",
        "users",
        "role IN ('admin', 'coach', 'staff', 'student', 'aluno')",
    )


def downgrade() -> None:
    op.drop_constraint("users_role_check", "users", type_="check")
    op.create_check_constraint(
        "users_role_check",
        "users",
        "role IN ('admin', 'coach', 'staff')",
    )

"""allow rescheduled occurrence type

Revision ID: 5ceb9531e651
Revises: 93b123574dd9
Create Date: 2026-03-10 22:30:58.545302

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "5ceb9531e651"
down_revision: str | Sequence[str] | None = "93b123574dd9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

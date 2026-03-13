"""set uuid defaults on scheduling tables

Revision ID: 9a369a4237e1
Revises: bfd1d227e7d3
Create Date: 2026-03-11 23:31:58.100568

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a369a4237e1"
down_revision: str | Sequence[str] | None = "bfd1d227e7d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "class_groups",
        "id",
        existing_type=sa.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )

    op.alter_column(
        "class_group_enrollments",
        "id",
        existing_type=sa.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )

    op.alter_column(
        "class_group_schedules",
        "id",
        existing_type=sa.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )

    op.alter_column(
        "bookable_slots",
        "id",
        existing_type=sa.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "bookable_slots",
        "id",
        existing_type=sa.UUID(),
        server_default=None,
        existing_nullable=False,
    )

    op.alter_column(
        "class_group_schedules",
        "id",
        existing_type=sa.UUID(),
        server_default=None,
        existing_nullable=False,
    )

    op.alter_column(
        "class_group_enrollments",
        "id",
        existing_type=sa.UUID(),
        server_default=None,
        existing_nullable=False,
    )

    op.alter_column(
        "class_groups",
        "id",
        existing_type=sa.UUID(),
        server_default=None,
        existing_nullable=False,
    )

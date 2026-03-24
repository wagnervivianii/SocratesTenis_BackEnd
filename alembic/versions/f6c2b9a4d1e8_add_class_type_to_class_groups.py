"""add class type to class groups

Revision ID: f6c2b9a4d1e8
Revises: e1a4b7c8d9f0
Create Date: 2026-03-23 21:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6c2b9a4d1e8"
down_revision: str | Sequence[str] | None = "e1a4b7c8d9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "class_groups",
        sa.Column(
            "class_type",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'group'"),
        ),
    )

    op.create_check_constraint(
        "ck_class_groups_class_type",
        "class_groups",
        "class_type IN ('individual', 'group')",
    )

    op.create_index(
        "ix_class_groups_class_type",
        "class_groups",
        ["class_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_class_groups_class_type",
        table_name="class_groups",
    )

    op.drop_constraint(
        "ck_class_groups_class_type",
        "class_groups",
        type_="check",
    )

    op.drop_column("class_groups", "class_type")

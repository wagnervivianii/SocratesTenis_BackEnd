"""add court metadata fields

Revision ID: f2c7a9d4b6e1
Revises: d8e4c1b7a9f2
Create Date: 2026-03-25 10:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2c7a9d4b6e1"
down_revision: str | Sequence[str] | None = "d8e4c1b7a9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SURFACE_VALUES = ("saibro", "rapida", "cimento", "grama", "outro")
COVER_VALUES = ("descoberta", "coberta", "semi_coberta")


def upgrade() -> None:
    op.add_column("courts", sa.Column("surface_type", sa.Text(), nullable=True))
    op.add_column("courts", sa.Column("cover_type", sa.Text(), nullable=True))
    op.add_column("courts", sa.Column("image_url", sa.Text(), nullable=True))
    op.add_column("courts", sa.Column("short_description", sa.Text(), nullable=True))

    op.create_check_constraint(
        "ck_courts_surface_type",
        "courts",
        "surface_type IS NULL OR surface_type IN ('saibro', 'rapida', 'cimento', 'grama', 'outro')",
    )
    op.create_check_constraint(
        "ck_courts_cover_type",
        "courts",
        "cover_type IS NULL OR cover_type IN ('descoberta', 'coberta', 'semi_coberta')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_courts_cover_type", "courts", type_="check")
    op.drop_constraint("ck_courts_surface_type", "courts", type_="check")

    op.drop_column("courts", "short_description")
    op.drop_column("courts", "image_url")
    op.drop_column("courts", "cover_type")
    op.drop_column("courts", "surface_type")

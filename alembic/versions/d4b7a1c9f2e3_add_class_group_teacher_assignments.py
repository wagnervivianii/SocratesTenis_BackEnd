"""add class group teacher assignments

Revision ID: d4b7a1c9f2e3
Revises: c3d9e4f1a2b6
Create Date: 2026-03-19 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4b7a1c9f2e3"
down_revision: str | Sequence[str] | None = "c3d9e4f1a2b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "class_group_teacher_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("class_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "ends_on IS NULL OR ends_on >= starts_on",
            name="ck_class_group_teacher_assignments_date_range",
        ),
        sa.ForeignKeyConstraint(
            ["class_group_id"],
            ["class_groups.id"],
            name="fk_class_group_teacher_assignments_class_group_id_class_groups",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["teachers.id"],
            name="fk_class_group_teacher_assignments_teacher_id_teachers",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_class_group_teacher_assignments"),
        sa.UniqueConstraint(
            "class_group_id",
            "teacher_id",
            "starts_on",
            name="uq_class_group_teacher_assignments_group_teacher_start",
        ),
    )

    op.create_index(
        "ix_class_group_teacher_assignments_class_group_id",
        "class_group_teacher_assignments",
        ["class_group_id"],
    )

    op.create_index(
        "ix_class_group_teacher_assignments_teacher_id",
        "class_group_teacher_assignments",
        ["teacher_id"],
    )

    op.create_index(
        "ix_class_group_teacher_assignments_is_active",
        "class_group_teacher_assignments",
        ["is_active"],
    )

    op.create_index(
        "ix_class_group_teacher_assignments_lookup",
        "class_group_teacher_assignments",
        ["class_group_id", "is_active", "starts_on", "ends_on"],
    )

    op.execute(
        """
        INSERT INTO public.class_group_teacher_assignments (
            class_group_id,
            teacher_id,
            starts_on,
            ends_on,
            is_active,
            notes
        )
        SELECT
            cg.id AS class_group_id,
            cg.teacher_id AS teacher_id,
            CURRENT_DATE AS starts_on,
            NULL AS ends_on,
            cg.is_active AS is_active,
            'Backfill inicial a partir de class_groups.teacher_id' AS notes
        FROM public.class_groups cg
        WHERE cg.teacher_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_class_group_teacher_assignments_lookup",
        table_name="class_group_teacher_assignments",
    )

    op.drop_index(
        "ix_class_group_teacher_assignments_is_active",
        table_name="class_group_teacher_assignments",
    )

    op.drop_index(
        "ix_class_group_teacher_assignments_teacher_id",
        table_name="class_group_teacher_assignments",
    )

    op.drop_index(
        "ix_class_group_teacher_assignments_class_group_id",
        table_name="class_group_teacher_assignments",
    )

    op.drop_table("class_group_teacher_assignments")

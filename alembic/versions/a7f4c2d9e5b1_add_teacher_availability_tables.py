"""add teacher availability tables

Revision ID: a7f4c2d9e5b1
Revises: 1d7f6e8c3b21
Create Date: 2026-03-17 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7f4c2d9e5b1"
down_revision: str | Sequence[str] | None = "1d7f6e8c3b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teacher_availability_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("modality", sa.Text(), nullable=True),
        sa.Column("court_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            "weekday BETWEEN 1 AND 7",
            name="ck_teacher_availability_rules_weekday",
        ),
        sa.CheckConstraint(
            "end_time > start_time",
            name="ck_teacher_availability_rules_time_range",
        ),
        sa.CheckConstraint(
            "ends_on IS NULL OR ends_on >= starts_on",
            name="ck_teacher_availability_rules_date_range",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["teachers.id"],
            name="fk_teacher_availability_rules_teacher_id_teachers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["court_id"],
            ["courts.id"],
            name="fk_teacher_availability_rules_court_id_courts",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teacher_availability_rules"),
    )
    op.create_index(
        "ix_teacher_availability_rules_teacher_id",
        "teacher_availability_rules",
        ["teacher_id"],
    )
    op.create_index(
        "ix_teacher_availability_rules_court_id",
        "teacher_availability_rules",
        ["court_id"],
    )
    op.create_index(
        "ix_teacher_availability_rules_is_active",
        "teacher_availability_rules",
        ["is_active"],
    )
    op.create_index(
        "ix_teacher_availability_rules_lookup",
        "teacher_availability_rules",
        ["weekday", "is_active", "starts_on", "ends_on"],
    )

    op.create_table(
        "teacher_availability_exceptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exception_type", sa.Text(), nullable=False),
        sa.Column("modality", sa.Text(), nullable=True),
        sa.Column("court_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("reason", sa.Text(), nullable=True),
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
            "end_at > start_at",
            name="ck_teacher_availability_exceptions_time_range",
        ),
        sa.CheckConstraint(
            "exception_type IN ('blocked', 'available_extra')",
            name="ck_teacher_availability_exceptions_type",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["teachers.id"],
            name="fk_teacher_availability_exceptions_teacher_id_teachers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["court_id"],
            ["courts.id"],
            name="fk_teacher_availability_exceptions_court_id_courts",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teacher_availability_exceptions"),
    )
    op.create_index(
        "ix_teacher_availability_exceptions_teacher_id",
        "teacher_availability_exceptions",
        ["teacher_id"],
    )
    op.create_index(
        "ix_teacher_availability_exceptions_court_id",
        "teacher_availability_exceptions",
        ["court_id"],
    )
    op.create_index(
        "ix_teacher_availability_exceptions_is_active",
        "teacher_availability_exceptions",
        ["is_active"],
    )
    op.create_index(
        "ix_teacher_availability_exceptions_time_range",
        "teacher_availability_exceptions",
        ["start_at", "end_at"],
    )

    op.execute(
        """
        CREATE TRIGGER trg_teacher_availability_rules_updated_at
        BEFORE UPDATE ON public.teacher_availability_rules
        FOR EACH ROW
        EXECUTE FUNCTION public.set_updated_at();
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_teacher_availability_exceptions_updated_at
        BEFORE UPDATE ON public.teacher_availability_exceptions
        FOR EACH ROW
        EXECUTE FUNCTION public.set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_teacher_availability_exceptions_updated_at
        ON public.teacher_availability_exceptions;
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_teacher_availability_rules_updated_at
        ON public.teacher_availability_rules;
        """
    )

    op.drop_index(
        "ix_teacher_availability_exceptions_time_range",
        table_name="teacher_availability_exceptions",
    )
    op.drop_index(
        "ix_teacher_availability_exceptions_is_active",
        table_name="teacher_availability_exceptions",
    )
    op.drop_index(
        "ix_teacher_availability_exceptions_court_id",
        table_name="teacher_availability_exceptions",
    )
    op.drop_index(
        "ix_teacher_availability_exceptions_teacher_id",
        table_name="teacher_availability_exceptions",
    )
    op.drop_table("teacher_availability_exceptions")

    op.drop_index(
        "ix_teacher_availability_rules_lookup",
        table_name="teacher_availability_rules",
    )
    op.drop_index(
        "ix_teacher_availability_rules_is_active",
        table_name="teacher_availability_rules",
    )
    op.drop_index(
        "ix_teacher_availability_rules_court_id",
        table_name="teacher_availability_rules",
    )
    op.drop_index(
        "ix_teacher_availability_rules_teacher_id",
        table_name="teacher_availability_rules",
    )
    op.drop_table("teacher_availability_rules")

"""add class groups and bookable slots

Revision ID: bfd1d227e7d3
Revises: 5ceb9531e651
Create Date: 2026-03-11 15:00:43.163320

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bfd1d227e7d3"
down_revision: str | Sequence[str] | None = "5ceb9531e651"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "class_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("court_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default=sa.text("4")),
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
        sa.CheckConstraint("capacity > 0", name="ck_class_groups_capacity_positive"),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["teachers.id"],
            name="fk_class_groups_teacher_id_teachers",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["court_id"],
            ["courts.id"],
            name="fk_class_groups_court_id_courts",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_class_groups"),
    )
    op.create_index("ix_class_groups_teacher_id", "class_groups", ["teacher_id"])
    op.create_index("ix_class_groups_court_id", "class_groups", ["court_id"])
    op.create_index("ix_class_groups_is_active", "class_groups", ["is_active"])

    op.create_table(
        "class_group_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("class_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column(
            "starts_on",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
        sa.Column("ends_on", sa.Date(), nullable=True),
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
            name="ck_class_group_enrollments_date_range",
        ),
        sa.ForeignKeyConstraint(
            ["class_group_id"],
            ["class_groups.id"],
            name="fk_class_group_enrollments_class_group_id_class_groups",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name="fk_class_group_enrollments_student_id_students",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_class_group_enrollments"),
        sa.UniqueConstraint(
            "class_group_id",
            "student_id",
            "starts_on",
            name="uq_class_group_enrollments_group_student_start",
        ),
    )
    op.create_index(
        "ix_class_group_enrollments_class_group_id",
        "class_group_enrollments",
        ["class_group_id"],
    )
    op.create_index(
        "ix_class_group_enrollments_student_id",
        "class_group_enrollments",
        ["student_id"],
    )
    op.create_index(
        "ix_class_group_enrollments_status",
        "class_group_enrollments",
        ["status"],
    )

    op.create_table(
        "class_group_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("class_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
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
        sa.CheckConstraint("weekday BETWEEN 1 AND 7", name="ck_class_group_schedules_weekday"),
        sa.CheckConstraint("end_time > start_time", name="ck_class_group_schedules_time_range"),
        sa.CheckConstraint(
            "ends_on IS NULL OR ends_on >= starts_on",
            name="ck_class_group_schedules_date_range",
        ),
        sa.ForeignKeyConstraint(
            ["class_group_id"],
            ["class_groups.id"],
            name="fk_class_group_schedules_class_group_id_class_groups",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_class_group_schedules"),
        sa.UniqueConstraint(
            "class_group_id",
            "weekday",
            "start_time",
            "end_time",
            "starts_on",
            name="uq_class_group_schedules_group_weekday_time_start",
        ),
    )
    op.create_index(
        "ix_class_group_schedules_class_group_id",
        "class_group_schedules",
        ["class_group_id"],
    )
    op.create_index(
        "ix_class_group_schedules_lookup",
        "class_group_schedules",
        ["weekday", "is_active", "starts_on", "ends_on"],
    )

    op.create_table(
        "bookable_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("modality", sa.Text(), nullable=False),
        sa.Column("court_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("slot_capacity", sa.Integer(), nullable=False, server_default=sa.text("1")),
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
        sa.CheckConstraint("weekday BETWEEN 1 AND 7", name="ck_bookable_slots_weekday"),
        sa.CheckConstraint("end_time > start_time", name="ck_bookable_slots_time_range"),
        sa.CheckConstraint("slot_capacity > 0", name="ck_bookable_slots_capacity_positive"),
        sa.CheckConstraint(
            "ends_on IS NULL OR ends_on >= starts_on",
            name="ck_bookable_slots_date_range",
        ),
        sa.ForeignKeyConstraint(
            ["court_id"],
            ["courts.id"],
            name="fk_bookable_slots_court_id_courts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["teachers.id"],
            name="fk_bookable_slots_teacher_id_teachers",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bookable_slots"),
    )
    op.create_index("ix_bookable_slots_court_id", "bookable_slots", ["court_id"])
    op.create_index("ix_bookable_slots_teacher_id", "bookable_slots", ["teacher_id"])
    op.create_index(
        "ix_bookable_slots_lookup",
        "bookable_slots",
        ["modality", "weekday", "is_active", "starts_on", "ends_on"],
    )

    op.add_column(
        "events",
        sa.Column("class_group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_events_class_group_id_class_groups",
        "events",
        "class_groups",
        ["class_group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_events_class_group_id", "events", ["class_group_id"])


def downgrade() -> None:
    op.drop_index("ix_events_class_group_id", table_name="events")
    op.drop_constraint("fk_events_class_group_id_class_groups", "events", type_="foreignkey")
    op.drop_column("events", "class_group_id")

    op.drop_index("ix_bookable_slots_lookup", table_name="bookable_slots")
    op.drop_index("ix_bookable_slots_teacher_id", table_name="bookable_slots")
    op.drop_index("ix_bookable_slots_court_id", table_name="bookable_slots")
    op.drop_table("bookable_slots")

    op.drop_index("ix_class_group_schedules_lookup", table_name="class_group_schedules")
    op.drop_index("ix_class_group_schedules_class_group_id", table_name="class_group_schedules")
    op.drop_table("class_group_schedules")

    op.drop_index("ix_class_group_enrollments_status", table_name="class_group_enrollments")
    op.drop_index("ix_class_group_enrollments_student_id", table_name="class_group_enrollments")
    op.drop_index(
        "ix_class_group_enrollments_class_group_id",
        table_name="class_group_enrollments",
    )
    op.drop_table("class_group_enrollments")

    op.drop_index("ix_class_groups_is_active", table_name="class_groups")
    op.drop_index("ix_class_groups_court_id", table_name="class_groups")
    op.drop_index("ix_class_groups_teacher_id", table_name="class_groups")
    op.drop_table("class_groups")

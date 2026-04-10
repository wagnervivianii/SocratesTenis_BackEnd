"""add teacher event reports

Revision ID: 3c5d7e9f1a2b
Revises: 9e2c4b7a1d3f, 2a9f6d4c1b8e
Create Date: 2026-04-09 18:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c5d7e9f1a2b"
down_revision: str | Sequence[str] | None = ("9e2c4b7a1d3f", "2a9f6d4c1b8e")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REPORTS_TABLE = "teacher_event_reports"
ABSENCES_TABLE = "teacher_event_report_absences"


def upgrade() -> None:
    op.create_table(
        REPORTS_TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("report_status", sa.Text(), nullable=False),
        sa.Column("issue_type", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_teacher_event_reports"),
        sa.UniqueConstraint("event_id", name="uq_teacher_event_reports_event_id"),
        sa.CheckConstraint(
            "report_status IN ('completed', 'issue')",
            name="ck_teacher_event_reports_report_status",
        ),
        sa.CheckConstraint(
            "issue_type IS NULL OR issue_type IN ('student_absence', 'class_not_held', 'operational_problem', 'other')",
            name="ck_teacher_event_reports_issue_type",
        ),
        sa.CheckConstraint(
            "(report_status = 'completed' AND issue_type IS NULL) OR "
            "(report_status = 'issue' AND issue_type IS NOT NULL)",
            name="ck_teacher_event_reports_status_issue_type_match",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name="fk_teacher_event_reports_event_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["teachers.id"],
            name="fk_teacher_event_reports_teacher_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_teacher_event_reports_created_by_user_id",
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "ix_teacher_event_reports_event_id",
        REPORTS_TABLE,
        ["event_id"],
    )
    op.create_index(
        "ix_teacher_event_reports_teacher_id",
        REPORTS_TABLE,
        ["teacher_id"],
    )
    op.create_index(
        "ix_teacher_event_reports_created_at",
        REPORTS_TABLE,
        ["created_at"],
    )

    op.create_table(
        ABSENCES_TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "teacher_event_report_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teacher_event_report_absences"),
        sa.UniqueConstraint(
            "teacher_event_report_id",
            "student_id",
            name="uq_teacher_event_report_absences_report_student",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_event_report_id"],
            [f"{REPORTS_TABLE}.id"],
            name="fk_teacher_event_report_absences_report_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name="fk_teacher_event_report_absences_student_id",
            ondelete="RESTRICT",
        ),
    )

    op.create_index(
        "ix_teacher_event_report_absences_report_id",
        ABSENCES_TABLE,
        ["teacher_event_report_id"],
    )
    op.create_index(
        "ix_teacher_event_report_absences_student_id",
        ABSENCES_TABLE,
        ["student_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_teacher_event_report_absences_student_id", table_name=ABSENCES_TABLE)
    op.drop_index("ix_teacher_event_report_absences_report_id", table_name=ABSENCES_TABLE)
    op.drop_table(ABSENCES_TABLE)

    op.drop_index("ix_teacher_event_reports_created_at", table_name=REPORTS_TABLE)
    op.drop_index("ix_teacher_event_reports_teacher_id", table_name=REPORTS_TABLE)
    op.drop_index("ix_teacher_event_reports_event_id", table_name=REPORTS_TABLE)
    op.drop_table(REPORTS_TABLE)

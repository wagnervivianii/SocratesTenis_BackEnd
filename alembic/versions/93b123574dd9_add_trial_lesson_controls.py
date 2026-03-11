"""add trial lesson controls

Revision ID: 93b123574dd9
Revises: 70cbe0908070
Create Date: 2026-03-10 21:47:24.656411

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "93b123574dd9"
down_revision: str | Sequence[str] | None = "70cbe0908070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trial_lesson_controls",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("whatsapp", sa.String(length=11), nullable=True),
        sa.Column(
            "requires_admin_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_blocked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "late_cancellations",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "no_show_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_cancellations",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_occurrence_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "(email IS NOT NULL) OR (whatsapp IS NOT NULL)",
            name="ck_trial_lesson_controls_email_or_whatsapp",
        ),
        sa.UniqueConstraint("email", name="uq_trial_lesson_controls_email"),
        sa.UniqueConstraint("whatsapp", name="uq_trial_lesson_controls_whatsapp"),
    )

    op.create_index(
        "ix_trial_lesson_controls_requires_admin_approval",
        "trial_lesson_controls",
        ["requires_admin_approval"],
        unique=False,
    )

    op.create_index(
        "ix_trial_lesson_controls_is_blocked",
        "trial_lesson_controls",
        ["is_blocked"],
        unique=False,
    )

    op.create_table(
        "trial_lesson_occurrences",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "trial_lesson_id",
            sa.UUID(),
            sa.ForeignKey("trial_lessons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("whatsapp", sa.String(length=11), nullable=True),
        sa.Column("occurrence_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "occurrence_type IN ('cancelled', 'cancelled_late', 'no_show', 'admin_approved', 'blocked')",
            name="ck_trial_lesson_occurrences_type",
        ),
    )

    op.create_index(
        "ix_trial_lesson_occurrences_user_id",
        "trial_lesson_occurrences",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "ix_trial_lesson_occurrences_trial_lesson_id",
        "trial_lesson_occurrences",
        ["trial_lesson_id"],
        unique=False,
    )

    op.create_index(
        "ix_trial_lesson_occurrences_email",
        "trial_lesson_occurrences",
        ["email"],
        unique=False,
    )

    op.create_index(
        "ix_trial_lesson_occurrences_whatsapp",
        "trial_lesson_occurrences",
        ["whatsapp"],
        unique=False,
    )

    op.create_index(
        "ix_trial_lesson_occurrences_occurrence_type",
        "trial_lesson_occurrences",
        ["occurrence_type"],
        unique=False,
    )

    op.create_index(
        "ix_trial_lesson_occurrences_created_at",
        "trial_lesson_occurrences",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trial_lesson_occurrences_created_at",
        table_name="trial_lesson_occurrences",
    )
    op.drop_index(
        "ix_trial_lesson_occurrences_occurrence_type",
        table_name="trial_lesson_occurrences",
    )
    op.drop_index(
        "ix_trial_lesson_occurrences_whatsapp",
        table_name="trial_lesson_occurrences",
    )
    op.drop_index(
        "ix_trial_lesson_occurrences_email",
        table_name="trial_lesson_occurrences",
    )
    op.drop_index(
        "ix_trial_lesson_occurrences_trial_lesson_id",
        table_name="trial_lesson_occurrences",
    )
    op.drop_index(
        "ix_trial_lesson_occurrences_user_id",
        table_name="trial_lesson_occurrences",
    )
    op.drop_table("trial_lesson_occurrences")

    op.drop_index(
        "ix_trial_lesson_controls_is_blocked",
        table_name="trial_lesson_controls",
    )
    op.drop_index(
        "ix_trial_lesson_controls_requires_admin_approval",
        table_name="trial_lesson_controls",
    )
    op.drop_table("trial_lesson_controls")

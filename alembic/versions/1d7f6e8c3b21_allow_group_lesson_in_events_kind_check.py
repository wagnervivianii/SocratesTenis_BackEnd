"""allow group_lesson in events kind check

Revision ID: 1d7f6e8c3b21
Revises: 9a369a4237e1
Create Date: 2026-03-13 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1d7f6e8c3b21"
down_revision: str | Sequence[str] | None = "9a369a4237e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("events_kind_check", "events", type_="check")
    op.create_check_constraint(
        "events_kind_check",
        "events",
        (
            "kind = ANY (ARRAY["
            "'aula_regular'::text, "
            "'primeira_aula'::text, "
            "'group_lesson'::text, "
            "'locacao'::text, "
            "'bloqueio'::text])"
        ),
    )


def downgrade() -> None:
    op.drop_constraint("events_kind_check", "events", type_="check")
    op.create_check_constraint(
        "events_kind_check",
        "events",
        (
            "kind = ANY (ARRAY["
            "'aula_regular'::text, "
            "'primeira_aula'::text, "
            "'locacao'::text, "
            "'bloqueio'::text])"
        ),
    )

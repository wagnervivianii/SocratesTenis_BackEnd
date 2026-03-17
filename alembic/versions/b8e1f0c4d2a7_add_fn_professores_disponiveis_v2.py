"""add fn_professores_disponiveis_v2

Revision ID: b8e1f0c4d2a7
Revises: a7f4c2d9e5b1
Create Date: 2026-03-17 11:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8e1f0c4d2a7"
down_revision: str | Sequence[str] | None = "a7f4c2d9e5b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.fn_professores_disponiveis_v2(
            p_from timestamptz,
            p_to timestamptz,
            p_modality text DEFAULT NULL,
            p_court_id uuid DEFAULT NULL
        )
        RETURNS TABLE (
            teacher_id uuid,
            full_name text
        )
        LANGUAGE sql
        STABLE
        AS $$
        WITH active_teachers AS (
            SELECT
                t.id,
                t.full_name
            FROM public.teachers t
            WHERE t.is_active = true
        ),
        rule_matches AS (
            SELECT DISTINCT
                r.teacher_id
            FROM public.teacher_availability_rules r
            WHERE r.is_active = true
              AND r.weekday = EXTRACT(ISODOW FROM (p_from AT TIME ZONE 'America/Sao_Paulo'))::smallint
              AND (p_from AT TIME ZONE 'America/Sao_Paulo')::date >= r.starts_on
              AND (
                    r.ends_on IS NULL
                    OR (p_to AT TIME ZONE 'America/Sao_Paulo')::date <= r.ends_on
                  )
              AND r.start_time <= (p_from AT TIME ZONE 'America/Sao_Paulo')::time
              AND r.end_time >= (p_to AT TIME ZONE 'America/Sao_Paulo')::time
              AND (
                    p_modality IS NULL
                    OR r.modality IS NULL
                    OR r.modality = p_modality
                  )
              AND (
                    p_court_id IS NULL
                    OR r.court_id IS NULL
                    OR r.court_id = p_court_id
                  )
        ),
        extra_available AS (
            SELECT DISTINCT
                e.teacher_id
            FROM public.teacher_availability_exceptions e
            WHERE e.is_active = true
              AND e.exception_type = 'available_extra'
              AND e.start_at <= p_from
              AND e.end_at >= p_to
              AND (
                    p_modality IS NULL
                    OR e.modality IS NULL
                    OR e.modality = p_modality
                  )
              AND (
                    p_court_id IS NULL
                    OR e.court_id IS NULL
                    OR e.court_id = p_court_id
                  )
        ),
        blocked_by_exception AS (
            SELECT DISTINCT
                e.teacher_id
            FROM public.teacher_availability_exceptions e
            WHERE e.is_active = true
              AND e.exception_type = 'blocked'
              AND e.start_at < p_to
              AND e.end_at > p_from
              AND (
                    p_modality IS NULL
                    OR e.modality IS NULL
                    OR e.modality = p_modality
                  )
              AND (
                    p_court_id IS NULL
                    OR e.court_id IS NULL
                    OR e.court_id = p_court_id
                  )
        ),
        blocked_by_event AS (
            SELECT DISTINCT
                ev.teacher_id
            FROM public.events ev
            WHERE ev.teacher_id IS NOT NULL
              AND COALESCE(ev.status, '') NOT IN ('cancelled', 'canceled')
              AND ev.start_at < p_to
              AND ev.end_at > p_from
        )
        SELECT
            t.id AS teacher_id,
            t.full_name
        FROM active_teachers t
        WHERE (
                t.id IN (SELECT teacher_id FROM rule_matches)
                OR t.id IN (SELECT teacher_id FROM extra_available)
              )
          AND t.id NOT IN (SELECT teacher_id FROM blocked_by_exception)
          AND t.id NOT IN (SELECT teacher_id FROM blocked_by_event)
        ORDER BY t.full_name;
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP FUNCTION IF EXISTS public.fn_professores_disponiveis_v2(
            timestamptz,
            timestamptz,
            text,
            uuid
        );
        """
    )

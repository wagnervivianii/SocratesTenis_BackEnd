from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.agenda import AgendaItemOut

router = APIRouter()


ADMIN_AGENDA_OVERVIEW_SELECT = """
WITH group_students AS (
  SELECT
    cge.class_group_id,
    array_agg(DISTINCT s.full_name ORDER BY s.full_name)
      FILTER (WHERE s.full_name IS NOT NULL) AS class_group_student_names
  FROM public.class_group_enrollments cge
  JOIN public.students s
    ON s.id = cge.student_id
  WHERE COALESCE(cge.status, 'active') = 'active'
  GROUP BY cge.class_group_id
)
SELECT
  e.id AS event_id,
  e.kind,
  e.status,
  e.start_at,
  e.end_at,
  e.notes,
  c.id AS court_id,
  c.name AS court_name,
  t.id AS teacher_id,
  t.full_name AS teacher_name,
  s.id AS student_id,
  s.full_name AS student_name,
  creator.id AS created_by_user_id,
  creator.email AS created_by_email,
  e.created_at,
  e.updated_at,
  cg.id AS class_group_id,
  cg.name AS class_group_name,
  gs.class_group_student_names,
  cr.id AS court_rental_id,
  cr.origin AS court_rental_origin,
  cr.pricing_profile AS court_rental_pricing_profile,
  cr.payment_status AS court_rental_payment_status,
  cr.customer_name,
  cr.customer_email,
  cr.customer_whatsapp,
  tl.id AS trial_lesson_id,
  trial_user.id AS trial_user_id,
  COALESCE(trial_user.full_name, cr.customer_name, s.full_name) AS trial_user_name,
  trial_user.email AS trial_user_email,
  trial_user.whatsapp AS trial_user_whatsapp,
  CASE
    WHEN e.kind = 'primeira_aula' THEN 'trial'
    WHEN e.kind = 'locacao' THEN 'rental'
    WHEN e.kind = 'group_lesson' THEN 'group_lesson'
    WHEN e.student_id IS NOT NULL THEN 'student_lesson'
    ELSE 'other'
  END AS event_group,
  CASE
    WHEN e.kind = 'primeira_aula' THEN 'Aula grátis'
    WHEN e.kind = 'locacao' THEN 'Locação'
    WHEN e.kind = 'group_lesson' THEN 'Turma'
    WHEN e.student_id IS NOT NULL THEN 'Aula'
    ELSE 'Evento'
  END AS event_label,
  CASE
    WHEN e.kind = 'primeira_aula' THEN 'green'
    WHEN e.kind = 'locacao' THEN 'red'
    WHEN e.kind = 'group_lesson' THEN 'yellow'
    WHEN e.student_id IS NOT NULL THEN 'yellow'
    ELSE 'gray'
  END AS color_key,
  CASE
    WHEN cg.id IS NOT NULL THEN cg.name
    WHEN e.kind = 'locacao' THEN COALESCE(cr.customer_name, s.full_name)
    WHEN e.kind = 'primeira_aula' THEN COALESCE(trial_user.full_name, s.full_name, cr.customer_name)
    ELSE s.full_name
  END AS participant_label,
  (e.class_group_id IS NOT NULL) AS is_recurring
FROM public.events e
JOIN public.courts c
  ON c.id = e.court_id
LEFT JOIN public.teachers t
  ON t.id = e.teacher_id
LEFT JOIN public.students s
  ON s.id = e.student_id
LEFT JOIN public.users creator
  ON creator.id = e.created_by
LEFT JOIN public.class_groups cg
  ON cg.id = e.class_group_id
LEFT JOIN group_students gs
  ON gs.class_group_id = e.class_group_id
LEFT JOIN public.court_rentals cr
  ON cr.event_id = e.id
LEFT JOIN public.trial_lessons tl
  ON tl.event_id = e.id
LEFT JOIN public.users trial_user
  ON trial_user.id = tl.user_id
"""


ADMIN_AGENDA_OVERVIEW_ORDER_BY = """
ORDER BY
  e.start_at,
  c.name,
  COALESCE(t.full_name, ''),
  COALESCE(
    CASE
      WHEN cg.id IS NOT NULL THEN cg.name
      WHEN e.kind = 'locacao' THEN COALESCE(cr.customer_name, s.full_name)
      WHEN e.kind = 'primeira_aula' THEN COALESCE(trial_user.full_name, s.full_name, cr.customer_name)
      ELSE s.full_name
    END,
    ''
  )
"""


def _get_current_user_row(db: Session, user_id: str):
    return (
        db.execute(
            text(
                """
                SELECT id, email, role, is_active
                FROM public.users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        .mappings()
        .first()
    )


def _require_admin(db: Session, user_id: str) -> None:
    user = _get_current_user_row(db, user_id)
    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário inválido",
        )

    if not str(user["role"]).startswith("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem visualizar a visão geral da agenda.",
        )


def _validate_range(from_: datetime, to: datetime, *, max_days: int) -> None:
    if from_ >= to:
        raise HTTPException(status_code=422, detail="'from' precisa ser menor que 'to'")

    if (to - from_).days > max_days:
        raise HTTPException(
            status_code=422,
            detail=f"Intervalo máximo: {max_days} dias",
        )


def _build_admin_overview_query(
    *,
    from_: datetime,
    to: datetime,
    status_value: str | None,
    kind_value: str | None,
    court_id: UUID | None,
    teacher_id: UUID | None,
    event_group: str | None,
    only_recurring: bool | None,
) -> tuple[str, dict[str, object]]:
    where_clauses = [
        "e.start_at < :p_to",
        "e.end_at > :p_from",
    ]
    params: dict[str, object] = {
        "p_from": from_,
        "p_to": to,
    }

    if status_value is not None:
        where_clauses.append("e.status = :p_status")
        params["p_status"] = status_value

    if kind_value is not None:
        where_clauses.append("e.kind = :p_kind")
        params["p_kind"] = kind_value

    if court_id is not None:
        where_clauses.append("e.court_id = :p_court")
        params["p_court"] = court_id

    if teacher_id is not None:
        where_clauses.append("e.teacher_id = :p_teacher")
        params["p_teacher"] = teacher_id

    if event_group is not None:
        where_clauses.append(
            """
            CASE
              WHEN e.kind = 'primeira_aula' THEN 'trial'
              WHEN e.kind = 'locacao' THEN 'rental'
              WHEN e.kind = 'group_lesson' THEN 'group_lesson'
              WHEN e.student_id IS NOT NULL THEN 'student_lesson'
              ELSE 'other'
            END = :p_event_group
            """
        )
        params["p_event_group"] = event_group

    if only_recurring is not None:
        where_clauses.append("(e.class_group_id IS NOT NULL) = :p_only_recurring")
        params["p_only_recurring"] = only_recurring

    sql = f"""
    {ADMIN_AGENDA_OVERVIEW_SELECT}
    WHERE {" AND ".join(where_clauses)}
    {ADMIN_AGENDA_OVERVIEW_ORDER_BY}
    """

    return sql, params


@router.get("/", response_model=list[AgendaItemOut])
def listar_agenda(
    from_: Annotated[datetime, Query(alias="from")],
    to: Annotated[datetime, Query()],
    status: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    court_id: Annotated[UUID | None, Query()] = None,
    teacher_id: Annotated[UUID | None, Query()] = None,
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    _user_id: Annotated[str, Depends(get_current_user_id)] = "",  # type: ignore[assignment]
):
    _validate_range(from_, to, max_days=31)

    sql = text(
        """
        SELECT * FROM public.fn_agenda_periodo(
          :p_from,
          :p_to,
          :p_status,
          :p_kind,
          :p_court,
          :p_teacher
        )
        """
    )

    rows = (
        db.execute(
            sql,
            {
                "p_from": from_,
                "p_to": to,
                "p_status": status,
                "p_kind": kind,
                "p_court": court_id,
                "p_teacher": teacher_id,
            },
        )
        .mappings()
        .all()
    )

    return rows


@router.get("/admin-overview", response_model=list[AgendaItemOut])
def listar_agenda_admin_overview(
    from_: Annotated[datetime, Query(alias="from")],
    to: Annotated[datetime, Query()],
    status: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    court_id: Annotated[UUID | None, Query()] = None,
    teacher_id: Annotated[UUID | None, Query()] = None,
    event_group: Annotated[str | None, Query()] = None,
    only_recurring: Annotated[bool | None, Query()] = None,
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    user_id: Annotated[str, Depends(get_current_user_id)] = "",  # type: ignore[assignment]
):
    _require_admin(db, user_id)
    _validate_range(from_, to, max_days=62)

    sql, params = _build_admin_overview_query(
        from_=from_,
        to=to,
        status_value=status,
        kind_value=kind,
        court_id=court_id,
        teacher_id=teacher_id,
        event_group=event_group,
        only_recurring=only_recurring,
    )

    rows = db.execute(text(sql), params).mappings().all()

    return rows

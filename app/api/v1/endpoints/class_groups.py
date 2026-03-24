from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.class_groups import (
    ClassGroupCreateIn,
    ClassGroupEnrollmentCreateIn,
    ClassGroupEnrollmentListItemOut,
    ClassGroupEnrollmentOut,
    ClassGroupEnrollmentUpdateIn,
    ClassGroupListItemOut,
    ClassGroupOut,
    ClassGroupScheduleCreateIn,
    ClassGroupScheduleOut,
    ClassGroupScheduleUpdateIn,
    ClassGroupStatusChangeIn,
    ClassGroupStatusHistoryItemOut,
    ClassGroupUpdateIn,
)

router = APIRouter(prefix="/class-groups")


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

    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem gerenciar turmas.",
        )


def _validate_class_group_payload(payload: ClassGroupCreateIn | ClassGroupUpdateIn) -> None:
    capacity = getattr(payload, "capacity", None)
    if capacity is not None and capacity <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="capacity precisa ser maior que zero",
        )


def _validate_schedule_payload(
    payload: ClassGroupScheduleCreateIn | ClassGroupScheduleUpdateIn,
) -> None:
    start_time = getattr(payload, "start_time", None)
    end_time = getattr(payload, "end_time", None)
    starts_on = getattr(payload, "starts_on", None)
    ends_on = getattr(payload, "ends_on", None)

    if start_time is not None and end_time is not None and end_time <= start_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_time precisa ser maior que start_time",
        )

    if starts_on is not None and ends_on is not None and ends_on < starts_on:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ends_on não pode ser menor que starts_on",
        )


def _validate_enrollment_payload(
    payload: ClassGroupEnrollmentCreateIn | ClassGroupEnrollmentUpdateIn,
) -> None:
    starts_on = getattr(payload, "starts_on", None)
    ends_on = getattr(payload, "ends_on", None)

    if starts_on is not None and ends_on is not None and ends_on < starts_on:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ends_on não pode ser menor que starts_on",
        )


def _validate_status_change_payload(
    payload: ClassGroupStatusChangeIn | None,
) -> tuple[str | None, str | None]:
    if payload is None:
        return None, None

    reason_code = payload.reason_code.strip() if payload.reason_code else None
    reason_note = payload.reason_note.strip() if payload.reason_note else None

    if reason_code == "other" and not reason_note:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Informe o motivo complementar quando o motivo for 'other'.",
        )

    return reason_code, reason_note


def _insert_class_group_status_history(
    db: Session,
    *,
    group_id: UUID,
    status_value: str,
    changed_by_user_id: str,
    reason_code: str | None = None,
    reason_note: str | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO public.class_group_status_history (
              class_group_id,
              status,
              reason_code,
              reason_note,
              changed_by_user_id
            )
            VALUES (
              :class_group_id,
              :status,
              :reason_code,
              :reason_note,
              :changed_by_user_id
            )
            """
        ),
        {
            "class_group_id": group_id,
            "status": status_value,
            "reason_code": reason_code,
            "reason_note": reason_note,
            "changed_by_user_id": changed_by_user_id,
        },
    )


def _integrity_to_http(e: IntegrityError) -> HTTPException:
    orig = getattr(e, "orig", None)
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)

    constraint = None
    diag = getattr(orig, "diag", None)
    if diag is not None:
        constraint = getattr(diag, "constraint_name", None)

    if pgcode == "23P01":
        if constraint == "ex_events_no_overlap_court":
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Conflito: a quadra já está ocupada nesse horário.",
            )

        if constraint == "ex_events_no_overlap_teacher":
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Conflito: o professor já está ocupado nesse horário.",
            )

        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflito: horário indisponível (sobreposição).",
        )

    if pgcode == "23503":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Referência inválida para relacionamento informado.",
        )

    if pgcode == "23505":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um registro igual para os mesmos parâmetros.",
        )

    if pgcode == "23514":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Violação de regra de validação do banco.",
        )

    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Erro ao salvar dados da turma: {str(orig) if orig else str(e)}",
    )


def _local_tz() -> ZoneInfo:
    return ZoneInfo("America/Sao_Paulo")


def _group_lesson_window() -> tuple[datetime, datetime, date, date]:
    tz = _local_tz()
    window_start = datetime.now(tz)
    window_end = window_start + timedelta(days=60)
    return window_start, window_end, window_start.date(), window_end.date()


def _iter_schedule_occurrences(
    *,
    weekday: int,
    starts_on: date,
    ends_on: date | None,
    window_start_date: date,
    window_end_date: date,
):
    effective_start = max(starts_on, window_start_date)
    effective_end = min(ends_on or window_end_date, window_end_date)

    if effective_start > effective_end:
        return

    offset = (weekday - effective_start.isoweekday()) % 7
    current = effective_start + timedelta(days=offset)

    while current <= effective_end:
        yield current
        current += timedelta(days=7)


def _resolve_group_teacher_id_for_date(
    db: Session,
    *,
    group_id: UUID,
    target_date: date,
) -> UUID | None:
    assignment = (
        db.execute(
            text(
                """
                SELECT
                  teacher_id
                FROM public.class_group_teacher_assignments
                WHERE class_group_id = :group_id
                  AND is_active = TRUE
                  AND starts_on <= :target_date
                  AND (
                    ends_on IS NULL
                    OR ends_on >= :target_date
                  )
                ORDER BY
                  starts_on DESC,
                  created_at DESC,
                  id DESC
                LIMIT 1
                """
            ),
            {
                "group_id": group_id,
                "target_date": target_date,
            },
        )
        .mappings()
        .first()
    )

    if assignment:
        return assignment["teacher_id"]

    legacy = (
        db.execute(
            text(
                """
                SELECT teacher_id
                FROM public.class_groups
                WHERE id = :group_id
                """
            ),
            {"group_id": group_id},
        )
        .mappings()
        .first()
    )

    if legacy:
        return legacy["teacher_id"]

    return None


def _sync_group_teacher_assignments_from_legacy_teacher_id(
    db: Session,
    *,
    group_id: UUID,
    teacher_id: UUID | None,
) -> None:
    if teacher_id is None:
        return

    today = datetime.now(_local_tz()).date()
    yesterday = today - timedelta(days=1)

    current_assignment = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  teacher_id,
                  starts_on,
                  ends_on
                FROM public.class_group_teacher_assignments
                WHERE class_group_id = :group_id
                  AND is_active = TRUE
                  AND starts_on <= :today
                  AND (
                    ends_on IS NULL
                    OR ends_on >= :today
                  )
                ORDER BY
                  starts_on DESC,
                  created_at DESC,
                  id DESC
                LIMIT 1
                """
            ),
            {
                "group_id": group_id,
                "today": today,
            },
        )
        .mappings()
        .first()
    )

    if current_assignment and current_assignment["teacher_id"] == teacher_id:
        return

    db.execute(
        text(
            """
            DELETE FROM public.class_group_teacher_assignments
            WHERE class_group_id = :group_id
              AND is_active = TRUE
              AND starts_on >= :today
            """
        ),
        {
            "group_id": group_id,
            "today": today,
        },
    )

    db.execute(
        text(
            """
            UPDATE public.class_group_teacher_assignments
            SET
              ends_on = :yesterday,
              is_active = FALSE,
              updated_at = now()
            WHERE class_group_id = :group_id
              AND is_active = TRUE
              AND starts_on < :today
              AND (
                ends_on IS NULL
                OR ends_on >= :today
              )
            """
        ),
        {
            "group_id": group_id,
            "today": today,
            "yesterday": yesterday,
        },
    )

    db.execute(
        text(
            """
            INSERT INTO public.class_group_teacher_assignments (
              class_group_id,
              teacher_id,
              starts_on,
              ends_on,
              is_active,
              notes
            )
            VALUES (
              :group_id,
              :teacher_id,
              :today,
              NULL,
              TRUE,
              'Sincronizado automaticamente a partir de class_groups.teacher_id'
            )
            """
        ),
        {
            "group_id": group_id,
            "teacher_id": teacher_id,
            "today": today,
        },
    )


def _sync_group_lesson_events(db: Session, group_id: UUID, user_id: str) -> None:
    window_start, window_end, window_start_date, window_end_date = _group_lesson_window()
    tz = _local_tz()

    db.execute(
        text(
            """
            DELETE FROM public.events
            WHERE class_group_id = :group_id
              AND kind = 'group_lesson'
              AND start_at >= :window_start
              AND start_at <= :window_end
            """
        ),
        {
            "group_id": group_id,
            "window_start": window_start,
            "window_end": window_end,
        },
    )

    group = _get_class_group_or_404(db, group_id)

    if not group["is_active"]:
        return

    if group["court_id"] is None:
        return

    schedules = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  class_group_id,
                  weekday,
                  start_time,
                  end_time,
                  starts_on,
                  ends_on,
                  is_active,
                  notes
                FROM public.class_group_schedules
                WHERE class_group_id = :group_id
                  AND is_active = TRUE
                  AND starts_on <= :window_end_date
                  AND (
                    ends_on IS NULL
                    OR ends_on >= :window_start_date
                  )
                ORDER BY
                  weekday,
                  start_time,
                  starts_on,
                  id
                """
            ),
            {
                "group_id": group_id,
                "window_start_date": window_start_date,
                "window_end_date": window_end_date,
            },
        )
        .mappings()
        .all()
    )

    if not schedules:
        return

    created_by_uuid = UUID(user_id)

    for schedule in schedules:
        event_notes = schedule["notes"] if schedule["notes"] is not None else group["notes"]

        for occurrence_date in _iter_schedule_occurrences(
            weekday=int(schedule["weekday"]),
            starts_on=schedule["starts_on"],
            ends_on=schedule["ends_on"],
            window_start_date=window_start_date,
            window_end_date=window_end_date,
        ):
            start_at = datetime.combine(occurrence_date, schedule["start_time"], tzinfo=tz)
            end_at = datetime.combine(occurrence_date, schedule["end_time"], tzinfo=tz)

            if start_at < window_start or start_at > window_end:
                continue

            teacher_id = _resolve_group_teacher_id_for_date(
                db,
                group_id=group_id,
                target_date=occurrence_date,
            )

            if teacher_id is None:
                continue

            db.execute(
                text(
                    """
                    INSERT INTO public.events (
                      court_id,
                      teacher_id,
                      student_id,
                      created_by,
                      class_group_id,
                      kind,
                      status,
                      start_at,
                      end_at,
                      notes
                    )
                    VALUES (
                      :court_id,
                      :teacher_id,
                      NULL,
                      :created_by,
                      :class_group_id,
                      'group_lesson',
                      'confirmado',
                      :start_at,
                      :end_at,
                      :notes
                    )
                    """
                ),
                {
                    "court_id": group["court_id"],
                    "teacher_id": teacher_id,
                    "created_by": created_by_uuid,
                    "class_group_id": group_id,
                    "start_at": start_at,
                    "end_at": end_at,
                    "notes": event_notes,
                },
            )


def _get_class_group_or_404(db: Session, group_id: UUID):
    row = (
        db.execute(
            text(
                """
                SELECT
                  cg.id,
                  cg.name,
                  cg.class_type,
                  cg.level,
                  cg.teacher_id,
                  t.full_name AS teacher_name,
                  cg.court_id,
                  c.name AS court_name,
                  cg.capacity,
                  cg.is_active,
                  cg.notes,
                  cg.created_at,
                  cg.updated_at
                FROM public.class_groups cg
                LEFT JOIN public.teachers t
                  ON t.id = cg.teacher_id
                LEFT JOIN public.courts c
                  ON c.id = cg.court_id
                WHERE cg.id = :group_id
                """
            ),
            {"group_id": group_id},
        )
        .mappings()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turma não encontrada.",
        )

    return row


def _get_class_group_schedule_or_404(db: Session, group_id: UUID, schedule_id: UUID):
    row = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  class_group_id,
                  weekday,
                  start_time,
                  end_time,
                  starts_on,
                  ends_on,
                  is_active,
                  notes,
                  created_at,
                  updated_at
                FROM public.class_group_schedules
                WHERE id = :schedule_id
                  AND class_group_id = :group_id
                """
            ),
            {"schedule_id": schedule_id, "group_id": group_id},
        )
        .mappings()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Horário da turma não encontrado.",
        )

    return row


def _get_class_group_enrollment_or_404(db: Session, group_id: UUID, enrollment_id: UUID):
    row = (
        db.execute(
            text(
                """
                SELECT
                  e.id,
                  e.class_group_id,
                  e.student_id,
                  s.full_name AS student_name,
                  s.email AS student_email,
                  s.phone AS student_phone,
                  e.status,
                  e.starts_on,
                  e.ends_on,
                  e.created_at,
                  e.updated_at
                FROM public.class_group_enrollments e
                JOIN public.students s
                  ON s.id = e.student_id
                WHERE e.id = :enrollment_id
                  AND e.class_group_id = :group_id
                """
            ),
            {"enrollment_id": enrollment_id, "group_id": group_id},
        )
        .mappings()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matrícula da turma não encontrada.",
        )

    return row


@router.get("/", response_model=list[ClassGroupListItemOut])
def list_class_groups(
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
    class_type: Annotated[str | None, Query()] = None,
    level: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    teacher_id: Annotated[UUID | None, Query()] = None,
    court_id: Annotated[UUID | None, Query()] = None,
):
    where_clauses = []
    params: dict[str, object] = {}

    if class_type is not None:
        where_clauses.append("cg.class_type = :class_type")
        params["class_type"] = class_type

    if level is not None:
        where_clauses.append("cg.level = :level")
        params["level"] = level

    if is_active is not None:
        where_clauses.append("cg.is_active = :is_active")
        params["is_active"] = is_active

    if teacher_id is not None:
        where_clauses.append("cg.teacher_id = :teacher_id")
        params["teacher_id"] = teacher_id

    if court_id is not None:
        where_clauses.append("cg.court_id = :court_id")
        params["court_id"] = court_id

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    sql = text(
        f"""
        SELECT
          cg.id,
          cg.name,
          cg.class_type,
          cg.level,
          cg.teacher_id,
          t.full_name AS teacher_name,
          cg.court_id,
          c.name AS court_name,
          cg.capacity,
          cg.is_active,
          cg.notes,
          cg.created_at,
          cg.updated_at
        FROM public.class_groups cg
        LEFT JOIN public.teachers t
          ON t.id = cg.teacher_id
        LEFT JOIN public.courts c
          ON c.id = cg.court_id
        {where_sql}
        ORDER BY
          cg.is_active DESC,
          cg.name
        """
    )

    rows = db.execute(sql, params).mappings().all()
    return rows


@router.get("/{group_id}", response_model=ClassGroupListItemOut)
def get_class_group(
    group_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    return _get_class_group_or_404(db, group_id)


@router.get(
    "/{group_id}/status-history",
    response_model=list[ClassGroupStatusHistoryItemOut],
)
def get_class_group_status_history(
    group_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_class_group_or_404(db, group_id)

    rows = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  class_group_id,
                  status,
                  reason_code,
                  reason_note,
                  changed_by_user_id,
                  created_at
                FROM public.class_group_status_history
                WHERE class_group_id = :group_id
                ORDER BY created_at DESC, id DESC
                """
            ),
            {"group_id": group_id},
        )
        .mappings()
        .all()
    )

    return rows


@router.post("/", response_model=ClassGroupOut, status_code=status.HTTP_201_CREATED)
def create_class_group(
    payload: ClassGroupCreateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _validate_class_group_payload(payload)

    try:
        row = (
            db.execute(
                text(
                    """
                    INSERT INTO public.class_groups (
                      name,
                      class_type,
                      level,
                      teacher_id,
                      court_id,
                      capacity,
                      is_active,
                      notes
                    )
                    VALUES (
                      :name,
                      :class_type,
                      :level,
                      :teacher_id,
                      :court_id,
                      :capacity,
                      :is_active,
                      :notes
                    )
                    RETURNING
                      id,
                      name,
                      class_type,
                      level,
                      teacher_id,
                      court_id,
                      capacity,
                      is_active,
                      notes,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "name": payload.name,
                    "class_type": payload.class_type,
                    "level": payload.level,
                    "teacher_id": payload.teacher_id,
                    "court_id": payload.court_id,
                    "capacity": payload.capacity,
                    "is_active": payload.is_active,
                    "notes": payload.notes,
                },
            )
            .mappings()
            .first()
        )
        _sync_group_teacher_assignments_from_legacy_teacher_id(
            db,
            group_id=row["id"],
            teacher_id=row["teacher_id"],
        )
        _insert_class_group_status_history(
            db,
            group_id=row["id"],
            status_value="active" if row["is_active"] else "inactive",
            changed_by_user_id=user_id,
            reason_code="created",
            reason_note="Cadastro inicial da turma.",
        )
        _sync_group_lesson_events(db, row["id"], user_id)
        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.patch("/{group_id}", response_model=ClassGroupOut)
def update_class_group(
    group_id: UUID,
    payload: ClassGroupUpdateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

    current = _get_class_group_or_404(db, group_id)

    if payload.is_active is not None and payload.is_active != current["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use os endpoints específicos de desativação/reativação da turma para alterar o status.",
        )

    merged = {
        "name": payload.name if payload.name is not None else current["name"],
        "class_type": payload.class_type
        if payload.class_type is not None
        else current["class_type"],
        "level": payload.level if payload.level is not None else current["level"],
        "teacher_id": payload.teacher_id
        if payload.teacher_id is not None
        else current["teacher_id"],
        "court_id": payload.court_id if payload.court_id is not None else current["court_id"],
        "capacity": payload.capacity if payload.capacity is not None else current["capacity"],
        "is_active": current["is_active"],
        "notes": payload.notes if payload.notes is not None else current["notes"],
    }

    _validate_class_group_payload(ClassGroupCreateIn(**merged))

    try:
        row = (
            db.execute(
                text(
                    """
                    UPDATE public.class_groups
                    SET
                      name = :name,
                      class_type = :class_type,
                      level = :level,
                      teacher_id = :teacher_id,
                      court_id = :court_id,
                      capacity = :capacity,
                      is_active = :is_active,
                      notes = :notes,
                      updated_at = now()
                    WHERE id = :group_id
                    RETURNING
                      id,
                      name,
                      class_type,
                      level,
                      teacher_id,
                      court_id,
                      capacity,
                      is_active,
                      notes,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "group_id": group_id,
                    **merged,
                },
            )
            .mappings()
            .first()
        )
        _sync_group_teacher_assignments_from_legacy_teacher_id(
            db,
            group_id=group_id,
            teacher_id=row["teacher_id"],
        )
        _sync_group_lesson_events(db, group_id, user_id)
        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.patch("/{group_id}/deactivate", response_model=ClassGroupOut)
def deactivate_class_group(
    group_id: UUID,
    payload: ClassGroupStatusChangeIn | None,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    current = _get_class_group_or_404(db, group_id)

    if not current["is_active"]:
        return current

    reason_code, reason_note = _validate_status_change_payload(payload)

    try:
        row = (
            db.execute(
                text(
                    """
                    UPDATE public.class_groups
                    SET
                      is_active = FALSE,
                      updated_at = now()
                    WHERE id = :group_id
                    RETURNING
                      id,
                      name,
                      class_type,
                      level,
                      teacher_id,
                      court_id,
                      capacity,
                      is_active,
                      notes,
                      created_at,
                      updated_at
                    """
                ),
                {"group_id": group_id},
            )
            .mappings()
            .first()
        )
        _insert_class_group_status_history(
            db,
            group_id=group_id,
            status_value="inactive",
            changed_by_user_id=user_id,
            reason_code=reason_code,
            reason_note=reason_note,
        )
        _sync_group_lesson_events(db, group_id, user_id)
        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.patch("/{group_id}/reactivate", response_model=ClassGroupOut)
def reactivate_class_group(
    group_id: UUID,
    payload: ClassGroupStatusChangeIn | None,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    current = _get_class_group_or_404(db, group_id)

    if current["is_active"]:
        return current

    reason_code, reason_note = _validate_status_change_payload(payload)

    try:
        row = (
            db.execute(
                text(
                    """
                    UPDATE public.class_groups
                    SET
                      is_active = TRUE,
                      updated_at = now()
                    WHERE id = :group_id
                    RETURNING
                      id,
                      name,
                      class_type,
                      level,
                      teacher_id,
                      court_id,
                      capacity,
                      is_active,
                      notes,
                      created_at,
                      updated_at
                    """
                ),
                {"group_id": group_id},
            )
            .mappings()
            .first()
        )
        _insert_class_group_status_history(
            db,
            group_id=group_id,
            status_value="active",
            changed_by_user_id=user_id,
            reason_code=reason_code,
            reason_note=reason_note,
        )
        _sync_group_lesson_events(db, group_id, user_id)
        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.get("/{group_id}/schedules", response_model=list[ClassGroupScheduleOut])
def list_class_group_schedules(
    group_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    _get_class_group_or_404(db, group_id)

    rows = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  class_group_id,
                  weekday,
                  start_time,
                  end_time,
                  starts_on,
                  ends_on,
                  is_active,
                  notes,
                  created_at,
                  updated_at
                FROM public.class_group_schedules
                WHERE class_group_id = :group_id
                ORDER BY
                  weekday,
                  start_time,
                  starts_on
                """
            ),
            {"group_id": group_id},
        )
        .mappings()
        .all()
    )
    return rows


@router.post(
    "/{group_id}/schedules",
    response_model=ClassGroupScheduleOut,
    status_code=status.HTTP_201_CREATED,
)
def create_class_group_schedule(
    group_id: UUID,
    payload: ClassGroupScheduleCreateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_class_group_or_404(db, group_id)
    _validate_schedule_payload(payload)

    try:
        row = (
            db.execute(
                text(
                    """
                    INSERT INTO public.class_group_schedules (
                      class_group_id,
                      weekday,
                      start_time,
                      end_time,
                      starts_on,
                      ends_on,
                      is_active,
                      notes
                    )
                    VALUES (
                      :class_group_id,
                      :weekday,
                      :start_time,
                      :end_time,
                      :starts_on,
                      :ends_on,
                      :is_active,
                      :notes
                    )
                    RETURNING
                      id,
                      class_group_id,
                      weekday,
                      start_time,
                      end_time,
                      starts_on,
                      ends_on,
                      is_active,
                      notes,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "class_group_id": group_id,
                    "weekday": payload.weekday,
                    "start_time": payload.start_time,
                    "end_time": payload.end_time,
                    "starts_on": payload.starts_on,
                    "ends_on": payload.ends_on,
                    "is_active": payload.is_active,
                    "notes": payload.notes,
                },
            )
            .mappings()
            .first()
        )
        _sync_group_lesson_events(db, group_id, user_id)
        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.get("/{group_id}/schedules/{schedule_id}", response_model=ClassGroupScheduleOut)
def get_class_group_schedule(
    group_id: UUID,
    schedule_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    _get_class_group_or_404(db, group_id)
    return _get_class_group_schedule_or_404(db, group_id, schedule_id)


@router.patch("/{group_id}/schedules/{schedule_id}", response_model=ClassGroupScheduleOut)
def update_class_group_schedule(
    group_id: UUID,
    schedule_id: UUID,
    payload: ClassGroupScheduleUpdateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_class_group_or_404(db, group_id)

    current = _get_class_group_schedule_or_404(db, group_id, schedule_id)

    merged = {
        "weekday": payload.weekday if payload.weekday is not None else current["weekday"],
        "start_time": payload.start_time
        if payload.start_time is not None
        else current["start_time"],
        "end_time": payload.end_time if payload.end_time is not None else current["end_time"],
        "starts_on": payload.starts_on if payload.starts_on is not None else current["starts_on"],
        "ends_on": payload.ends_on if payload.ends_on is not None else current["ends_on"],
        "is_active": payload.is_active if payload.is_active is not None else current["is_active"],
        "notes": payload.notes if payload.notes is not None else current["notes"],
    }

    _validate_schedule_payload(ClassGroupScheduleCreateIn(**merged))

    try:
        row = (
            db.execute(
                text(
                    """
                    UPDATE public.class_group_schedules
                    SET
                      weekday = :weekday,
                      start_time = :start_time,
                      end_time = :end_time,
                      starts_on = :starts_on,
                      ends_on = :ends_on,
                      is_active = :is_active,
                      notes = :notes,
                      updated_at = now()
                    WHERE id = :schedule_id
                      AND class_group_id = :group_id
                    RETURNING
                      id,
                      class_group_id,
                      weekday,
                      start_time,
                      end_time,
                      starts_on,
                      ends_on,
                      is_active,
                      notes,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "schedule_id": schedule_id,
                    "group_id": group_id,
                    **merged,
                },
            )
            .mappings()
            .first()
        )
        _sync_group_lesson_events(db, group_id, user_id)
        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.patch(
    "/{group_id}/schedules/{schedule_id}/deactivate",
    response_model=ClassGroupScheduleOut,
)
def deactivate_class_group_schedule(
    group_id: UUID,
    schedule_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_class_group_or_404(db, group_id)
    _get_class_group_schedule_or_404(db, group_id, schedule_id)

    try:
        row = (
            db.execute(
                text(
                    """
                    UPDATE public.class_group_schedules
                    SET
                      is_active = FALSE,
                      updated_at = now()
                    WHERE id = :schedule_id
                      AND class_group_id = :group_id
                    RETURNING
                      id,
                      class_group_id,
                      weekday,
                      start_time,
                      end_time,
                      starts_on,
                      ends_on,
                      is_active,
                      notes,
                      created_at,
                      updated_at
                    """
                ),
                {"schedule_id": schedule_id, "group_id": group_id},
            )
            .mappings()
            .first()
        )
        _sync_group_lesson_events(db, group_id, user_id)
        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.get("/{group_id}/enrollments", response_model=list[ClassGroupEnrollmentListItemOut])
def list_class_group_enrollments(
    group_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    _get_class_group_or_404(db, group_id)

    rows = (
        db.execute(
            text(
                """
                SELECT
                  e.id,
                  e.class_group_id,
                  e.student_id,
                  s.full_name AS student_name,
                  s.email AS student_email,
                  s.phone AS student_phone,
                  e.status,
                  e.starts_on,
                  e.ends_on,
                  e.created_at,
                  e.updated_at
                FROM public.class_group_enrollments e
                JOIN public.students s
                  ON s.id = e.student_id
                WHERE e.class_group_id = :group_id
                ORDER BY
                  s.full_name,
                  e.starts_on
                """
            ),
            {"group_id": group_id},
        )
        .mappings()
        .all()
    )
    return rows


@router.post(
    "/{group_id}/enrollments",
    response_model=ClassGroupEnrollmentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_class_group_enrollment(
    group_id: UUID,
    payload: ClassGroupEnrollmentCreateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    group = _get_class_group_or_404(db, group_id)
    _validate_enrollment_payload(payload)

    active_enrollments = (
        db.execute(
            text(
                """
            SELECT COUNT(*) AS total
            FROM public.class_group_enrollments
            WHERE class_group_id = :group_id
              AND status = 'active'
              AND (
                ends_on IS NULL
                OR ends_on >= CURRENT_DATE
              )
            """
            ),
            {"group_id": group_id},
        )
        .mappings()
        .first()
    )

    current_total = int(active_enrollments["total"]) if active_enrollments else 0
    if current_total >= int(group["capacity"]):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A turma já atingiu sua capacidade máxima.",
        )

    try:
        row = (
            db.execute(
                text(
                    """
                    INSERT INTO public.class_group_enrollments (
                      class_group_id,
                      student_id,
                      status,
                      starts_on,
                      ends_on
                    )
                    VALUES (
                      :class_group_id,
                      :student_id,
                      :status,
                      :starts_on,
                      :ends_on
                    )
                    RETURNING
                      id,
                      class_group_id,
                      student_id,
                      status,
                      starts_on,
                      ends_on,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "class_group_id": group_id,
                    "student_id": payload.student_id,
                    "status": payload.status,
                    "starts_on": payload.starts_on,
                    "ends_on": payload.ends_on,
                },
            )
            .mappings()
            .first()
        )
        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.get(
    "/{group_id}/enrollments/{enrollment_id}",
    response_model=ClassGroupEnrollmentListItemOut,
)
def get_class_group_enrollment(
    group_id: UUID,
    enrollment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    _get_class_group_or_404(db, group_id)
    return _get_class_group_enrollment_or_404(db, group_id, enrollment_id)


@router.patch(
    "/{group_id}/enrollments/{enrollment_id}",
    response_model=ClassGroupEnrollmentOut,
)
def update_class_group_enrollment(
    group_id: UUID,
    enrollment_id: UUID,
    payload: ClassGroupEnrollmentUpdateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_class_group_or_404(db, group_id)

    current = _get_class_group_enrollment_or_404(db, group_id, enrollment_id)

    merged = {
        "status": payload.status if payload.status is not None else current["status"],
        "starts_on": payload.starts_on if payload.starts_on is not None else current["starts_on"],
        "ends_on": payload.ends_on if payload.ends_on is not None else current["ends_on"],
    }

    _validate_enrollment_payload(
        ClassGroupEnrollmentCreateIn(student_id=current["student_id"], **merged)
    )

    try:
        row = (
            db.execute(
                text(
                    """
                    UPDATE public.class_group_enrollments
                    SET
                      status = :status,
                      starts_on = :starts_on,
                      ends_on = :ends_on,
                      updated_at = now()
                    WHERE id = :enrollment_id
                      AND class_group_id = :group_id
                    RETURNING
                      id,
                      class_group_id,
                      student_id,
                      status,
                      starts_on,
                      ends_on,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "enrollment_id": enrollment_id,
                    "group_id": group_id,
                    **merged,
                },
            )
            .mappings()
            .first()
        )
        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.patch(
    "/{group_id}/enrollments/{enrollment_id}/cancel",
    response_model=ClassGroupEnrollmentOut,
)
def cancel_class_group_enrollment(
    group_id: UUID,
    enrollment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_class_group_or_404(db, group_id)
    _get_class_group_enrollment_or_404(db, group_id, enrollment_id)

    row = (
        db.execute(
            text(
                """
                UPDATE public.class_group_enrollments
                SET
                  status = 'cancelled',
                  updated_at = now()
                WHERE id = :enrollment_id
                  AND class_group_id = :group_id
                RETURNING
                  id,
                  class_group_id,
                  student_id,
                  status,
                  starts_on,
                  ends_on,
                  created_at,
                  updated_at
                """
            ),
            {"enrollment_id": enrollment_id, "group_id": group_id},
        )
        .mappings()
        .first()
    )
    db.commit()
    return row

from __future__ import annotations

from typing import Annotated
from uuid import UUID

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


def _integrity_to_http(e: IntegrityError) -> HTTPException:
    orig = getattr(e, "orig", None)
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)

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


def _get_class_group_or_404(db: Session, group_id: UUID):
    row = (
        db.execute(
            text(
                """
                SELECT
                  cg.id,
                  cg.name,
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
    level: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    teacher_id: Annotated[UUID | None, Query()] = None,
    court_id: Annotated[UUID | None, Query()] = None,
):
    where_clauses = []
    params: dict[str, object] = {}

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
                      level,
                      teacher_id,
                      court_id,
                      capacity,
                      is_active,
                      notes
                    )
                    VALUES (
                      :name,
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

    merged = {
        "name": payload.name if payload.name is not None else current["name"],
        "level": payload.level if payload.level is not None else current["level"],
        "teacher_id": payload.teacher_id
        if payload.teacher_id is not None
        else current["teacher_id"],
        "court_id": payload.court_id if payload.court_id is not None else current["court_id"],
        "capacity": payload.capacity if payload.capacity is not None else current["capacity"],
        "is_active": payload.is_active if payload.is_active is not None else current["is_active"],
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
        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.patch("/{group_id}/deactivate", response_model=ClassGroupOut)
def deactivate_class_group(
    group_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_class_group_or_404(db, group_id)

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
    db.commit()
    return row


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
    db.commit()
    return row


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

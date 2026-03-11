from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.db.session import get_db
from app.models.student import Student
from app.models.trial_lesson import TrialLesson
from app.models.user import User

router = APIRouter(prefix="/trial-lessons", tags=["trial-lessons"])


def _raise_trial_block(code: str, message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": code,
            "message": message,
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
                status_code=409,
                detail={
                    "code": "COURT_ALREADY_OCCUPIED",
                    "message": "A quadra selecionada já não está mais disponível nesse horário.",
                },
            )
        if constraint == "ex_events_no_overlap_teacher":
            return HTTPException(
                status_code=409,
                detail={
                    "code": "TEACHER_ALREADY_OCCUPIED",
                    "message": "O professor selecionado já não está mais disponível nesse horário.",
                },
            )
        return HTTPException(
            status_code=409,
            detail={
                "code": "TIME_SLOT_UNAVAILABLE",
                "message": "Esse horário não está mais disponível.",
            },
        )

    if pgcode == "23503":
        return HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_REFERENCE",
                "message": "Referência inválida para quadra ou professor.",
            },
        )

    return HTTPException(
        status_code=400,
        detail={
            "code": "EVENT_CREATE_ERROR",
            "message": f"Erro ao salvar evento: {str(orig) if orig else str(e)}",
        },
    )


class TrialLessonRequestIn(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class TrialLessonEligibilityOut(BaseModel):
    eligible: bool
    reason_code: str | None = None
    message: str
    current_status: str | None = None


class TrialLessonRequestOut(BaseModel):
    id: str
    user_id: str
    status: str
    message: str


class TrialLessonSlotOut(BaseModel):
    start_at: datetime
    end_at: datetime
    court_id: UUID
    court_name: str
    teacher_id: UUID
    teacher_name: str


class TrialLessonScheduleIn(BaseModel):
    court_id: UUID
    teacher_id: UUID
    start_at: datetime
    end_at: datetime
    notes: str | None = Field(default=None, max_length=1000)


class TrialLessonScheduleOut(BaseModel):
    trial_lesson_id: str
    event_id: str
    status: str
    start_at: datetime
    end_at: datetime
    court_id: UUID
    teacher_id: UUID
    message: str


class TrialLessonCurrentOut(BaseModel):
    scheduled: bool
    message: str
    trial_lesson_id: str | None = None
    event_id: str | None = None
    status: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    court_id: UUID | None = None
    court_name: str | None = None
    teacher_id: UUID | None = None
    teacher_name: str | None = None
    notes: str | None = None
    can_cancel: bool = False
    can_reschedule: bool = False
    change_deadline_at: datetime | None = None
    change_rule_message: str | None = None
    change_status_message: str | None = None


class TrialLessonCancelOut(BaseModel):
    trial_lesson_id: str
    event_id: str
    status: str
    message: str
    cancelled_outside_reschedule_policy: bool = False
    requires_admin_approval: bool = False


class TrialLessonRescheduleIn(BaseModel):
    court_id: UUID
    teacher_id: UUID
    start_at: datetime
    end_at: datetime
    notes: str | None = Field(default=None, max_length=1000)


class TrialLessonRescheduleOut(BaseModel):
    trial_lesson_id: str
    old_event_id: str
    new_event_id: str
    status: str
    start_at: datetime
    end_at: datetime
    court_id: UUID
    teacher_id: UUID
    message: str


def _normalize_notes(notes: str | None) -> str | None:
    if not notes:
        return None
    value = notes.strip()
    return value or None


def _normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    value = email.strip().lower()
    return value or None


def _normalize_whatsapp(whatsapp: str | None) -> str | None:
    if not whatsapp:
        return None
    digits = "".join(ch for ch in whatsapp if ch.isdigit())
    return digits or None


def _get_user_or_404(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")
    return user


def _is_active_student(db: Session, user: User) -> bool:
    conditions = [Student.user_id == user.id]

    if user.email:
        conditions.append(func.lower(Student.email) == user.email.lower())

    stmt = select(Student).where(
        Student.is_active.is_(True),
        or_(*conditions),
    )

    student = db.scalar(stmt)
    return student is not None


def _get_latest_completed_trial(db: Session, user_id: UUID) -> TrialLesson | None:
    return db.scalar(
        select(TrialLesson)
        .where(
            TrialLesson.user_id == user_id,
            TrialLesson.status == "completed",
        )
        .order_by(TrialLesson.created_at.desc())
        .limit(1)
    )


def _get_latest_scheduled_trial(db: Session, user_id: UUID) -> TrialLesson | None:
    return db.scalar(
        select(TrialLesson)
        .where(
            TrialLesson.user_id == user_id,
            TrialLesson.status == "scheduled",
        )
        .order_by(TrialLesson.created_at.desc())
        .limit(1)
    )


def _get_latest_requested_trial(db: Session, user_id: UUID) -> TrialLesson | None:
    return db.scalar(
        select(TrialLesson)
        .where(
            TrialLesson.user_id == user_id,
            TrialLesson.status == "requested",
        )
        .order_by(TrialLesson.created_at.desc())
        .limit(1)
    )


def _local_tz() -> ZoneInfo:
    return ZoneInfo("America/Sao_Paulo")


def _trial_last_allowed_date() -> date:
    tz = _local_tz()
    today = datetime.now(tz).date()

    if today.month == 12:
        year = today.year + 1
        month = 1
    else:
        year = today.year
        month = today.month + 1

    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def _validate_trial_date_window(target_date: date) -> None:
    tz = _local_tz()
    today = datetime.now(tz).date()
    max_date = _trial_last_allowed_date()

    if target_date < today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "TRIAL_DATE_BEFORE_TODAY",
                "message": "A aula grátis só pode ser agendada a partir de hoje.",
            },
        )

    if target_date > max_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "TRIAL_DATE_OUT_OF_WINDOW",
                "message": "A aula grátis só pode ser agendada para este mês ou para o próximo.",
            },
        )


def _validate_trial_slot_duration(start_at: datetime, end_at: datetime) -> None:
    duration_minutes = int((end_at - start_at).total_seconds() / 60)

    if duration_minutes != 30:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_TRIAL_DURATION",
                "message": "A aula grátis deve ter duração de 30 minutos.",
            },
        )


def _round_up_to_next_slot(dt: datetime, slot_minutes: int) -> datetime:
    dt = dt.replace(second=0, microsecond=0)

    remainder = dt.minute % slot_minutes
    if remainder == 0:
        return dt

    minutes_to_add = slot_minutes - remainder
    return dt + timedelta(minutes=minutes_to_add)


def _validate_trial_not_in_past(start_at: datetime) -> None:
    now = datetime.now(_local_tz())

    if start_at.astimezone(_local_tz()) <= now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "TRIAL_TIME_IN_PAST",
                "message": "Não é possível agendar ou remarcar aula grátis para horário passado.",
            },
        )


def _list_available_courts(db: Session, start_at: datetime, end_at: datetime):
    sql = text("SELECT * FROM public.fn_quadras_disponiveis(:p_from, :p_to)")
    return db.execute(sql, {"p_from": start_at, "p_to": end_at}).mappings().all()


def _list_available_teachers(db: Session, start_at: datetime, end_at: datetime):
    sql = text("SELECT * FROM public.fn_professores_disponiveis(:p_from, :p_to)")
    return db.execute(sql, {"p_from": start_at, "p_to": end_at}).mappings().all()


def _slot_is_still_available(
    db: Session,
    start_at: datetime,
    end_at: datetime,
    court_id: UUID,
    teacher_id: UUID,
) -> bool:
    available_courts = _list_available_courts(db, start_at, end_at)
    available_teachers = _list_available_teachers(db, start_at, end_at)

    court_ok = any(item["court_id"] == court_id for item in available_courts)
    teacher_ok = any(item["teacher_id"] == teacher_id for item in available_teachers)

    return court_ok and teacher_ok


def _get_change_policy(start_at: datetime) -> tuple[bool, bool, datetime | None, str, str]:
    tz = _local_tz()
    now = datetime.now(tz)
    local_start = start_at.astimezone(tz)

    if local_start <= now:
        return (
            False,
            False,
            None,
            (
                "Cancelamentos podem ser feitos até o início da aula. "
                "Remarcações respeitam a antecedência mínima definida pela escola."
            ),
            "A aula já começou ou já passou. Não é mais possível cancelar ou remarcar.",
        )

    today = now.date()
    lesson_date = local_start.date()

    if lesson_date == today:
        reschedule_deadline = local_start - timedelta(hours=2)
        reschedule_rule = (
            "Para aulas agendadas no mesmo dia, a remarcação deve ocorrer "
            "com no mínimo 2 horas de antecedência."
        )
    elif lesson_date == today + timedelta(days=1):
        reschedule_deadline = local_start - timedelta(hours=6)
        reschedule_rule = (
            "Para aulas agendadas para o dia seguinte, a remarcação deve ocorrer "
            "com no mínimo 6 horas de antecedência."
        )
    else:
        reschedule_deadline = local_start - timedelta(hours=48)
        reschedule_rule = (
            "Para aulas agendadas a partir de dois dias à frente, a remarcação deve ocorrer "
            "com no mínimo 48 horas de antecedência."
        )

    can_cancel = now < local_start
    can_reschedule = now <= reschedule_deadline

    combined_rule = (
        f"Cancelamentos podem ser feitos até o início da aula agendada. {reschedule_rule}"
    )

    if can_reschedule:
        status_message = (
            "Você ainda pode cancelar esta aula até o início do horário agendado "
            "e também remarcar dentro do prazo atual."
        )
    else:
        status_message = (
            "Você ainda pode cancelar esta aula até o início do horário agendado, "
            "mas o prazo para remarcação já expirou."
        )

    return can_cancel, can_reschedule, reschedule_deadline, combined_rule, status_message


def _get_current_scheduled_trial_row(db: Session, user_id: UUID):
    return (
        db.execute(
            text(
                """
                SELECT
                  tl.id AS trial_lesson_id,
                  tl.event_id AS event_id,
                  tl.status AS status,
                  tl.notes AS notes,
                  ag.start_at AS start_at,
                  ag.end_at AS end_at,
                  ag.court_id AS court_id,
                  ag.court_name AS court_name,
                  ag.teacher_id AS teacher_id,
                  ag.teacher_name AS teacher_name
                FROM public.trial_lessons tl
                JOIN public.vw_agenda ag
                  ON ag.event_id = tl.event_id
                WHERE tl.user_id = :user_id
                  AND tl.status = 'scheduled'
                  AND ag.kind = 'primeira_aula'
                  AND ag.status = 'confirmado'
                ORDER BY tl.scheduled_at DESC NULLS LAST, tl.created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
        .mappings()
        .first()
    )


def _find_trial_control(db: Session, email: str | None, whatsapp: str | None):
    if not email and not whatsapp:
        return None

    if email and whatsapp:
        sql = text(
            """
            SELECT *
            FROM public.trial_lesson_controls
            WHERE lower(email) = :email
               OR whatsapp = :whatsapp
            ORDER BY
              CASE WHEN lower(email) = :email THEN 0 ELSE 1 END,
              CASE WHEN whatsapp = :whatsapp THEN 0 ELSE 1 END
            LIMIT 1
            """
        )
        params = {
            "email": email,
            "whatsapp": whatsapp,
        }
    elif email:
        sql = text(
            """
            SELECT *
            FROM public.trial_lesson_controls
            WHERE lower(email) = :email
            LIMIT 1
            """
        )
        params = {"email": email}
    else:
        sql = text(
            """
            SELECT *
            FROM public.trial_lesson_controls
            WHERE whatsapp = :whatsapp
            LIMIT 1
            """
        )
        params = {"whatsapp": whatsapp}

    return db.execute(sql, params).mappings().first()


def _ensure_trial_control_for_user(db: Session, user: User):
    email = _normalize_email(user.email)
    whatsapp = _normalize_whatsapp(getattr(user, "whatsapp", None))

    row = _find_trial_control(db, email, whatsapp)

    if row:
        return (
            db.execute(
                text(
                    """
                    UPDATE public.trial_lesson_controls
                    SET
                      email = COALESCE(email, :email),
                      whatsapp = COALESCE(whatsapp, :whatsapp),
                      updated_at = now()
                    WHERE id = :id
                    RETURNING *
                    """
                ),
                {
                    "id": row["id"],
                    "email": email,
                    "whatsapp": whatsapp,
                },
            )
            .mappings()
            .first()
        )

    if not email and not whatsapp:
        return None

    return (
        db.execute(
            text(
                """
                INSERT INTO public.trial_lesson_controls (
                  email,
                  whatsapp,
                  requires_admin_approval,
                  is_blocked
                )
                VALUES (
                  :email,
                  :whatsapp,
                  false,
                  false
                )
                RETURNING *
                """
            ),
            {
                "email": email,
                "whatsapp": whatsapp,
            },
        )
        .mappings()
        .first()
    )


def _count_recent_occurrences(
    db: Session,
    email: str | None,
    whatsapp: str | None,
    occurrence_types: tuple[str, ...],
    *,
    days: int = 60,
) -> int:
    if not email and not whatsapp:
        return 0

    type_list_sql = ", ".join(f"'{item}'" for item in occurrence_types)

    if email and whatsapp:
        sql = text(
            f"""
            SELECT COUNT(*) AS total
            FROM public.trial_lesson_occurrences
            WHERE occurrence_type IN ({type_list_sql})
              AND created_at >= now() - (:days * interval '1 day')
              AND (
                lower(email) = :email
                OR whatsapp = :whatsapp
              )
            """
        )
        params = {
            "email": email,
            "whatsapp": whatsapp,
            "days": days,
        }
    elif email:
        sql = text(
            f"""
            SELECT COUNT(*) AS total
            FROM public.trial_lesson_occurrences
            WHERE occurrence_type IN ({type_list_sql})
              AND created_at >= now() - (:days * interval '1 day')
              AND lower(email) = :email
            """
        )
        params = {
            "email": email,
            "days": days,
        }
    else:
        sql = text(
            f"""
            SELECT COUNT(*) AS total
            FROM public.trial_lesson_occurrences
            WHERE occurrence_type IN ({type_list_sql})
              AND created_at >= now() - (:days * interval '1 day')
              AND whatsapp = :whatsapp
            """
        )
        params = {
            "whatsapp": whatsapp,
            "days": days,
        }

    count_value = db.execute(sql, params).scalar_one()
    return int(count_value or 0)


def _sync_trial_control_requirements(
    db: Session,
    control_id: UUID,
    email: str | None,
    whatsapp: str | None,
) -> bool:
    control = (
        db.execute(
            text(
                """
                SELECT *
                FROM public.trial_lesson_controls
                WHERE id = :id
                """
            ),
            {"id": control_id},
        )
        .mappings()
        .first()
    )

    if not control:
        return False

    recent_cancellations = _count_recent_occurrences(
        db,
        email,
        whatsapp,
        ("cancelled", "cancelled_late"),
        days=60,
    )

    recent_reschedules = _count_recent_occurrences(
        db,
        email,
        whatsapp,
        ("rescheduled",),
        days=60,
    )

    requires_admin_approval = (
        bool(control["requires_admin_approval"])
        or int(control["no_show_count"] or 0) >= 1
        or int(control["late_cancellations"] or 0) >= 2
        or int(recent_cancellations) >= 3
        or int(recent_reschedules) >= 2
    )

    db.execute(
        text(
            """
            UPDATE public.trial_lesson_controls
            SET
              requires_admin_approval = :requires_admin_approval,
              updated_at = now()
            WHERE id = :id
            """
        ),
        {
            "id": control_id,
            "requires_admin_approval": requires_admin_approval,
        },
    )

    return requires_admin_approval


def _record_trial_occurrence(
    db: Session,
    *,
    user: User,
    trial_lesson_id: UUID | None,
    occurrence_type: str,
    description: str | None,
) -> bool:
    email = _normalize_email(user.email)
    whatsapp = _normalize_whatsapp(getattr(user, "whatsapp", None))

    control = _ensure_trial_control_for_user(db, user)

    db.execute(
        text(
            """
            INSERT INTO public.trial_lesson_occurrences (
              user_id,
              trial_lesson_id,
              email,
              whatsapp,
              occurrence_type,
              description
            )
            VALUES (
              :user_id,
              :trial_lesson_id,
              :email,
              :whatsapp,
              :occurrence_type,
              :description
            )
            """
        ),
        {
            "user_id": user.id,
            "trial_lesson_id": trial_lesson_id,
            "email": email,
            "whatsapp": whatsapp,
            "occurrence_type": occurrence_type,
            "description": description,
        },
    )

    if not control:
        return False

    cancellation_increment = 1 if occurrence_type in ("cancelled", "cancelled_late") else 0
    late_cancellation_increment = 1 if occurrence_type == "cancelled_late" else 0
    no_show_increment = 1 if occurrence_type == "no_show" else 0

    updated_control = (
        db.execute(
            text(
                """
                UPDATE public.trial_lesson_controls
                SET
                  total_cancellations = total_cancellations + :cancellation_increment,
                  late_cancellations = late_cancellations + :late_cancellation_increment,
                  no_show_count = no_show_count + :no_show_increment,
                  last_occurrence_at = now(),
                  updated_at = now()
                WHERE id = :id
                RETURNING *
                """
            ),
            {
                "id": control["id"],
                "cancellation_increment": cancellation_increment,
                "late_cancellation_increment": late_cancellation_increment,
                "no_show_increment": no_show_increment,
            },
        )
        .mappings()
        .first()
    )

    if not updated_control:
        return False

    return _sync_trial_control_requirements(
        db,
        updated_control["id"],
        email,
        whatsapp,
    )


def _get_trial_control_state(db: Session, user: User):
    email = _normalize_email(user.email)
    whatsapp = _normalize_whatsapp(getattr(user, "whatsapp", None))
    return _find_trial_control(db, email, whatsapp)


def _get_trial_block_reason(
    db: Session,
    user: User,
    *,
    allow_scheduled_for_reschedule: bool = False,
) -> tuple[str | None, str, str | None]:
    if _is_active_student(db, user):
        return (
            "ACTIVE_STUDENT_NOT_ELIGIBLE",
            "Alunos ativos da escola não podem solicitar aula grátis.",
            None,
        )

    scheduled = _get_latest_scheduled_trial(db, user.id)
    if scheduled:
        if allow_scheduled_for_reschedule:
            control = _get_trial_control_state(db, user)
            if control and bool(control["requires_admin_approval"]):
                return (
                    "TRIAL_ADMIN_APPROVAL_REQUIRED",
                    "Não foi possível concluir uma nova remarcação automática. Entre em contato com a escola para validar o próximo horário.",
                    scheduled.status,
                )

            return (
                None,
                "Você pode remarcar sua aula grátis dentro da política vigente.",
                scheduled.status,
            )

        return (
            "TRIAL_LESSON_ALREADY_SCHEDULED",
            "Você já possui uma aula grátis agendada.",
            scheduled.status,
        )

    completed = _get_latest_completed_trial(db, user.id)
    if completed:
        return (
            "TRIAL_LESSON_ALREADY_COMPLETED",
            "Você já utilizou sua aula grátis.",
            completed.status,
        )

    control = _get_trial_control_state(db, user)
    if control:
        blocked_until = control["blocked_until"]

        if bool(control["is_blocked"]):
            if blocked_until is None or blocked_until > datetime.now(_local_tz()):
                return (
                    "TRIAL_BOOKING_BLOCKED",
                    "Seu cadastro está temporariamente impedido de novos agendamentos. Entre em contato com a escola.",
                    None,
                )

        if bool(control["requires_admin_approval"]):
            return (
                "TRIAL_ADMIN_APPROVAL_REQUIRED",
                "Seu cadastro precisa de aprovação da equipe antes de um novo agendamento. Entre em contato com a escola.",
                None,
            )

    return (None, "Você pode solicitar sua aula grátis.", None)


@router.get("/eligibility", response_model=TrialLessonEligibilityOut)
def trial_lesson_eligibility(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    current_user = _get_user_or_404(db, UUID(user_id))
    reason_code, message, current_status = _get_trial_block_reason(db, current_user)

    return TrialLessonEligibilityOut(
        eligible=reason_code is None,
        reason_code=reason_code,
        message=message,
        current_status=current_status,
    )


@router.get("/current", response_model=TrialLessonCurrentOut)
def current_trial_lesson(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    current_user = _get_user_or_404(db, UUID(user_id))

    row = _get_current_scheduled_trial_row(db, current_user.id)

    if not row:
        return TrialLessonCurrentOut(
            scheduled=False,
            message="Você não possui aula grátis agendada no momento.",
        )

    can_cancel, can_reschedule, deadline_at, rule_message, status_message = _get_change_policy(
        row["start_at"]
    )

    return TrialLessonCurrentOut(
        scheduled=True,
        message="Sua aula grátis está agendada.",
        trial_lesson_id=str(row["trial_lesson_id"]),
        event_id=str(row["event_id"]),
        status=row["status"],
        start_at=row["start_at"],
        end_at=row["end_at"],
        court_id=row["court_id"],
        court_name=row["court_name"],
        teacher_id=row["teacher_id"],
        teacher_name=row["teacher_name"],
        notes=row["notes"],
        can_cancel=can_cancel,
        can_reschedule=can_reschedule,
        change_deadline_at=deadline_at,
        change_rule_message=rule_message,
        change_status_message=status_message,
    )


@router.get("/slots", response_model=list[TrialLessonSlotOut])
def trial_lesson_slots(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=7)] = 7,
    slot_minutes: Annotated[int, Query(ge=30, le=30)] = 30,
    day_start_hour: Annotated[int, Query(ge=6, le=20)] = 8,
    day_end_hour: Annotated[int, Query(ge=7, le=22)] = 20,
    mode: Annotated[str, Query()] = "schedule",
):
    current_user = _get_user_or_404(db, UUID(user_id))

    allow_scheduled_for_reschedule = mode == "reschedule"

    if allow_scheduled_for_reschedule:
        row = _get_current_scheduled_trial_row(db, current_user.id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "TRIAL_LESSON_NOT_FOUND",
                    "message": "Você não possui aula grátis agendada para remarcar.",
                },
            )

        _can_cancel, can_reschedule, _deadline_at, _rule_message, status_message = (
            _get_change_policy(row["start_at"])
        )

        if not can_reschedule:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "TRIAL_RESCHEDULE_WINDOW_EXPIRED",
                    "message": status_message,
                },
            )

    reason_code, message, _current_status = _get_trial_block_reason(
        db,
        current_user,
        allow_scheduled_for_reschedule=allow_scheduled_for_reschedule,
    )
    if reason_code is not None:
        _raise_trial_block(reason_code, message)

    if day_start_hour >= day_end_hour:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="day_start_hour precisa ser menor que day_end_hour",
        )

    tz = _local_tz()
    today = datetime.now(tz).date()
    max_allowed_date = _trial_last_allowed_date()
    start_day = from_date or today

    _validate_trial_date_window(start_day)

    slots: list[TrialLessonSlotOut] = []

    for day_offset in range(days):
        current_day = start_day + timedelta(days=day_offset)

        if current_day > max_allowed_date:
            break

        window_start = datetime.combine(current_day, time(hour=day_start_hour), tzinfo=tz)
        window_end = datetime.combine(current_day, time(hour=day_end_hour), tzinfo=tz)

        slot_delta = timedelta(minutes=slot_minutes)

        if current_day == today:
            now_local = datetime.now(tz)
            earliest_start = _round_up_to_next_slot(now_local, slot_minutes)
            slot_start = max(window_start, earliest_start)
        else:
            slot_start = window_start

        while slot_start + slot_delta <= window_end:
            slot_end = slot_start + slot_delta

            available_courts = _list_available_courts(db, slot_start, slot_end)
            available_teachers = _list_available_teachers(db, slot_start, slot_end)

            if available_courts and available_teachers:
                first_court = available_courts[0]
                first_teacher = available_teachers[0]

                slots.append(
                    TrialLessonSlotOut(
                        start_at=slot_start,
                        end_at=slot_end,
                        court_id=first_court["court_id"],
                        court_name=first_court["court_name"],
                        teacher_id=first_teacher["teacher_id"],
                        teacher_name=first_teacher["teacher_name"],
                    )
                )

            slot_start = slot_end

    return slots


@router.post(
    "/schedule", response_model=TrialLessonScheduleOut, status_code=status.HTTP_201_CREATED
)
def schedule_trial_lesson(
    data: TrialLessonScheduleIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    current_user = _get_user_or_404(db, UUID(user_id))

    reason_code, message, _current_status = _get_trial_block_reason(db, current_user)
    if reason_code is not None:
        _raise_trial_block(reason_code, message)

    if data.end_at <= data.start_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_TIME_RANGE",
                "message": "end_at precisa ser maior que start_at.",
            },
        )

    _validate_trial_slot_duration(data.start_at, data.end_at)
    _validate_trial_date_window(data.start_at.astimezone(_local_tz()).date())
    _validate_trial_not_in_past(data.start_at)

    if not _slot_is_still_available(
        db=db,
        start_at=data.start_at,
        end_at=data.end_at,
        court_id=data.court_id,
        teacher_id=data.teacher_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SLOT_NO_LONGER_AVAILABLE",
                "message": "O horário selecionado não está mais disponível. Atualize a agenda e escolha outro slot.",
            },
        )

    try:
        event_row = (
            db.execute(
                text(
                    """
                    INSERT INTO public.events (
                      court_id, teacher_id, student_id, created_by,
                      kind, status, start_at, end_at, notes
                    )
                    VALUES (
                      :court_id, :teacher_id, :student_id, :created_by,
                      :kind, :status, :start_at, :end_at, :notes
                    )
                    RETURNING
                      id, court_id, teacher_id, student_id, created_by,
                      kind, status, start_at, end_at, notes, created_at, updated_at
                    """
                ),
                {
                    "court_id": data.court_id,
                    "teacher_id": data.teacher_id,
                    "student_id": None,
                    "created_by": current_user.id,
                    "kind": "primeira_aula",
                    "status": "confirmado",
                    "start_at": data.start_at,
                    "end_at": data.end_at,
                    "notes": _normalize_notes(data.notes) or "Primeira aula agendada pelo portal.",
                },
            )
            .mappings()
            .first()
        )

        existing_requested = _get_latest_requested_trial(db, current_user.id)

        if existing_requested:
            existing_requested.event_id = event_row["id"]
            existing_requested.status = "scheduled"
            existing_requested.scheduled_at = data.start_at
            existing_requested.notes = _normalize_notes(data.notes)
            trial = existing_requested
        else:
            trial = TrialLesson(
                user_id=current_user.id,
                event_id=event_row["id"],
                status="scheduled",
                scheduled_at=data.start_at,
                notes=_normalize_notes(data.notes),
            )
            db.add(trial)

        db.commit()
        db.refresh(trial)

        return TrialLessonScheduleOut(
            trial_lesson_id=str(trial.id),
            event_id=str(event_row["id"]),
            status=trial.status,
            start_at=event_row["start_at"],
            end_at=event_row["end_at"],
            court_id=event_row["court_id"],
            teacher_id=event_row["teacher_id"],
            message="Sua aula grátis foi agendada com sucesso.",
        )

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.post("/cancel", response_model=TrialLessonCancelOut)
def cancel_trial_lesson(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    current_user = _get_user_or_404(db, UUID(user_id))

    row = _get_current_scheduled_trial_row(db, current_user.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "TRIAL_LESSON_NOT_FOUND",
                "message": "Você não possui aula grátis agendada no momento.",
            },
        )

    can_cancel, can_reschedule, _deadline_at, _rule_message, status_message = _get_change_policy(
        row["start_at"]
    )

    if not can_cancel:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIAL_CANCEL_WINDOW_EXPIRED",
                "message": status_message,
            },
        )

    trial = db.get(TrialLesson, row["trial_lesson_id"])
    if not trial:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "TRIAL_LESSON_NOT_FOUND",
                "message": "Registro da aula grátis não encontrado.",
            },
        )

    cancelled_outside_reschedule_policy = not can_reschedule

    db.execute(
        text(
            """
            UPDATE public.events
            SET status = 'cancelado'
            WHERE id = :event_id
            """
        ),
        {"event_id": row["event_id"]},
    )

    trial.status = "cancelled"
    trial.cancelled_at = datetime.now(_local_tz())

    occurrence_type = "cancelled_late" if cancelled_outside_reschedule_policy else "cancelled"

    requires_admin_approval = _record_trial_occurrence(
        db,
        user=current_user,
        trial_lesson_id=trial.id,
        occurrence_type=occurrence_type,
        description="Cancelamento realizado pelo portal.",
    )

    db.commit()
    db.refresh(trial)

    message = "Seu agendamento da aula grátis foi cancelado com sucesso."
    if cancelled_outside_reschedule_policy:
        message = (
            "Seu agendamento da aula grátis foi cancelado com sucesso. "
            "O cancelamento ocorreu fora da janela ideal de remarcação, mas a agenda foi liberada."
        )

    if requires_admin_approval:
        message = f"{message} Seus próximos agendamentos dependerão de aprovação da equipe."

    return TrialLessonCancelOut(
        trial_lesson_id=str(trial.id),
        event_id=str(row["event_id"]),
        status=trial.status,
        message=message,
        cancelled_outside_reschedule_policy=cancelled_outside_reschedule_policy,
        requires_admin_approval=requires_admin_approval,
    )


@router.post("/reschedule", response_model=TrialLessonRescheduleOut)
def reschedule_trial_lesson(
    data: TrialLessonRescheduleIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    current_user = _get_user_or_404(db, UUID(user_id))

    row = _get_current_scheduled_trial_row(db, current_user.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "TRIAL_LESSON_NOT_FOUND",
                "message": "Você não possui aula grátis agendada no momento.",
            },
        )

    _can_cancel, can_reschedule, _deadline_at, _rule_message, status_message = _get_change_policy(
        row["start_at"]
    )

    if not can_reschedule:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIAL_RESCHEDULE_WINDOW_EXPIRED",
                "message": status_message,
            },
        )

    control = _get_trial_control_state(db, current_user)
    if control and bool(control["requires_admin_approval"]):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIAL_ADMIN_APPROVAL_REQUIRED",
                "message": "Não foi possível concluir uma nova remarcação automática. Entre em contato com a escola para validar o próximo horário.",
            },
        )

    if data.end_at <= data.start_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_TIME_RANGE",
                "message": "end_at precisa ser maior que start_at.",
            },
        )

    _validate_trial_slot_duration(data.start_at, data.end_at)
    _validate_trial_date_window(data.start_at.astimezone(_local_tz()).date())
    _validate_trial_not_in_past(data.start_at)

    if not _slot_is_still_available(
        db=db,
        start_at=data.start_at,
        end_at=data.end_at,
        court_id=data.court_id,
        teacher_id=data.teacher_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SLOT_NO_LONGER_AVAILABLE",
                "message": "O horário selecionado não está mais disponível. Atualize a agenda e escolha outro slot.",
            },
        )

    trial = db.get(TrialLesson, row["trial_lesson_id"])
    if not trial:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "TRIAL_LESSON_NOT_FOUND",
                "message": "Registro da aula grátis não encontrado.",
            },
        )

    old_event_id = row["event_id"]

    try:
        db.execute(
            text(
                """
                UPDATE public.events
                SET status = 'cancelado'
                WHERE id = :event_id
                """
            ),
            {"event_id": old_event_id},
        )

        new_event_row = (
            db.execute(
                text(
                    """
                    INSERT INTO public.events (
                      court_id, teacher_id, student_id, created_by,
                      kind, status, start_at, end_at, notes
                    )
                    VALUES (
                      :court_id, :teacher_id, :student_id, :created_by,
                      :kind, :status, :start_at, :end_at, :notes
                    )
                    RETURNING
                      id, court_id, teacher_id, student_id, created_by,
                      kind, status, start_at, end_at, notes, created_at, updated_at
                    """
                ),
                {
                    "court_id": data.court_id,
                    "teacher_id": data.teacher_id,
                    "student_id": None,
                    "created_by": current_user.id,
                    "kind": "primeira_aula",
                    "status": "confirmado",
                    "start_at": data.start_at,
                    "end_at": data.end_at,
                    "notes": _normalize_notes(data.notes) or "Primeira aula remarcada pelo portal.",
                },
            )
            .mappings()
            .first()
        )

        trial.event_id = new_event_row["id"]
        trial.status = "scheduled"
        trial.scheduled_at = data.start_at
        trial.notes = _normalize_notes(data.notes)

        requires_admin_approval = _record_trial_occurrence(
            db,
            user=current_user,
            trial_lesson_id=trial.id,
            occurrence_type="rescheduled",
            description="Remarcação realizada pelo portal.",
        )

        db.commit()
        db.refresh(trial)

        message = "Sua aula grátis foi remarcada com sucesso."
        if requires_admin_approval:
            message = (
                "Sua aula grátis foi remarcada com sucesso. "
                "Seus próximos agendamentos dependerão de aprovação da equipe."
            )

        return TrialLessonRescheduleOut(
            trial_lesson_id=str(trial.id),
            old_event_id=str(old_event_id),
            new_event_id=str(new_event_row["id"]),
            status=trial.status,
            start_at=new_event_row["start_at"],
            end_at=new_event_row["end_at"],
            court_id=new_event_row["court_id"],
            teacher_id=new_event_row["teacher_id"],
            message=message,
        )

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.post("/request", response_model=TrialLessonRequestOut, status_code=status.HTTP_201_CREATED)
def request_trial_lesson(
    data: TrialLessonRequestIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    current_user = _get_user_or_404(db, UUID(user_id))

    reason_code, message, _current_status = _get_trial_block_reason(db, current_user)
    if reason_code is not None:
        _raise_trial_block(reason_code, message)

    existing_requested = _get_latest_requested_trial(db, current_user.id)
    if existing_requested:
        existing_requested.notes = _normalize_notes(data.notes)
        db.commit()
        db.refresh(existing_requested)

        return TrialLessonRequestOut(
            id=str(existing_requested.id),
            user_id=str(existing_requested.user_id),
            status=existing_requested.status,
            message="Sua solicitação de aula grátis já estava em andamento.",
        )

    trial = TrialLesson(
        user_id=current_user.id,
        status="requested",
        notes=_normalize_notes(data.notes),
    )

    db.add(trial)
    db.commit()
    db.refresh(trial)

    return TrialLessonRequestOut(
        id=str(trial.id),
        user_id=str(trial.user_id),
        status=trial.status,
        message="Sua solicitação de aula grátis foi registrada com sucesso.",
    )

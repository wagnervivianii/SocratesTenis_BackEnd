from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import MessageOut
from app.schemas.teachers import (
    TeacherAgendaWeekItemOut,
    TeacherAvailabilityExceptionOut,
    TeacherAvailabilityRuleOut,
    TeacherCreateIn,
    TeacherListItemOut,
    TeacherOut,
    TeacherStatusChangeIn,
    TeacherStatusHistoryItemOut,
    TeacherUpdateIn,
)
from app.services.email_sender import (
    ConsoleEmailSender,
    EmailSendError,
    SmtpConfig,
    SmtpEmailSender,
)
from app.services.password_reset import PasswordResetService

router = APIRouter(prefix="/teachers")

BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")


def _normalize_role(value: str | None) -> str:
    return (value or "").strip().lower()


def _get_email_sender():
    if settings.email_sender_backend.lower() == "smtp":
        cfg = SmtpConfig(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            mail_from=settings.smtp_from,
            use_tls=settings.smtp_use_tls,
        )
        return SmtpEmailSender(cfg)
    return ConsoleEmailSender()


def _build_teacher_first_access_link(*, token: str, email: str) -> str:
    query = f"token={token}&email={email}"
    return f"{settings.frontend_url}/primeiro-acesso?{query}"


def _build_teacher_login_link(email: str) -> str:
    return f"{settings.frontend_url}/login?email={email}"


def _issue_first_access_token(db: Session, user: User) -> str | None:
    if user.password_hash:
        return None

    svc = PasswordResetService(ttl_minutes=getattr(settings, "password_reset_ttl_minutes", 30))
    issued = svc.issue_for_user(db, user.id, ip=None, user_agent="teacher-access-invite")
    return issued.token


def _find_other_teacher_for_user(db: Session, *, teacher_id: UUID, user_id: UUID):
    return (
        db.execute(
            text(
                """
                SELECT id, full_name
                FROM public.teachers
                WHERE user_id = :user_id
                  AND id <> :teacher_id
                LIMIT 1
                """
            ),
            {"teacher_id": teacher_id, "user_id": user_id},
        )
        .mappings()
        .first()
    )


def _find_student_by_email(db: Session, *, email: str):
    return (
        db.execute(
            text(
                """
                SELECT id, full_name, email, user_id, is_active
                FROM public.students
                WHERE lower(email) = :email
                LIMIT 1
                """
            ),
            {"email": email},
        )
        .mappings()
        .first()
    )


def _ensure_email_not_used_by_student(
    db: Session,
    *,
    email: str | None,
    teacher_id: UUID | None = None,
) -> None:
    normalized_email = str(email or "").strip().lower()
    if not normalized_email:
        return

    conflict = _find_student_by_email(db, email=normalized_email)
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este e-mail já está cadastrado para um aluno. "
                "Cada e-mail pode pertencer a apenas um grupo no sistema."
            ),
        )


def _normalize_optional_teacher_email(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _ensure_teacher_user_account(*, db: Session, teacher_row) -> User:
    teacher_email = str(teacher_row["email"] or "").strip().lower()
    if not teacher_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cadastre um e-mail válido para o professor antes de enviar o convite de acesso.",
        )

    _ensure_email_not_used_by_student(
        db,
        email=teacher_email,
        teacher_id=teacher_row["id"],
    )

    linked_user_id = teacher_row["user_id"]
    if linked_user_id:
        linked_user = db.get(User, linked_user_id)
        if not linked_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="O professor está vinculado a uma conta inexistente. Revise o cadastro antes de enviar o convite.",
            )

        if str(linked_user.email).strip().lower() != teacher_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="O e-mail do professor não confere com a conta vinculada. Revise o cadastro antes de enviar o convite.",
            )

        if _find_other_teacher_for_user(db, teacher_id=teacher_row["id"], user_id=linked_user.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Esta conta já está vinculada a outro professor. Revise manualmente antes de prosseguir.",
            )

        if _normalize_role(linked_user.role) != "admin":
            linked_user.role = "coach"
        linked_user.is_active = True
        linked_user.full_name = linked_user.full_name or teacher_row["full_name"]
        return linked_user

    existing_user = db.scalar(select(User).where(User.email == teacher_email))
    if existing_user is not None:
        if _find_other_teacher_for_user(db, teacher_id=teacher_row["id"], user_id=existing_user.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe outro professor vinculado a esta conta. Revise manualmente antes de prosseguir.",
            )

        existing_role = _normalize_role(existing_user.role)
        if existing_role in {"student", "aluno"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe uma conta de aluno com este e-mail. Revise manualmente antes de liberar o acesso do professor.",
            )

        if existing_role != "admin":
            existing_user.role = "coach"
        existing_user.is_active = True
        existing_user.full_name = existing_user.full_name or teacher_row["full_name"]

        db.execute(
            text(
                """
                UPDATE public.teachers
                SET user_id = :user_id, updated_at = now()
                WHERE id = :teacher_id
                """
            ),
            {"teacher_id": teacher_row["id"], "user_id": existing_user.id},
        )
        return existing_user

    new_user = User(
        email=teacher_email,
        password_hash=None,
        full_name=teacher_row["full_name"],
        role="coach",
        is_active=True,
        email_verified_at=None,
    )
    db.add(new_user)
    db.flush()

    db.execute(
        text(
            """
            UPDATE public.teachers
            SET user_id = :user_id, updated_at = now()
            WHERE id = :teacher_id
            """
        ),
        {"teacher_id": teacher_row["id"], "user_id": new_user.id},
    )

    return new_user


def _send_teacher_access_email(
    *, to_email: str, teacher_name: str, access_link: str, first_access: bool
) -> None:
    subject = "Sócrates Tênis — Acesso da agenda do professor"
    cta_label = "Criar senha e acessar agenda" if first_access else "Acessar agenda do professor"
    intro = (
        "Seu acesso como professor foi liberado pela equipe da Sócrates Tênis."
        if first_access
        else "Seu acesso à agenda do professor foi atualizado pela equipe da Sócrates Tênis."
    )
    guidance = (
        "No primeiro acesso, você definirá sua própria senha antes de entrar na área do professor."
        if first_access
        else "Use o botão abaixo para entrar na área do professor com seu e-mail e senha atuais."
    )

    text_body = (
        f"Olá, {teacher_name}!\n\n"
        f"{intro}\n\n"
        "Use o link abaixo para continuar:\n\n"
        f"{access_link}\n\n"
        f"{guidance}\n"
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.5;color:#0f172a">
      <h2 style="margin:0 0 12px;color:#0b5fff">Sócrates Tênis</h2>
      <p>Olá, <strong>{teacher_name}</strong>!</p>
      <p>{intro}</p>
      <p>Use o botão abaixo para continuar:</p>
      <p>
        <a href="{access_link}"
           style="display:inline-block;padding:10px 14px;background:#0b5fff;color:#fff;text-decoration:none;border-radius:8px">
          {cta_label}
        </a>
      </p>
      <p style="font-size:12px;color:#475569">{guidance}</p>
    </div>
    """

    sender = _get_email_sender()
    try:
        sender.send_email(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )
    except EmailSendError as exc:
        print(f"[EMAIL][TEACHER-ACCESS][ERROR] to={to_email} err={exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível enviar o convite de acesso do professor. Tente novamente em instantes.",
        ) from None


def _resolve_teacher_agenda_window(
    view: Literal["day", "week", "month"], reference_date: date
) -> tuple[datetime, datetime]:
    if view == "day":
        window_start = datetime.combine(reference_date, time.min, tzinfo=BRAZIL_TZ)
        return window_start, window_start + timedelta(days=1)

    if view == "month":
        month_start = reference_date.replace(day=1)
        if month_start.month == 12:
            next_month_start = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month_start = month_start.replace(month=month_start.month + 1)

        window_start = datetime.combine(month_start, time.min, tzinfo=BRAZIL_TZ)
        window_end = datetime.combine(next_month_start, time.min, tzinfo=BRAZIL_TZ)
        return window_start, window_end

    window_start = datetime.combine(reference_date, time.min, tzinfo=BRAZIL_TZ)
    return window_start, window_start + timedelta(days=7)


def _get_teacher_agenda_rows(
    db: Session,
    *,
    teacher_id: UUID,
    view: Literal["day", "week", "month"],
    reference_date: date,
):
    window_start, window_end = _resolve_teacher_agenda_window(view, reference_date)

    rows = (
        db.execute(
            text(
                """
                SELECT
                  ev.id AS event_id,
                  ev.kind,
                  ev.status,
                  ev.start_at,
                  ev.end_at,
                  ev.notes,
                  ev.court_id,
                  c.name AS court_name,
                  ev.teacher_id,
                  t.full_name AS teacher_name,
                  ev.student_id,
                  s.full_name AS student_name,
                  ev.class_group_id,
                  cg.name AS class_group_name
                FROM public.events ev
                LEFT JOIN public.courts c
                  ON c.id = ev.court_id
                LEFT JOIN public.teachers t
                  ON t.id = ev.teacher_id
                LEFT JOIN public.students s
                  ON s.id = ev.student_id
                LEFT JOIN public.class_groups cg
                  ON cg.id = ev.class_group_id
                WHERE ev.teacher_id = :teacher_id
                  AND ev.start_at < :window_end
                  AND ev.end_at >= :window_start
                ORDER BY
                  ev.start_at,
                  ev.end_at,
                  ev.id
                """
            ),
            {
                "teacher_id": teacher_id,
                "window_start": window_start,
                "window_end": window_end,
            },
        )
        .mappings()
        .all()
    )

    return rows


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
            detail="Apenas administradores podem gerenciar professores.",
        )


def _integrity_to_http(e: IntegrityError) -> HTTPException:
    orig = getattr(e, "orig", None)
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)

    constraint = None
    diag = getattr(orig, "diag", None)
    if diag is not None:
        constraint = getattr(diag, "constraint_name", None)

    if pgcode == "23503":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Referência inválida para relacionamento informado.",
        )

    if pgcode == "23505":
        if constraint and "email" in constraint.lower():
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um professor com este e-mail.",
            )

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
        detail=f"Erro ao salvar dados do professor: {str(orig) if orig else str(e)}",
    )


def _get_teacher_or_404(db: Session, teacher_id: UUID):
    row = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  user_id,
                  full_name,
                  email,
                  phone,
                  notes,
                  is_active,
                  created_at,
                  updated_at
                FROM public.teachers
                WHERE id = :teacher_id
                """
            ),
            {"teacher_id": teacher_id},
        )
        .mappings()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Professor não encontrado.",
        )

    return row


def _insert_teacher_status_history(
    db: Session,
    *,
    teacher_id: UUID,
    status_value: str,
    changed_by_user_id: str,
    reason_code: str | None = None,
    reason_note: str | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO public.teacher_status_history (
              teacher_id,
              status,
              reason_code,
              reason_note,
              changed_by_user_id
            )
            VALUES (
              :teacher_id,
              :status,
              :reason_code,
              :reason_note,
              :changed_by_user_id
            )
            """
        ),
        {
            "teacher_id": teacher_id,
            "status": status_value,
            "reason_code": reason_code.strip() if reason_code else None,
            "reason_note": reason_note.strip() if reason_note else None,
            "changed_by_user_id": changed_by_user_id,
        },
    )


@router.get("/", response_model=list[TeacherListItemOut])
def list_teachers(
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    is_active: bool | None = None,
    q: str | None = Query(default=None, description="Busca por nome do professor"),
):
    _require_admin(db, user_id)

    params: dict[str, object] = {"is_active": is_active}
    where_parts = ["1 = 1"]

    if is_active is not None:
        where_parts.append("is_active = :is_active")

    if q and q.strip():
        params["q"] = f"%{q.strip()}%"
        where_parts.append("full_name ILIKE :q")

    where_sql = " AND ".join(where_parts)

    rows = (
        db.execute(
            text(
                f"""
                SELECT
                  id,
                  user_id,
                  full_name,
                  email,
                  phone,
                  notes,
                  is_active,
                  created_at,
                  updated_at
                FROM public.teachers
                WHERE {where_sql}
                ORDER BY
                  is_active DESC,
                  full_name
                """
            ),
            params,
        )
        .mappings()
        .all()
    )

    return rows


@router.get("/{teacher_id}", response_model=TeacherOut)
def get_teacher(
    teacher_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    return _get_teacher_or_404(db, teacher_id)


@router.get("/{teacher_id}/status-history", response_model=list[TeacherStatusHistoryItemOut])
def get_teacher_status_history(
    teacher_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_teacher_or_404(db, teacher_id)

    rows = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  teacher_id,
                  status,
                  reason_code,
                  reason_note,
                  changed_by_user_id,
                  created_at
                FROM public.teacher_status_history
                WHERE teacher_id = :teacher_id
                ORDER BY created_at DESC, id DESC
                """
            ),
            {"teacher_id": teacher_id},
        )
        .mappings()
        .all()
    )

    return rows


@router.get("/{teacher_id}/availability-rules", response_model=list[TeacherAvailabilityRuleOut])
def get_teacher_availability_rules(
    teacher_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_teacher_or_404(db, teacher_id)

    rows = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  teacher_id,
                  weekday,
                  start_time,
                  end_time,
                  starts_on,
                  ends_on,
                  modality,
                  court_id,
                  is_active,
                  notes,
                  created_at,
                  updated_at
                FROM public.teacher_availability_rules
                WHERE teacher_id = :teacher_id
                ORDER BY
                  is_active DESC,
                  weekday,
                  start_time,
                  starts_on,
                  id
                """
            ),
            {"teacher_id": teacher_id},
        )
        .mappings()
        .all()
    )

    return rows


@router.get(
    "/{teacher_id}/availability-exceptions",
    response_model=list[TeacherAvailabilityExceptionOut],
)
def get_teacher_availability_exceptions(
    teacher_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_teacher_or_404(db, teacher_id)

    rows = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  teacher_id,
                  start_at,
                  end_at,
                  exception_type,
                  modality,
                  court_id,
                  is_active,
                  reason,
                  created_at,
                  updated_at
                FROM public.teacher_availability_exceptions
                WHERE teacher_id = :teacher_id
                ORDER BY
                  is_active DESC,
                  start_at DESC,
                  end_at DESC,
                  id DESC
                """
            ),
            {"teacher_id": teacher_id},
        )
        .mappings()
        .all()
    )

    return rows


@router.get("/{teacher_id}/agenda", response_model=list[TeacherAgendaWeekItemOut])
def get_teacher_agenda(
    teacher_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    view: Annotated[
        Literal["day", "week", "month"],
        Query(description="Recorte da agenda: day, week ou month."),
    ] = "week",
    reference_date: Annotated[
        date | None,
        Query(description="Data de referência do recorte no formato YYYY-MM-DD"),
    ] = None,
):
    _require_admin(db, user_id)
    _get_teacher_or_404(db, teacher_id)

    agenda_reference_date = reference_date or datetime.now(BRAZIL_TZ).date()
    return _get_teacher_agenda_rows(
        db,
        teacher_id=teacher_id,
        view=view,
        reference_date=agenda_reference_date,
    )


@router.get("/{teacher_id}/agenda-week", response_model=list[TeacherAgendaWeekItemOut])
def get_teacher_agenda_week(
    teacher_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    date_from: Annotated[
        date | None,
        Query(description="Data inicial da janela semanal no formato YYYY-MM-DD"),
    ] = None,
):
    _require_admin(db, user_id)
    _get_teacher_or_404(db, teacher_id)

    reference_date = date_from or datetime.now(BRAZIL_TZ).date()
    return _get_teacher_agenda_rows(
        db,
        teacher_id=teacher_id,
        view="week",
        reference_date=reference_date,
    )


@router.post("/{teacher_id}/access-invite", response_model=MessageOut)
def send_teacher_access_invite(
    teacher_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    teacher = _get_teacher_or_404(db, teacher_id)

    if not teacher["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ative o professor antes de enviar o convite de acesso.",
        )

    teacher_email = str(teacher["email"] or "").strip().lower()
    if not teacher_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cadastre um e-mail válido para o professor antes de enviar o convite de acesso.",
        )

    teacher_name = str(teacher["full_name"] or teacher_email).strip() or teacher_email

    try:
        user = _ensure_teacher_user_account(db=db, teacher_row=teacher)
        token = _issue_first_access_token(db, user)
        access_link = (
            _build_teacher_first_access_link(token=token, email=user.email)
            if token
            else _build_teacher_login_link(user.email)
        )
        _send_teacher_access_email(
            to_email=user.email,
            teacher_name=teacher_name,
            access_link=access_link,
            first_access=bool(token),
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível preparar o acesso do professor.",
        ) from None

    message = (
        "Convite de primeiro acesso enviado com sucesso para o professor."
        if token
        else "O professor já possuía acesso. Reenviamos o link de entrada para o e-mail cadastrado."
    )
    return MessageOut(message=message)


@router.post("/", response_model=TeacherOut, status_code=status.HTTP_201_CREATED)
def create_teacher(
    payload: TeacherCreateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

    normalized_email = _normalize_optional_teacher_email(
        str(payload.email) if payload.email else None
    )
    _ensure_email_not_used_by_student(db, email=normalized_email)

    try:
        row = (
            db.execute(
                text(
                    """
                    INSERT INTO public.teachers (
                      full_name,
                      email,
                      phone,
                      notes,
                      is_active
                    )
                    VALUES (
                      :full_name,
                      :email,
                      :phone,
                      :notes,
                      :is_active
                    )
                    RETURNING
                      id,
                      user_id,
                      full_name,
                      email,
                      phone,
                      notes,
                      is_active,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "full_name": payload.full_name.strip(),
                    "email": normalized_email,
                    "phone": payload.phone.strip() if payload.phone else None,
                    "notes": payload.notes.strip() if payload.notes else None,
                    "is_active": payload.is_active,
                },
            )
            .mappings()
            .first()
        )

        _insert_teacher_status_history(
            db,
            teacher_id=row["id"],
            status_value="active" if row["is_active"] else "inactive",
            changed_by_user_id=user_id,
            reason_code="created",
            reason_note="Cadastro inicial do professor.",
        )

        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.patch("/{teacher_id}", response_model=TeacherOut)
def update_teacher(
    teacher_id: UUID,
    payload: TeacherUpdateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

    current = _get_teacher_or_404(db, teacher_id)

    merged = {
        "full_name": payload.full_name if payload.full_name is not None else current["full_name"],
        "email": (
            _normalize_optional_teacher_email(str(payload.email))
            if payload.email is not None
            else current["email"]
        ),
        "phone": payload.phone.strip() if payload.phone is not None else current["phone"],
        "notes": payload.notes.strip() if payload.notes is not None else current["notes"],
        "is_active": payload.is_active if payload.is_active is not None else current["is_active"],
    }

    _ensure_email_not_used_by_student(db, email=merged["email"], teacher_id=teacher_id)

    try:
        row = (
            db.execute(
                text(
                    """
                    UPDATE public.teachers
                    SET
                      full_name = :full_name,
                      email = :email,
                      phone = :phone,
                      notes = :notes,
                      is_active = :is_active,
                      updated_at = now()
                    WHERE id = :teacher_id
                    RETURNING
                      id,
                      user_id,
                      full_name,
                      email,
                      phone,
                      notes,
                      is_active,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "teacher_id": teacher_id,
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


@router.patch("/{teacher_id}/deactivate", response_model=TeacherOut)
def deactivate_teacher(
    teacher_id: UUID,
    payload: TeacherStatusChangeIn | None,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    current = _get_teacher_or_404(db, teacher_id)

    if not current["is_active"]:
        return current

    row = (
        db.execute(
            text(
                """
                UPDATE public.teachers
                SET
                  is_active = FALSE,
                  updated_at = now()
                WHERE id = :teacher_id
                RETURNING
                  id,
                  user_id,
                  full_name,
                  email,
                  phone,
                  notes,
                  is_active,
                  created_at,
                  updated_at
                """
            ),
            {"teacher_id": teacher_id},
        )
        .mappings()
        .first()
    )

    _insert_teacher_status_history(
        db,
        teacher_id=teacher_id,
        status_value="inactive",
        changed_by_user_id=user_id,
        reason_code=payload.reason_code if payload else None,
        reason_note=payload.reason_note if payload else None,
    )

    db.commit()
    return row


@router.patch("/{teacher_id}/reactivate", response_model=TeacherOut)
def reactivate_teacher(
    teacher_id: UUID,
    payload: TeacherStatusChangeIn | None,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    current = _get_teacher_or_404(db, teacher_id)

    if current["is_active"]:
        return current

    row = (
        db.execute(
            text(
                """
                UPDATE public.teachers
                SET
                  is_active = TRUE,
                  updated_at = now()
                WHERE id = :teacher_id
                RETURNING
                  id,
                  user_id,
                  full_name,
                  email,
                  phone,
                  notes,
                  is_active,
                  created_at,
                  updated_at
                """
            ),
            {"teacher_id": teacher_id},
        )
        .mappings()
        .first()
    )

    _insert_teacher_status_history(
        db,
        teacher_id=teacher_id,
        status_value="active",
        changed_by_user_id=user_id,
        reason_code=payload.reason_code if payload else None,
        reason_note=payload.reason_note if payload else None,
    )

    db.commit()
    return row

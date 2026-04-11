from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.models.student import Student
from app.models.student_signup_request import StudentSignupRequest
from app.models.user import User
from app.schemas.student_signup_requests import (
    StudentSignupRequestCreateIn,
    StudentSignupRequestCreateOut,
    StudentSignupRequestListItemOut,
    StudentSignupRequestOut,
    StudentSignupRequestReviewIn,
    StudentSignupRequestReviewOut,
)
from app.services.email_sender import (
    ConsoleEmailSender,
    EmailSendError,
    SmtpConfig,
    SmtpEmailSender,
)
from app.services.password_reset import PasswordResetService

router = APIRouter(prefix="/student-signup-requests")

DBSession = Annotated[Session, Depends(get_db)]
CurrentUserId = Annotated[str, Depends(get_current_user_id)]


def _only_digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = " ".join(value.strip().split())
    return normalized or None


def _normalize_name(value: str, *, field_label: str) -> str:
    raw = _normalize_optional_text(value)
    if not raw or len(raw) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_label} inválido.",
        )

    letters_only = "".join(ch for ch in raw if ch.isalpha() or ch.isspace())
    normalized = " ".join(letters_only.split()).upper()
    if len(normalized) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_label} deve conter apenas letras e espaços.",
        )

    return normalized


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _normalize_instagram(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if not normalized:
        return None

    handle = normalized.removeprefix("@").strip().lower()
    return handle or None


def _normalize_zip_code(value: str) -> str:
    digits = _only_digits(value)
    if len(digits) != 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Informe um CEP válido com 8 dígitos.",
        )
    return digits


def _normalize_whatsapp(value: str, *, field_label: str) -> str:
    digits = _only_digits(value)
    if len(digits) not in (10, 11):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_label} inválido. Use DDD + número.",
        )
    return digits


def _calculate_age(birth_date) -> int:
    today = datetime.now(UTC).date()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def _is_minor(birth_date) -> bool:
    return _calculate_age(birth_date) < 18


def _require_admin(db: Session, user_id: str) -> None:
    user = (
        db.execute(
            text(
                """
                SELECT id, role, is_active
                FROM public.users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        .mappings()
        .first()
    )

    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário inválido.",
        )

    role = str(user["role"] or "").strip().lower()
    if not role.startswith("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem revisar solicitações de alunos.",
        )


def _resolve_email_confirmed_at(
    *,
    request: StudentSignupRequest,
    approved_user: User | None,
):
    if request.status != "approved":
        return None
    if approved_user is None:
        return None
    return approved_user.email_verified_at


def _resolve_email_confidence_status(
    *,
    request: StudentSignupRequest,
    approved_user: User | None,
) -> str:
    if request.status == "pending":
        return "awaiting_review"
    if request.status == "rejected":
        return "rejected"
    if approved_user and approved_user.email_verified_at is not None:
        return "confirmed"
    return "pending_confirmation"


def _to_list_item_out(
    request: StudentSignupRequest,
    *,
    approved_user: User | None = None,
) -> StudentSignupRequestListItemOut:
    email_confirmed_at = _resolve_email_confirmed_at(
        request=request,
        approved_user=approved_user,
    )
    email_confidence_status = _resolve_email_confidence_status(
        request=request,
        approved_user=approved_user,
    )

    return StudentSignupRequestListItemOut(
        id=request.id,
        full_name=request.full_name,
        email=request.email,
        whatsapp=request.whatsapp,
        instagram=request.instagram,
        birth_date=request.birth_date,
        zip_code=request.zip_code,
        guardian_full_name=request.guardian_full_name,
        guardian_whatsapp=request.guardian_whatsapp,
        guardian_relationship=request.guardian_relationship,
        status=request.status,
        review_note=request.review_note,
        reviewed_at=request.reviewed_at,
        reviewed_by_user_id=request.reviewed_by_user_id,
        approved_user_id=request.approved_user_id,
        approved_student_id=request.approved_student_id,
        email_confidence_status=email_confidence_status,
        email_confirmed_at=email_confirmed_at,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )


def _get_request_or_404(db: Session, request_id: UUID) -> StudentSignupRequest:
    request = db.get(StudentSignupRequest, request_id)
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação de aluno não encontrada.",
        )
    return request


def _get_approved_user_for_request(
    db: Session,
    request: StudentSignupRequest,
) -> User | None:
    if request.approved_user_id is None:
        return None
    return db.get(User, request.approved_user_id)


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


def _build_first_access_link(*, token: str, email: str) -> str:
    query = urlencode({"token": token, "email": email})
    return f"{settings.frontend_url}/primeiro-acesso?{query}"


def _build_login_link(*, email: str) -> str:
    query = urlencode({"email": email})
    return f"{settings.frontend_url}/login?{query}"


def _protected_non_student_role(role: str | None) -> bool:
    value = (role or "").strip().lower()
    if not value:
        return False
    if value.startswith("admin"):
        return True
    if value in {"coach", "teacher", "professor", "prof", "employee", "collaborator"}:
        return True
    return False


def _create_or_update_user_for_approved_request(
    *,
    db: Session,
    request: StudentSignupRequest,
) -> User:
    existing_user = db.scalar(select(User).where(User.email == request.email))

    whatsapp_owner = db.scalar(select(User).where(User.whatsapp == request.whatsapp))
    if whatsapp_owner is not None and (
        existing_user is None or whatsapp_owner.id != existing_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um usuário com o WhatsApp informado nesta solicitação.",
        )

    if existing_user is None:
        user = User(
            email=request.email,
            password_hash=None,
            full_name=request.full_name,
            whatsapp=request.whatsapp,
            instagram=request.instagram,
            birth_date=request.birth_date,
            zip_code=request.zip_code,
            guardian_full_name=request.guardian_full_name,
            guardian_whatsapp=request.guardian_whatsapp,
            guardian_relationship=request.guardian_relationship,
            role="student",
            is_active=True,
            email_verified_at=None,
        )
        db.add(user)
        db.flush()
        return user

    if _protected_non_student_role(existing_user.role):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Já existe uma conta institucional com este e-mail. Revise manualmente antes de aprovar como aluno."
            ),
        )

    existing_user.full_name = existing_user.full_name or request.full_name
    existing_user.whatsapp = request.whatsapp or existing_user.whatsapp
    existing_user.instagram = existing_user.instagram or request.instagram
    existing_user.birth_date = existing_user.birth_date or request.birth_date
    existing_user.zip_code = existing_user.zip_code or request.zip_code
    existing_user.guardian_full_name = (
        existing_user.guardian_full_name or request.guardian_full_name
    )
    existing_user.guardian_whatsapp = existing_user.guardian_whatsapp or request.guardian_whatsapp
    existing_user.guardian_relationship = (
        existing_user.guardian_relationship or request.guardian_relationship
    )
    existing_user.is_active = True
    existing_user.role = "student"
    existing_user.updated_at = datetime.now(UTC)

    return existing_user


def _insert_student_status_history(
    db: Session,
    *,
    student_id: UUID,
    status_value: str,
    changed_by_user_id: str,
    reason_code: str | None = None,
    reason_note: str | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO public.student_status_history (
              student_id,
              status,
              reason_code,
              reason_note,
              changed_by_user_id
            )
            VALUES (
              :student_id,
              :status,
              :reason_code,
              :reason_note,
              :changed_by_user_id
            )
            """
        ),
        {
            "student_id": student_id,
            "status": status_value,
            "reason_code": reason_code.strip() if reason_code else None,
            "reason_note": reason_note.strip() if reason_note else None,
            "changed_by_user_id": changed_by_user_id,
        },
    )


def _create_or_update_student_for_approved_request(
    *,
    db: Session,
    request: StudentSignupRequest,
    user: User,
    reviewed_by_user_id: str,
) -> Student:
    existing_student = db.scalar(select(Student).where(Student.email == request.email))

    if existing_student is None:
        student = Student(
            user_id=user.id,
            full_name=request.full_name,
            email=request.email,
            phone=request.whatsapp,
            notes="Cadastro aprovado a partir de solicitação pública de aluno.",
            profession=None,
            instagram_handle=request.instagram,
            share_profession=False,
            share_instagram=False,
            is_active=True,
        )
        db.add(student)
        db.flush()
        _insert_student_status_history(
            db,
            student_id=student.id,
            status_value="active",
            changed_by_user_id=reviewed_by_user_id,
            reason_code="signup_approved",
            reason_note="Aluno criado a partir da aprovação da solicitação pública de cadastro.",
        )
        return student

    was_active = bool(existing_student.is_active)

    if existing_student.user_id is None:
        existing_student.user_id = user.id

    existing_student.full_name = existing_student.full_name or request.full_name
    existing_student.phone = existing_student.phone or request.whatsapp
    existing_student.instagram_handle = existing_student.instagram_handle or request.instagram
    existing_student.is_active = True

    if not was_active:
        db.flush()
        _insert_student_status_history(
            db,
            student_id=existing_student.id,
            status_value="active",
            changed_by_user_id=reviewed_by_user_id,
            reason_code="signup_approved",
            reason_note="Aluno reativado a partir da aprovação da solicitação pública de cadastro.",
        )

    return existing_student


def _issue_first_access_token(db: Session, user: User) -> str | None:
    if user.password_hash:
        return None

    svc = PasswordResetService(ttl_minutes=getattr(settings, "password_reset_ttl_minutes", 30))
    issued = svc.issue_for_user(db, user.id, ip=None, user_agent="student-signup-approval")
    return issued.token


def _send_received_email(request: StudentSignupRequest) -> None:
    sender = _get_email_sender()
    try:
        sender.send_student_signup_received_email(
            to_email=request.email,
            student_name=request.full_name,
        )
    except EmailSendError as exc:
        print(
            f"[EMAIL][STUDENT_SIGNUP][RECEIVED][ERROR] to={request.email} request={request.id} err={exc}"
        )


def _send_approved_email(*, db: Session, request: StudentSignupRequest, user: User) -> None:
    sender = _get_email_sender()
    token = _issue_first_access_token(db=db, user=user)
    login_link = (
        _build_first_access_link(token=token, email=user.email)
        if token
        else _build_login_link(email=user.email)
    )

    try:
        sender.send_student_signup_approved_email(
            to_email=user.email,
            student_name=request.full_name,
            login_link=login_link,
        )
    except EmailSendError as exc:
        print(
            f"[EMAIL][STUDENT_SIGNUP][APPROVED][ERROR] to={user.email} request={request.id} err={exc}"
        )


def _send_rejected_email(request: StudentSignupRequest) -> None:
    sender = _get_email_sender()
    contact_email = settings.smtp_from or None
    try:
        sender.send_student_signup_rejected_email(
            to_email=request.email,
            student_name=request.full_name,
            contact_email=contact_email,
        )
    except EmailSendError as exc:
        print(
            f"[EMAIL][STUDENT_SIGNUP][REJECTED][ERROR] to={request.email} request={request.id} err={exc}"
        )


@router.post("", response_model=StudentSignupRequestCreateOut, status_code=status.HTTP_201_CREATED)
def create_student_signup_request(data: StudentSignupRequestCreateIn, db: DBSession):
    normalized_email = _normalize_email(str(data.email))
    normalized_full_name = _normalize_name(data.full_name, field_label="Nome completo")
    normalized_whatsapp = _normalize_whatsapp(data.whatsapp, field_label="WhatsApp")
    normalized_zip_code = _normalize_zip_code(data.zip_code)
    normalized_instagram = _normalize_instagram(data.instagram)

    if data.birth_date > datetime.now(UTC).date():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Data de nascimento inválida.",
        )

    guardian_full_name = None
    guardian_whatsapp = None
    guardian_relationship = None

    if _is_minor(data.birth_date):
        guardian_full_name = _normalize_name(
            data.guardian_full_name or "",
            field_label="Nome do responsável",
        )
        guardian_whatsapp = _normalize_whatsapp(
            data.guardian_whatsapp or "",
            field_label="Telefone do responsável",
        )
        guardian_relationship = _normalize_optional_text(data.guardian_relationship)
        if not guardian_relationship:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Selecione o parentesco do responsável.",
            )
        guardian_relationship = guardian_relationship.upper()

        if guardian_whatsapp == normalized_whatsapp:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="O telefone do responsável deve ser diferente do telefone do aluno.",
            )

    existing_student = db.scalar(select(Student).where(Student.email == normalized_email))
    if existing_student is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um aluno cadastrado com este e-mail. Aguarde a ativação ou faça login se já tiver acesso.",
        )

    existing_pending_request = db.scalar(
        select(StudentSignupRequest).where(
            StudentSignupRequest.status == "pending",
            or_(
                StudentSignupRequest.email == normalized_email,
                StudentSignupRequest.whatsapp == normalized_whatsapp,
            ),
        )
    )
    if existing_pending_request is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe uma solicitação pendente para este aluno. Aguarde a conferência da equipe.",
        )

    existing_rejected_request = db.scalar(
        select(StudentSignupRequest).where(
            StudentSignupRequest.status == "rejected",
            or_(
                StudentSignupRequest.email == normalized_email,
                StudentSignupRequest.whatsapp == normalized_whatsapp,
            ),
        )
    )
    if existing_rejected_request is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe uma solicitação anterior não aprovada para este cadastro. Entre em contato com a escola para mais informações.",
        )

    request = StudentSignupRequest(
        full_name=normalized_full_name,
        email=normalized_email,
        whatsapp=normalized_whatsapp,
        instagram=normalized_instagram,
        birth_date=data.birth_date,
        zip_code=normalized_zip_code,
        guardian_full_name=guardian_full_name,
        guardian_whatsapp=guardian_whatsapp,
        guardian_relationship=guardian_relationship,
        status="pending",
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    _send_received_email(request)

    return StudentSignupRequestCreateOut(request_id=request.id, status="pending")


@router.get("", response_model=list[StudentSignupRequestListItemOut])
def list_student_signup_requests(
    db: DBSession,
    user_id: CurrentUserId,
    status_filter: str | None = Query(default=None, alias="status"),
):
    _require_admin(db, user_id)

    stmt = select(StudentSignupRequest).order_by(StudentSignupRequest.created_at.desc())

    if status_filter:
        normalized_status = status_filter.strip().lower()
        if normalized_status not in {"pending", "approved", "rejected"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Status inválido. Use pending, approved ou rejected.",
            )
        stmt = stmt.where(StudentSignupRequest.status == normalized_status)

    requests = db.scalars(stmt).all()

    approved_user_ids = {
        request.approved_user_id for request in requests if request.approved_user_id is not None
    }
    approved_user_map: dict[UUID, User] = {}
    if approved_user_ids:
        approved_users = db.scalars(select(User).where(User.id.in_(approved_user_ids))).all()
        approved_user_map = {user.id: user for user in approved_users}

    return [
        _to_list_item_out(
            item,
            approved_user=approved_user_map.get(item.approved_user_id),
        )
        for item in requests
    ]


@router.get("/{request_id}", response_model=StudentSignupRequestOut)
def get_student_signup_request(
    request_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
):
    _require_admin(db, user_id)
    request = _get_request_or_404(db, request_id)
    approved_user = _get_approved_user_for_request(db, request)
    return StudentSignupRequestOut(
        **_to_list_item_out(request, approved_user=approved_user).model_dump()
    )


@router.post("/{request_id}/review", response_model=StudentSignupRequestReviewOut)
def review_student_signup_request(
    request_id: UUID,
    payload: StudentSignupRequestReviewIn,
    db: DBSession,
    user_id: CurrentUserId,
):
    _require_admin(db, user_id)

    request = _get_request_or_404(db, request_id)
    if request.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta solicitação já foi revisada.",
        )

    reviewed_at = datetime.now(UTC)
    request.reviewed_at = reviewed_at
    request.reviewed_by_user_id = UUID(user_id)
    request.review_note = _normalize_optional_text(payload.review_note)

    if payload.action == "reject":
        request.status = "rejected"
        db.commit()
        db.refresh(request)
        _send_rejected_email(request)

        review_payload = {
            "id": request.id,
            "status": "rejected",
            "reviewed_at": request.reviewed_at,
            "reviewed_by_user_id": request.reviewed_by_user_id,
            "approved_user_id": None,
            "approved_student_id": None,
            "email_confidence_status": "rejected",
            "email_confirmed_at": None,
            "message": "Solicitação rejeitada com sucesso.",
        }
        return StudentSignupRequestReviewOut(**review_payload)

    user = _create_or_update_user_for_approved_request(db=db, request=request)
    student = _create_or_update_student_for_approved_request(
        db=db,
        request=request,
        user=user,
        reviewed_by_user_id=user_id,
    )

    request.status = "approved"
    request.approved_user_id = user.id
    request.approved_student_id = student.id

    db.commit()
    db.refresh(request)
    db.refresh(user)

    _send_approved_email(db=db, request=request, user=user)

    review_payload = {
        "id": request.id,
        "status": "approved",
        "reviewed_at": request.reviewed_at,
        "reviewed_by_user_id": request.reviewed_by_user_id,
        "approved_user_id": request.approved_user_id,
        "approved_student_id": request.approved_student_id,
        "email_confidence_status": _resolve_email_confidence_status(
            request=request,
            approved_user=user,
        ),
        "email_confirmed_at": _resolve_email_confirmed_at(
            request=request,
            approved_user=user,
        ),
        "message": "Solicitação aprovada com sucesso.",
    }
    return StudentSignupRequestReviewOut(**review_payload)

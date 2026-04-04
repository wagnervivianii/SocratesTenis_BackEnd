from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
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


def _to_list_item_out(request: StudentSignupRequest) -> StudentSignupRequestListItemOut:
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
            detail="Já existe um aluno cadastrado com este e-mail.",
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
    return [_to_list_item_out(item) for item in requests]


@router.get("/{request_id}", response_model=StudentSignupRequestOut)
def get_student_signup_request(
    request_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
):
    _require_admin(db, user_id)
    request = _get_request_or_404(db, request_id)
    return StudentSignupRequestOut(**_to_list_item_out(request).model_dump())


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
        return StudentSignupRequestReviewOut(
            id=request.id,
            status="rejected",
            reviewed_at=request.reviewed_at,
            reviewed_by_user_id=request.reviewed_by_user_id,
            approved_user_id=None,
            approved_student_id=None,
            message="Solicitação rejeitada com sucesso.",
        )

    existing_user = db.scalar(select(User).where(User.email == request.email))
    existing_student = db.scalar(select(Student).where(Student.email == request.email))

    if existing_student is None:
        student = Student(
            user_id=existing_user.id if existing_user is not None else None,
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
    else:
        student = existing_student
        if student.user_id is None and existing_user is not None:
            student.user_id = existing_user.id
        if (not student.phone) and request.whatsapp:
            student.phone = request.whatsapp
        if (not student.instagram_handle) and request.instagram:
            student.instagram_handle = request.instagram

    request.status = "approved"
    request.approved_user_id = existing_user.id if existing_user is not None else None
    request.approved_student_id = student.id

    db.commit()
    db.refresh(request)

    return StudentSignupRequestReviewOut(
        id=request.id,
        status="approved",
        reviewed_at=request.reviewed_at,
        reviewed_by_user_id=request.reviewed_by_user_id,
        approved_user_id=request.approved_user_id,
        approved_student_id=request.approved_student_id,
        message="Solicitação aprovada com sucesso.",
    )

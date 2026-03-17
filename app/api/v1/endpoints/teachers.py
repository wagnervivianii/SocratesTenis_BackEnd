from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.teachers import (
    TeacherCreateIn,
    TeacherListItemOut,
    TeacherOut,
    TeacherUpdateIn,
)

router = APIRouter(prefix="/teachers")


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


@router.post("/", response_model=TeacherOut, status_code=status.HTTP_201_CREATED)
def create_teacher(
    payload: TeacherCreateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

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
                    "email": str(payload.email).strip().lower() if payload.email else None,
                    "phone": payload.phone.strip() if payload.phone else None,
                    "notes": payload.notes.strip() if payload.notes else None,
                    "is_active": payload.is_active,
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
            str(payload.email).strip().lower() if payload.email is not None else current["email"]
        ),
        "phone": payload.phone.strip() if payload.phone is not None else current["phone"],
        "notes": payload.notes.strip() if payload.notes is not None else current["notes"],
        "is_active": payload.is_active if payload.is_active is not None else current["is_active"],
    }

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
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_teacher_or_404(db, teacher_id)

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
    db.commit()
    return row

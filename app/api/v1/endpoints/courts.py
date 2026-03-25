from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.courts import (
    CourtCreateIn,
    CourtListItemOut,
    CourtOut,
    CourtStatusChangeIn,
    CourtStatusHistoryItemOut,
    CourtUpdateIn,
)

router = APIRouter(prefix="/courts")


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
            detail="Apenas administradores podem gerenciar quadras.",
        )


def _integrity_to_http(e: IntegrityError) -> HTTPException:
    orig = getattr(e, "orig", None)
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)

    constraint = None
    diag = getattr(orig, "diag", None)
    if diag is not None:
        constraint = getattr(diag, "constraint_name", None)

    if pgcode == "23505":
        if constraint and "name" in constraint.lower():
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe uma quadra com este nome.",
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
        detail=f"Erro ao salvar dados da quadra: {str(orig) if orig else str(e)}",
    )


def _get_court_or_404(db: Session, court_id: UUID):
    row = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  name,
                  is_active,
                  created_at,
                  updated_at
                FROM public.courts
                WHERE id = :court_id
                """
            ),
            {"court_id": court_id},
        )
        .mappings()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quadra não encontrada.",
        )

    return row


def _insert_court_status_history(
    db: Session,
    *,
    court_id: UUID,
    status_value: str,
    changed_by_user_id: str,
    reason_code: str | None = None,
    reason_note: str | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO public.court_status_history (
              court_id,
              status,
              reason_code,
              reason_note,
              changed_by_user_id
            )
            VALUES (
              :court_id,
              :status,
              :reason_code,
              :reason_note,
              :changed_by_user_id
            )
            """
        ),
        {
            "court_id": court_id,
            "status": status_value,
            "reason_code": reason_code.strip() if reason_code else None,
            "reason_note": reason_note.strip() if reason_note else None,
            "changed_by_user_id": changed_by_user_id,
        },
    )


def _validate_status_change_payload(payload: CourtStatusChangeIn | None) -> None:
    if not payload:
        return

    reason_code = payload.reason_code.strip() if payload.reason_code else None
    reason_note = payload.reason_note.strip() if payload.reason_note else None

    if reason_code == "other" and not reason_note:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A observação é obrigatória quando o motivo for 'other'.",
        )


@router.get("/", response_model=list[CourtListItemOut])
def list_courts(
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    is_active: bool | None = None,
    q: str | None = Query(default=None, description="Busca por nome da quadra"),
):
    _require_admin(db, user_id)

    params: dict[str, object] = {"is_active": is_active}
    where_parts = ["1 = 1"]

    if is_active is not None:
        where_parts.append("is_active = :is_active")

    if q and q.strip():
        params["q"] = f"%{q.strip()}%"
        where_parts.append("name ILIKE :q")

    where_sql = " AND ".join(where_parts)

    rows = (
        db.execute(
            text(
                f"""
                SELECT
                  id,
                  name,
                  is_active,
                  created_at,
                  updated_at
                FROM public.courts
                WHERE {where_sql}
                ORDER BY
                  is_active DESC,
                  name
                """
            ),
            params,
        )
        .mappings()
        .all()
    )

    return rows


@router.get("/{court_id}", response_model=CourtOut)
def get_court(
    court_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    return _get_court_or_404(db, court_id)


@router.get("/{court_id}/status-history", response_model=list[CourtStatusHistoryItemOut])
def get_court_status_history(
    court_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_court_or_404(db, court_id)

    rows = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  court_id,
                  status,
                  reason_code,
                  reason_note,
                  changed_by_user_id,
                  created_at
                FROM public.court_status_history
                WHERE court_id = :court_id
                ORDER BY created_at DESC, id DESC
                """
            ),
            {"court_id": court_id},
        )
        .mappings()
        .all()
    )

    return rows


@router.post("/", response_model=CourtOut, status_code=status.HTTP_201_CREATED)
def create_court(
    payload: CourtCreateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

    try:
        row = (
            db.execute(
                text(
                    """
                    INSERT INTO public.courts (
                      name,
                      is_active
                    )
                    VALUES (
                      :name,
                      :is_active
                    )
                    RETURNING
                      id,
                      name,
                      is_active,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "name": payload.name.strip(),
                    "is_active": payload.is_active,
                },
            )
            .mappings()
            .first()
        )

        _insert_court_status_history(
            db,
            court_id=row["id"],
            status_value="active" if row["is_active"] else "inactive",
            changed_by_user_id=user_id,
            reason_code="created",
            reason_note="Cadastro inicial da quadra.",
        )

        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.patch("/{court_id}", response_model=CourtOut)
def update_court(
    court_id: UUID,
    payload: CourtUpdateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

    current = _get_court_or_404(db, court_id)

    if payload.is_active is not None and bool(payload.is_active) != bool(current["is_active"]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use os endpoints específicos de ativação ou inativação para alterar o status da quadra.",
        )

    merged = {
        "name": payload.name.strip() if payload.name is not None else current["name"],
    }

    try:
        row = (
            db.execute(
                text(
                    """
                    UPDATE public.courts
                    SET
                      name = :name,
                      updated_at = now()
                    WHERE id = :court_id
                    RETURNING
                      id,
                      name,
                      is_active,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "court_id": court_id,
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


@router.patch("/{court_id}/deactivate", response_model=CourtOut)
def deactivate_court(
    court_id: UUID,
    payload: CourtStatusChangeIn | None,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _validate_status_change_payload(payload)
    current = _get_court_or_404(db, court_id)

    if not current["is_active"]:
        return current

    row = (
        db.execute(
            text(
                """
                UPDATE public.courts
                SET
                  is_active = FALSE,
                  updated_at = now()
                WHERE id = :court_id
                RETURNING
                  id,
                  name,
                  is_active,
                  created_at,
                  updated_at
                """
            ),
            {"court_id": court_id},
        )
        .mappings()
        .first()
    )

    _insert_court_status_history(
        db,
        court_id=court_id,
        status_value="inactive",
        changed_by_user_id=user_id,
        reason_code=payload.reason_code if payload else None,
        reason_note=payload.reason_note if payload else None,
    )

    db.commit()
    return row


@router.patch("/{court_id}/reactivate", response_model=CourtOut)
def reactivate_court(
    court_id: UUID,
    payload: CourtStatusChangeIn | None,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _validate_status_change_payload(payload)
    current = _get_court_or_404(db, court_id)

    if current["is_active"]:
        return current

    row = (
        db.execute(
            text(
                """
                UPDATE public.courts
                SET
                  is_active = TRUE,
                  updated_at = now()
                WHERE id = :court_id
                RETURNING
                  id,
                  name,
                  is_active,
                  created_at,
                  updated_at
                """
            ),
            {"court_id": court_id},
        )
        .mappings()
        .first()
    )

    _insert_court_status_history(
        db,
        court_id=court_id,
        status_value="active",
        changed_by_user_id=user_id,
        reason_code=payload.reason_code if payload else None,
        reason_note=payload.reason_note if payload else None,
    )

    db.commit()
    return row

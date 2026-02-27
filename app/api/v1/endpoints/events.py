from typing import Annotated
from uuid import UUID as UUIDType

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.events import EventCreateIn, EventOut

router = APIRouter()


def _integrity_to_http(e: IntegrityError) -> HTTPException:
    orig = getattr(e, "orig", None)
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)

    constraint = None
    diag = getattr(orig, "diag", None)
    if diag is not None:
        constraint = getattr(diag, "constraint_name", None)

    if pgcode == "23P01":  # exclusion violation (overbooking)
        if constraint == "ex_events_no_overlap_court":
            return HTTPException(
                status_code=409,
                detail="Conflito: a quadra já está ocupada nesse horário.",
            )
        if constraint == "ex_events_no_overlap_teacher":
            return HTTPException(
                status_code=409,
                detail="Conflito: o professor já está ocupado nesse horário.",
            )
        return HTTPException(
            status_code=409,
            detail="Conflito: horário indisponível (sobreposição).",
        )

    if pgcode == "23503":  # foreign key
        return HTTPException(
            status_code=422,
            detail="Referência inválida (court/teacher/student não existe).",
        )

    return HTTPException(
        status_code=400,
        detail=f"Erro ao salvar evento: {str(orig) if orig else str(e)}",
    )


@router.post("/", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def criar_evento(
    payload: EventCreateIn,
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    user_id: Annotated[str, Depends(get_current_user_id)] = "",  # type: ignore[assignment]
):
    if payload.end_at <= payload.start_at:
        raise HTTPException(status_code=422, detail="end_at precisa ser maior que start_at")

    if payload.kind in ("aula_regular", "primeira_aula") and payload.teacher_id is None:
        raise HTTPException(status_code=422, detail="teacher_id é obrigatório para aulas")

    if payload.kind not in ("aula_regular", "primeira_aula", "locacao", "bloqueio"):
        raise HTTPException(status_code=422, detail="kind inválido")

    if payload.status not in ("confirmado", "cancelado"):
        raise HTTPException(status_code=422, detail="status inválido")

    created_by_uuid = UUIDType(user_id)

    try:
        row = (
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
                    "court_id": payload.court_id,
                    "teacher_id": payload.teacher_id,
                    "student_id": payload.student_id,
                    "created_by": created_by_uuid,
                    "kind": payload.kind,
                    "status": payload.status,
                    "start_at": payload.start_at,
                    "end_at": payload.end_at,
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


@router.patch("/{event_id}/cancel", response_model=EventOut)
def cancelar_evento(
    event_id: UUIDType,
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    _user_id: Annotated[str, Depends(get_current_user_id)] = "",  # type: ignore[assignment]
):
    row = (
        db.execute(
            text(
                """
            UPDATE public.events
            SET status = 'cancelado'
            WHERE id = :id
            RETURNING
              id, court_id, teacher_id, student_id, created_by,
              kind, status, start_at, end_at, notes, created_at, updated_at
            """
            ),
            {"id": event_id},
        )
        .mappings()
        .first()
    )

    if not row:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    db.commit()
    return row

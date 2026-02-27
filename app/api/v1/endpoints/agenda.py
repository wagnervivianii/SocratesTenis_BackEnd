from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.agenda import AgendaItemOut

router = APIRouter()


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
    if from_ >= to:
        raise HTTPException(status_code=422, detail="'from' precisa ser menor que 'to'")

    if (to - from_).days > 31:
        raise HTTPException(status_code=422, detail="Intervalo máximo: 31 dias")

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

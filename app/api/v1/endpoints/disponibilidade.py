from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.agenda import CourtDisponivelOut, ProfessorDisponivelOut

router = APIRouter()


@router.get("/quadras", response_model=list[CourtDisponivelOut])
def quadras_disponiveis(
    from_: Annotated[datetime, Query(alias="from")],
    to: Annotated[datetime, Query()],
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    _user_id: Annotated[str, Depends(get_current_user_id)] = "",  # type: ignore[assignment]
):
    if from_ >= to:
        raise HTTPException(status_code=422, detail="'from' precisa ser menor que 'to'")

    sql = text("SELECT * FROM public.fn_quadras_disponiveis(:p_from, :p_to)")
    return db.execute(sql, {"p_from": from_, "p_to": to}).mappings().all()


@router.get("/professores", response_model=list[ProfessorDisponivelOut])
def professores_disponiveis(
    from_: Annotated[datetime, Query(alias="from")],
    to: Annotated[datetime, Query()],
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    _user_id: Annotated[str, Depends(get_current_user_id)] = "",  # type: ignore[assignment]
):
    if from_ >= to:
        raise HTTPException(status_code=422, detail="'from' precisa ser menor que 'to'")

    sql = text("SELECT * FROM public.fn_professores_disponiveis(:p_from, :p_to)")
    return db.execute(sql, {"p_from": from_, "p_to": to}).mappings().all()

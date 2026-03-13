from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.catalogs import (
    BookableSlotCatalogsOut,
    CatalogCourtOut,
    CatalogOptionOut,
    CatalogTeacherOut,
    CatalogWeekdayOptionOut,
)

router = APIRouter(prefix="/catalogs")


@router.get("/courts", response_model=list[CatalogCourtOut])
def list_courts(
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    rows = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  name,
                  is_active
                FROM public.courts
                ORDER BY
                  is_active DESC,
                  name
                """
            )
        )
        .mappings()
        .all()
    )
    return rows


@router.get("/teachers", response_model=list[CatalogTeacherOut])
def list_teachers(
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    rows = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  full_name,
                  is_active
                FROM public.teachers
                ORDER BY
                  is_active DESC,
                  full_name
                """
            )
        )
        .mappings()
        .all()
    )
    return rows


@router.get("/bookable-slot-modalities", response_model=list[CatalogOptionOut])
def list_bookable_slot_modalities(
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    return [
        CatalogOptionOut(value="trial_lesson", label="Aula grátis"),
        CatalogOptionOut(value="court_rental", label="Locação de quadra"),
    ]


@router.get("/weekdays", response_model=list[CatalogWeekdayOptionOut])
def list_weekdays(
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    return [
        CatalogWeekdayOptionOut(value=1, label="Segunda-feira"),
        CatalogWeekdayOptionOut(value=2, label="Terça-feira"),
        CatalogWeekdayOptionOut(value=3, label="Quarta-feira"),
        CatalogWeekdayOptionOut(value=4, label="Quinta-feira"),
        CatalogWeekdayOptionOut(value=5, label="Sexta-feira"),
        CatalogWeekdayOptionOut(value=6, label="Sábado"),
        CatalogWeekdayOptionOut(value=7, label="Domingo"),
    ]


@router.get("/bookable-slots", response_model=BookableSlotCatalogsOut)
def get_bookable_slot_catalogs(
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    courts = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  name,
                  is_active
                FROM public.courts
                ORDER BY
                  is_active DESC,
                  name
                """
            )
        )
        .mappings()
        .all()
    )

    teachers = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  full_name,
                  is_active
                FROM public.teachers
                ORDER BY
                  is_active DESC,
                  full_name
                """
            )
        )
        .mappings()
        .all()
    )

    modalities = [
        CatalogOptionOut(value="trial_lesson", label="Aula grátis"),
        CatalogOptionOut(value="court_rental", label="Locação de quadra"),
    ]

    weekdays = [
        CatalogWeekdayOptionOut(value=1, label="Segunda-feira"),
        CatalogWeekdayOptionOut(value=2, label="Terça-feira"),
        CatalogWeekdayOptionOut(value=3, label="Quarta-feira"),
        CatalogWeekdayOptionOut(value=4, label="Quinta-feira"),
        CatalogWeekdayOptionOut(value=5, label="Sexta-feira"),
        CatalogWeekdayOptionOut(value=6, label="Sábado"),
        CatalogWeekdayOptionOut(value=7, label="Domingo"),
    ]

    return BookableSlotCatalogsOut(
        modalities=modalities,
        weekdays=weekdays,
        courts=[CatalogCourtOut(**row) for row in courts],
        teachers=[CatalogTeacherOut(**row) for row in teachers],
    )

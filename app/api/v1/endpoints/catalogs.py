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
    CatalogStudentOut,
    CatalogTeacherOut,
    CatalogWeekdayOptionOut,
    ClassGroupCatalogsOut,
)

router = APIRouter(prefix="/catalogs")


def _get_courts(db: Session):
    return (
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


def _get_teachers(db: Session):
    return (
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


def _get_students(db: Session):
    return (
        db.execute(
            text(
                """
                SELECT
                  id,
                  full_name,
                  email,
                  phone,
                  is_active
                FROM public.students
                ORDER BY
                  is_active DESC,
                  full_name
                """
            )
        )
        .mappings()
        .all()
    )


def _get_weekdays():
    return [
        CatalogWeekdayOptionOut(value=1, label="Segunda-feira"),
        CatalogWeekdayOptionOut(value=2, label="Terça-feira"),
        CatalogWeekdayOptionOut(value=3, label="Quarta-feira"),
        CatalogWeekdayOptionOut(value=4, label="Quinta-feira"),
        CatalogWeekdayOptionOut(value=5, label="Sexta-feira"),
        CatalogWeekdayOptionOut(value=6, label="Sábado"),
        CatalogWeekdayOptionOut(value=7, label="Domingo"),
    ]


@router.get("/courts", response_model=list[CatalogCourtOut])
def list_courts(
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    return _get_courts(db)


@router.get("/teachers", response_model=list[CatalogTeacherOut])
def list_teachers(
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    return _get_teachers(db)


@router.get("/students", response_model=list[CatalogStudentOut])
def list_students(
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
    is_active: bool | None = None,
):
    rows = _get_students(db)

    if is_active is None:
        return [CatalogStudentOut(**row) for row in rows]

    return [CatalogStudentOut(**row) for row in rows if bool(row["is_active"]) is is_active]


@router.get("/bookable-slot-modalities", response_model=list[CatalogOptionOut])
def list_bookable_slot_modalities(
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    return [
        CatalogOptionOut(value="trial_lesson", label="Aula grátis"),
        CatalogOptionOut(value="court_rental", label="Locação de quadra"),
    ]


@router.get("/class-group-levels", response_model=list[CatalogOptionOut])
def list_class_group_levels(
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    return [
        CatalogOptionOut(value="iniciante", label="Iniciante"),
        CatalogOptionOut(value="intermediario", label="Intermediário"),
        CatalogOptionOut(value="avancado", label="Avançado"),
    ]


@router.get("/weekdays", response_model=list[CatalogWeekdayOptionOut])
def list_weekdays(
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    return _get_weekdays()


@router.get("/bookable-slots", response_model=BookableSlotCatalogsOut)
def get_bookable_slot_catalogs(
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    modalities = [
        CatalogOptionOut(value="trial_lesson", label="Aula grátis"),
        CatalogOptionOut(value="court_rental", label="Locação de quadra"),
    ]

    weekdays = _get_weekdays()
    courts = _get_courts(db)
    teachers = _get_teachers(db)

    return BookableSlotCatalogsOut(
        modalities=modalities,
        weekdays=weekdays,
        courts=[CatalogCourtOut(**row) for row in courts],
        teachers=[CatalogTeacherOut(**row) for row in teachers],
    )


@router.get("/class-groups", response_model=ClassGroupCatalogsOut)
def get_class_group_catalogs(
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    levels = [
        CatalogOptionOut(value="iniciante", label="Iniciante"),
        CatalogOptionOut(value="intermediario", label="Intermediário"),
        CatalogOptionOut(value="avancado", label="Avançado"),
    ]

    weekdays = _get_weekdays()
    courts = _get_courts(db)
    teachers = _get_teachers(db)
    students = _get_students(db)

    return ClassGroupCatalogsOut(
        levels=levels,
        weekdays=weekdays,
        courts=[CatalogCourtOut(**row) for row in courts],
        teachers=[CatalogTeacherOut(**row) for row in teachers],
        students=[CatalogStudentOut(**row) for row in students],
    )

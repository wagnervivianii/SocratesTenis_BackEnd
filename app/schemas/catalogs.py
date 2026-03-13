from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class CatalogOptionOut(BaseModel):
    value: str
    label: str


class CatalogWeekdayOptionOut(BaseModel):
    value: int
    label: str


class CatalogCourtOut(BaseModel):
    id: UUID
    name: str
    is_active: bool


class CatalogTeacherOut(BaseModel):
    id: UUID
    full_name: str
    is_active: bool


class BookableSlotCatalogsOut(BaseModel):
    modalities: list[CatalogOptionOut]
    weekdays: list[CatalogWeekdayOptionOut]
    courts: list[CatalogCourtOut]
    teachers: list[CatalogTeacherOut]

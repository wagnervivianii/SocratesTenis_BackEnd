from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

BookableModality = Literal["trial_lesson", "court_rental"]


class BookableSlotCreateIn(BaseModel):
    modality: BookableModality = Field(
        ...,
        description="trial_lesson | court_rental",
    )
    court_id: UUID
    teacher_id: UUID | None = None

    weekday: int = Field(..., ge=1, le=7, description="1=segunda ... 7=domingo")
    start_time: time
    end_time: time

    starts_on: date
    ends_on: date | None = None

    slot_capacity: int = Field(default=1, ge=1)
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=1000)


class BookableSlotUpdateIn(BaseModel):
    modality: BookableModality | None = Field(
        default=None,
        description="trial_lesson | court_rental",
    )
    court_id: UUID | None = None
    teacher_id: UUID | None = None

    weekday: int | None = Field(default=None, ge=1, le=7, description="1=segunda ... 7=domingo")
    start_time: time | None = None
    end_time: time | None = None

    starts_on: date | None = None
    ends_on: date | None = None

    slot_capacity: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)


class BookableSlotOut(BaseModel):
    id: UUID
    modality: str

    court_id: UUID
    teacher_id: UUID | None = None

    weekday: int
    start_time: time
    end_time: time

    starts_on: date
    ends_on: date | None = None

    slot_capacity: int
    is_active: bool
    notes: str | None = None

    created_at: datetime
    updated_at: datetime


class BookableSlotListItemOut(BookableSlotOut):
    court_name: str
    teacher_name: str | None = None


class BookableSlotBulkRowIn(BaseModel):
    modality: BookableModality = Field(
        ...,
        description="trial_lesson | court_rental",
    )
    court_id: UUID
    teacher_id: UUID | None = None

    weekday: int = Field(..., ge=1, le=7, description="1=segunda ... 7=domingo")
    start_time: time
    end_time: time

    starts_on: date
    ends_on: date | None = None

    slot_capacity: int = Field(default=1, ge=1)
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=1000)


class BookableSlotBulkCreateIn(BaseModel):
    items: list[BookableSlotBulkRowIn] = Field(..., min_length=1, max_length=1000)


class BookableSlotBulkErrorOut(BaseModel):
    row_number: int
    message: str


class BookableSlotBulkCreateOut(BaseModel):
    created_count: int
    errors: list[BookableSlotBulkErrorOut] = []

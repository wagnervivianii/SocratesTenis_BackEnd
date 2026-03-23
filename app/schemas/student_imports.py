from __future__ import annotations

from pydantic import BaseModel, Field


class StudentImportRowPreviewOut(BaseModel):
    row_number: int = Field(..., ge=2)
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
    profession: str | None = None
    instagram_handle: str | None = None
    share_profession: bool | None = None
    share_instagram: bool | None = None
    is_active: bool | None = None
    errors: list[str] = Field(default_factory=list)


class StudentImportPreviewOut(BaseModel):
    file_name: str | None = None
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    rows: list[StudentImportRowPreviewOut] = Field(default_factory=list)


class StudentImportCommitOut(BaseModel):
    file_name: str | None = None
    total_rows: int = 0
    imported_rows: int = 0
    invalid_rows: int = 0
    rows: list[StudentImportRowPreviewOut] = Field(default_factory=list)

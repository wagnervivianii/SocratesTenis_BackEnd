from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class ShortsItem(BaseModel):
    keyword: str = Field(..., description="Palavra-chave do ciclo da hora")
    video_id: str
    title: str
    channel: str
    published_at: datetime | None = None

    thumb: HttpUrl | None = None
    watch_url: HttpUrl
    embed_url: HttpUrl

    duration_seconds: int | None = None


class ShortsResponse(BaseModel):
    keyword: str
    updated_at: datetime
    items: list[ShortsItem]

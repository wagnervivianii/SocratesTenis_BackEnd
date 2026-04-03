# app/models/user.py
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    # ✅ UUID gerado pelo banco (gen_random_uuid())
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    email: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ✅ novos campos (já existem no banco)
    whatsapp: Mapped[str | None] = mapped_column(String(11), unique=True, index=True, nullable=True)
    instagram: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # ✅ cadastro público complementar
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(8), index=True, nullable=True)
    guardian_full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    guardian_whatsapp: Mapped[str | None] = mapped_column(String(11), nullable=True)
    guardian_relationship: Mapped[str | None] = mapped_column(String(60), nullable=True)

    role: Mapped[str] = mapped_column(Text, nullable=False, default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ✅ novo: verificação de e-mail (null = não verificado)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

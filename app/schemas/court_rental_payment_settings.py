from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class CourtRentalPaymentSettingBase(BaseModel):
    name: str = Field(default="Configuração principal", max_length=255)
    pix_key: str = Field(..., min_length=1, max_length=255)
    merchant_name: str = Field(default="SOCRATES TENIS", min_length=1, max_length=255)
    merchant_city: str = Field(default="SAO PAULO", min_length=1, max_length=255)
    default_price_per_hour: Decimal = Field(..., gt=0)
    proof_whatsapp: str | None = Field(default=None, max_length=40)
    payment_instructions: str | None = Field(default=None, max_length=2000)
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=2000)


class CourtRentalPaymentSettingCreateIn(CourtRentalPaymentSettingBase):
    pass


class CourtRentalPaymentSettingUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    pix_key: str | None = Field(default=None, min_length=1, max_length=255)
    merchant_name: str | None = Field(default=None, min_length=1, max_length=255)
    merchant_city: str | None = Field(default=None, min_length=1, max_length=255)
    default_price_per_hour: Decimal | None = Field(default=None, gt=0)
    proof_whatsapp: str | None = Field(default=None, max_length=40)
    payment_instructions: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class CourtRentalPaymentSettingOut(CourtRentalPaymentSettingBase):
    id: UUID
    created_by_user_id: UUID | None = None
    updated_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class CourtRentalPaymentSettingSummaryOut(BaseModel):
    id: UUID
    name: str
    pix_key: str
    merchant_name: str
    merchant_city: str
    default_price_per_hour: Decimal
    proof_whatsapp: str | None = None
    payment_instructions: str | None = None
    is_active: bool
    updated_at: datetime


class CourtRentalPaymentSettingAppliedOut(BaseModel):
    rental_id: UUID
    status: str
    payment_status: str
    price_per_hour: Decimal
    total_amount: Decimal
    pix_key: str
    pix_qr_code_payload: str
    message: str
    email_sent: bool

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.court_rental_payment_settings import (
    CourtRentalPaymentSettingCreateIn,
    CourtRentalPaymentSettingOut,
    CourtRentalPaymentSettingSummaryOut,
    CourtRentalPaymentSettingUpdateIn,
)

router = APIRouter(prefix="/court-rental-payment-settings", tags=["court-rental-payment-settings"])

_SETTING_COLUMNS = """
  id,
  created_by_user_id,
  updated_by_user_id,
  name,
  pix_key,
  merchant_name,
  merchant_city,
  student_price_per_hour,
  public_third_party_price_per_hour,
  admin_third_party_price_per_hour,
  proof_whatsapp,
  payment_instructions,
  is_active,
  notes,
  created_at,
  updated_at
"""

_SUMMARY_COLUMNS = """
  id,
  name,
  pix_key,
  merchant_name,
  merchant_city,
  student_price_per_hour,
  public_third_party_price_per_hour,
  admin_third_party_price_per_hour,
  proof_whatsapp,
  payment_instructions,
  is_active,
  updated_at
"""


def _get_current_user_row(db: Session, user_id: str):
    return (
        db.execute(
            text(
                """
                SELECT id, email, role, is_active
                FROM public.users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        .mappings()
        .first()
    )


def _require_admin(db: Session, user_id: str) -> None:
    user = _get_current_user_row(db, user_id)
    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário inválido.",
        )

    if not str(user["role"]).startswith("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem gerenciar a configuração Pix da locação.",
        )


def _integrity_to_http(e: IntegrityError) -> HTTPException:
    orig = getattr(e, "orig", None)
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)

    constraint = None
    diag = getattr(orig, "diag", None)
    if diag is not None:
        constraint = getattr(diag, "constraint_name", None)

    if pgcode == "23505":
        if constraint == "uq_court_rental_payment_settings_single_active":
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe uma configuração Pix ativa para locação.",
            )

        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um registro igual para os mesmos parâmetros.",
        )

    if pgcode == "23514":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Violação de regra de validação do banco.",
        )

    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Erro ao salvar a configuração Pix: {str(orig) if orig else str(e)}",
    )


def _row_to_out(row) -> CourtRentalPaymentSettingOut:
    return CourtRentalPaymentSettingOut.model_validate(dict(row))


def _row_to_summary(row) -> CourtRentalPaymentSettingSummaryOut:
    return CourtRentalPaymentSettingSummaryOut.model_validate(dict(row))


def _get_setting_or_404(db: Session, setting_id: UUID):
    row = (
        db.execute(
            text(
                f"""
                SELECT
{_SETTING_COLUMNS}
                FROM public.court_rental_payment_settings
                WHERE id = :setting_id
                """
            ),
            {"setting_id": setting_id},
        )
        .mappings()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuração Pix da locação não encontrada.",
        )

    return row


@router.get("/current", response_model=CourtRentalPaymentSettingOut)
def get_current_court_rental_payment_setting(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(db, user_id)

    row = (
        db.execute(
            text(
                f"""
                SELECT
{_SETTING_COLUMNS}
                FROM public.court_rental_payment_settings
                WHERE is_active = true
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
        )
        .mappings()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhuma configuração Pix ativa foi cadastrada para locação.",
        )

    return _row_to_out(row)


@router.get("", response_model=list[CourtRentalPaymentSettingSummaryOut])
def list_court_rental_payment_settings(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(db, user_id)

    rows = db.execute(
        text(
            f"""
            SELECT
{_SUMMARY_COLUMNS}
            FROM public.court_rental_payment_settings
            ORDER BY is_active DESC, updated_at DESC, created_at DESC
            """
        )
    ).mappings()

    return [_row_to_summary(row) for row in rows]


@router.post("", response_model=CourtRentalPaymentSettingOut, status_code=status.HTTP_201_CREATED)
def create_court_rental_payment_setting(
    payload: CourtRentalPaymentSettingCreateIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(db, user_id)

    data = payload.model_dump()

    try:
        row = (
            db.execute(
                text(
                    f"""
                    INSERT INTO public.court_rental_payment_settings (
                      created_by_user_id,
                      updated_by_user_id,
                      name,
                      pix_key,
                      merchant_name,
                      merchant_city,
                      student_price_per_hour,
                      public_third_party_price_per_hour,
                      admin_third_party_price_per_hour,
                      proof_whatsapp,
                      payment_instructions,
                      is_active,
                      notes
                    )
                    VALUES (
                      :created_by_user_id,
                      :updated_by_user_id,
                      :name,
                      :pix_key,
                      :merchant_name,
                      :merchant_city,
                      :student_price_per_hour,
                      :public_third_party_price_per_hour,
                      :admin_third_party_price_per_hour,
                      :proof_whatsapp,
                      :payment_instructions,
                      :is_active,
                      :notes
                    )
                    RETURNING
{_SETTING_COLUMNS}
                    """
                ),
                {
                    "created_by_user_id": user_id,
                    "updated_by_user_id": user_id,
                    "name": data["name"].strip(),
                    "pix_key": data["pix_key"].strip(),
                    "merchant_name": data["merchant_name"].strip().upper(),
                    "merchant_city": data["merchant_city"].strip().upper(),
                    "student_price_per_hour": data["student_price_per_hour"],
                    "public_third_party_price_per_hour": data["public_third_party_price_per_hour"],
                    "admin_third_party_price_per_hour": data["admin_third_party_price_per_hour"],
                    "proof_whatsapp": data["proof_whatsapp"].strip()
                    if data["proof_whatsapp"]
                    else None,
                    "payment_instructions": data["payment_instructions"].strip()
                    if data["payment_instructions"]
                    else None,
                    "is_active": data["is_active"],
                    "notes": data["notes"].strip() if data["notes"] else None,
                },
            )
            .mappings()
            .one()
        )
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e

    return _row_to_out(row)


@router.patch("/{setting_id}", response_model=CourtRentalPaymentSettingOut)
def update_court_rental_payment_setting(
    setting_id: UUID,
    payload: CourtRentalPaymentSettingUpdateIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(db, user_id)
    existing = _get_setting_or_404(db, setting_id)

    data = payload.model_dump(exclude_unset=True)

    if not data:
        return _row_to_out(existing)

    merged = {
        "name": data.get("name", existing["name"]),
        "pix_key": data.get("pix_key", existing["pix_key"]),
        "merchant_name": data.get("merchant_name", existing["merchant_name"]),
        "merchant_city": data.get("merchant_city", existing["merchant_city"]),
        "student_price_per_hour": data.get(
            "student_price_per_hour", existing["student_price_per_hour"]
        ),
        "public_third_party_price_per_hour": data.get(
            "public_third_party_price_per_hour", existing["public_third_party_price_per_hour"]
        ),
        "admin_third_party_price_per_hour": data.get(
            "admin_third_party_price_per_hour", existing["admin_third_party_price_per_hour"]
        ),
        "proof_whatsapp": data.get("proof_whatsapp", existing["proof_whatsapp"]),
        "payment_instructions": data.get("payment_instructions", existing["payment_instructions"]),
        "is_active": data.get("is_active", existing["is_active"]),
        "notes": data.get("notes", existing["notes"]),
    }

    try:
        row = (
            db.execute(
                text(
                    f"""
                    UPDATE public.court_rental_payment_settings
                    SET
                      updated_by_user_id = :updated_by_user_id,
                      name = :name,
                      pix_key = :pix_key,
                      merchant_name = :merchant_name,
                      merchant_city = :merchant_city,
                      student_price_per_hour = :student_price_per_hour,
                      public_third_party_price_per_hour = :public_third_party_price_per_hour,
                      admin_third_party_price_per_hour = :admin_third_party_price_per_hour,
                      proof_whatsapp = :proof_whatsapp,
                      payment_instructions = :payment_instructions,
                      is_active = :is_active,
                      notes = :notes,
                      updated_at = now()
                    WHERE id = :setting_id
                    RETURNING
{_SETTING_COLUMNS}
                    """
                ),
                {
                    "setting_id": setting_id,
                    "updated_by_user_id": user_id,
                    "name": merged["name"].strip()
                    if isinstance(merged["name"], str)
                    else merged["name"],
                    "pix_key": merged["pix_key"].strip()
                    if isinstance(merged["pix_key"], str)
                    else merged["pix_key"],
                    "merchant_name": merged["merchant_name"].strip().upper()
                    if isinstance(merged["merchant_name"], str)
                    else merged["merchant_name"],
                    "merchant_city": merged["merchant_city"].strip().upper()
                    if isinstance(merged["merchant_city"], str)
                    else merged["merchant_city"],
                    "student_price_per_hour": merged["student_price_per_hour"],
                    "public_third_party_price_per_hour": merged[
                        "public_third_party_price_per_hour"
                    ],
                    "admin_third_party_price_per_hour": merged["admin_third_party_price_per_hour"],
                    "proof_whatsapp": merged["proof_whatsapp"].strip()
                    if isinstance(merged["proof_whatsapp"], str) and merged["proof_whatsapp"]
                    else None,
                    "payment_instructions": merged["payment_instructions"].strip()
                    if isinstance(merged["payment_instructions"], str)
                    and merged["payment_instructions"]
                    else None,
                    "is_active": merged["is_active"],
                    "notes": merged["notes"].strip()
                    if isinstance(merged["notes"], str) and merged["notes"]
                    else None,
                },
            )
            .mappings()
            .one()
        )
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e

    return _row_to_out(row)


@router.post("/{setting_id}/activate", response_model=CourtRentalPaymentSettingOut)
def activate_court_rental_payment_setting(
    setting_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(db, user_id)
    _get_setting_or_404(db, setting_id)

    try:
        db.execute(
            text(
                """
                UPDATE public.court_rental_payment_settings
                SET
                  is_active = false,
                  updated_by_user_id = :user_id,
                  updated_at = now()
                WHERE is_active = true
                  AND id <> :setting_id
                """
            ),
            {"user_id": user_id, "setting_id": setting_id},
        )

        row = (
            db.execute(
                text(
                    f"""
                    UPDATE public.court_rental_payment_settings
                    SET
                      is_active = true,
                      updated_by_user_id = :user_id,
                      updated_at = now()
                    WHERE id = :setting_id
                    RETURNING
{_SETTING_COLUMNS}
                    """
                ),
                {"user_id": user_id, "setting_id": setting_id},
            )
            .mappings()
            .one()
        )
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e

    return _row_to_out(row)

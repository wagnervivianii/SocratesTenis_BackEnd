from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.courts import (
    CourtCreateIn,
    CourtListItemOut,
    CourtOut,
    CourtStatusChangeIn,
    CourtStatusHistoryItemOut,
    CourtUpdateIn,
)

router = APIRouter(prefix="/courts")


_COURT_SELECT_COLUMNS = """
  id,
  name,
  surface_type,
  cover_type,
  image_url,
  short_description,
  is_active,
  created_at,
  updated_at
"""


def _clean_required_text(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O valor informado não pode ficar vazio.",
        )
    return cleaned


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


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
            detail="Usuário inválido",
        )

    if not str(user["role"]).startswith("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem gerenciar quadras.",
        )


def _integrity_to_http(e: IntegrityError) -> HTTPException:
    orig = getattr(e, "orig", None)
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)

    constraint = None
    diag = getattr(orig, "diag", None)
    if diag is not None:
        constraint = getattr(diag, "constraint_name", None)

    if pgcode == "23505":
        if constraint and "name" in constraint.lower():
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe uma quadra com este nome.",
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
        detail=f"Erro ao salvar dados da quadra: {str(orig) if orig else str(e)}",
    )


def _get_court_or_404(db: Session, court_id: UUID):
    row = (
        db.execute(
            text(
                f"""
                SELECT
                  {_COURT_SELECT_COLUMNS}
                FROM public.courts
                WHERE id = :court_id
                """
            ),
            {"court_id": court_id},
        )
        .mappings()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quadra não encontrada.",
        )

    return row


def _insert_court_status_history(
    db: Session,
    *,
    court_id: UUID,
    status_value: str,
    changed_by_user_id: str,
    reason_code: str | None = None,
    reason_note: str | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO public.court_status_history (
              court_id,
              status,
              reason_code,
              reason_note,
              changed_by_user_id
            )
            VALUES (
              :court_id,
              :status,
              :reason_code,
              :reason_note,
              :changed_by_user_id
            )
            """
        ),
        {
            "court_id": court_id,
            "status": status_value,
            "reason_code": reason_code.strip() if reason_code else None,
            "reason_note": reason_note.strip() if reason_note else None,
            "changed_by_user_id": changed_by_user_id,
        },
    )


def _validate_status_change_payload(payload: CourtStatusChangeIn | None) -> None:
    if not payload:
        return

    reason_code = payload.reason_code.strip() if payload.reason_code else None
    reason_note = payload.reason_note.strip() if payload.reason_note else None

    if reason_code == "other" and not reason_note:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A observação é obrigatória quando o motivo for 'other'.",
        )


def _court_image_storage_root() -> Path:
    return Path(__file__).resolve().parents[4] / "storage" / "courts"


def _guess_court_image_extension(upload: UploadFile) -> str:
    file_name = upload.filename or "court-image"
    suffix = Path(file_name).suffix.strip().lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return suffix

    content_type = (upload.content_type or "").lower()
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
    }.get(content_type, "")


def _remove_managed_court_image_if_exists(*, court_id: UUID, image_url: str | None) -> None:
    if not image_url:
        return

    media_marker = "/media/"
    marker_index = image_url.find(media_marker)
    if marker_index < 0:
        return

    relative_media_path = image_url[marker_index + len(media_marker) :].lstrip("/")
    expected_prefix = f"courts/{court_id}/"
    if not relative_media_path.startswith(expected_prefix):
        return

    absolute_path = Path(__file__).resolve().parents[4] / "storage" / relative_media_path
    if absolute_path.is_file():
        absolute_path.unlink()


_ALLOWED_COURT_IMAGE_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}
_COURT_IMAGE_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_COURT_IMAGE_MAX_DIMENSION = 1600
_COURT_IMAGE_OUTPUT_QUALITY = 80


def _optimize_court_image(file_bytes: bytes) -> bytes:
    try:
        with Image.open(BytesIO(file_bytes)) as image:
            normalized = ImageOps.exif_transpose(image)
            if normalized.mode not in {"RGB", "RGBA"}:
                normalized = normalized.convert("RGBA" if "A" in normalized.getbands() else "RGB")

            normalized.thumbnail(
                (_COURT_IMAGE_MAX_DIMENSION, _COURT_IMAGE_MAX_DIMENSION),
                Image.Resampling.LANCZOS,
            )

            output = BytesIO()
            if "A" in normalized.getbands():
                normalized.save(
                    output,
                    format="WEBP",
                    quality=_COURT_IMAGE_OUTPUT_QUALITY,
                    method=6,
                )
            else:
                normalized.convert("RGB").save(
                    output,
                    format="WEBP",
                    quality=_COURT_IMAGE_OUTPUT_QUALITY,
                    method=6,
                )

            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Não foi possível processar a imagem da quadra enviada.",
        ) from exc


@router.get("/", response_model=list[CourtListItemOut])
def list_courts(
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    is_active: bool | None = None,
    q: str | None = Query(default=None, description="Busca por nome da quadra"),
):
    _require_admin(db, user_id)

    params: dict[str, object] = {"is_active": is_active}
    where_parts = ["1 = 1"]

    if is_active is not None:
        where_parts.append("is_active = :is_active")

    if q and q.strip():
        params["q"] = f"%{q.strip()}%"
        where_parts.append("(name ILIKE :q OR COALESCE(short_description, '') ILIKE :q)")

    where_sql = " AND ".join(where_parts)

    rows = (
        db.execute(
            text(
                f"""
                SELECT
                  {_COURT_SELECT_COLUMNS}
                FROM public.courts
                WHERE {where_sql}
                ORDER BY
                  is_active DESC,
                  name
                """
            ),
            params,
        )
        .mappings()
        .all()
    )

    return rows


@router.get("/{court_id}", response_model=CourtOut)
def get_court(
    court_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    return _get_court_or_404(db, court_id)


@router.get("/{court_id}/status-history", response_model=list[CourtStatusHistoryItemOut])
def get_court_status_history(
    court_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_court_or_404(db, court_id)

    rows = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  court_id,
                  status,
                  reason_code,
                  reason_note,
                  changed_by_user_id,
                  created_at
                FROM public.court_status_history
                WHERE court_id = :court_id
                ORDER BY created_at DESC, id DESC
                """
            ),
            {"court_id": court_id},
        )
        .mappings()
        .all()
    )

    return rows


@router.post("/", response_model=CourtOut, status_code=status.HTTP_201_CREATED)
def create_court(
    payload: CourtCreateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

    try:
        row = (
            db.execute(
                text(
                    f"""
                    INSERT INTO public.courts (
                      name,
                      surface_type,
                      cover_type,
                      image_url,
                      short_description,
                      is_active
                    )
                    VALUES (
                      :name,
                      :surface_type,
                      :cover_type,
                      :image_url,
                      :short_description,
                      :is_active
                    )
                    RETURNING
                      {_COURT_SELECT_COLUMNS}
                    """
                ),
                {
                    "name": _clean_required_text(payload.name),
                    "surface_type": payload.surface_type,
                    "cover_type": payload.cover_type,
                    "image_url": _clean_optional_text(payload.image_url),
                    "short_description": _clean_optional_text(payload.short_description),
                    "is_active": payload.is_active,
                },
            )
            .mappings()
            .first()
        )

        _insert_court_status_history(
            db,
            court_id=row["id"],
            status_value="active" if row["is_active"] else "inactive",
            changed_by_user_id=user_id,
            reason_code="created",
            reason_note="Cadastro inicial da quadra.",
        )

        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.patch("/{court_id}", response_model=CourtOut)
def update_court(
    court_id: UUID,
    payload: CourtUpdateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

    current = _get_court_or_404(db, court_id)

    if payload.is_active is not None and bool(payload.is_active) != bool(current["is_active"]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use os endpoints específicos de ativação ou inativação para alterar o status da quadra.",
        )

    fields_set = payload.model_fields_set

    merged = {
        "name": (
            _clean_required_text(payload.name)
            if "name" in fields_set and payload.name is not None
            else current["name"]
        ),
        "surface_type": (
            payload.surface_type if "surface_type" in fields_set else current["surface_type"]
        ),
        "cover_type": (payload.cover_type if "cover_type" in fields_set else current["cover_type"]),
        "image_url": (
            _clean_optional_text(payload.image_url)
            if "image_url" in fields_set
            else current["image_url"]
        ),
        "short_description": (
            _clean_optional_text(payload.short_description)
            if "short_description" in fields_set
            else current["short_description"]
        ),
    }

    try:
        row = (
            db.execute(
                text(
                    f"""
                    UPDATE public.courts
                    SET
                      name = :name,
                      surface_type = :surface_type,
                      cover_type = :cover_type,
                      image_url = :image_url,
                      short_description = :short_description,
                      updated_at = now()
                    WHERE id = :court_id
                    RETURNING
                      {_COURT_SELECT_COLUMNS}
                    """
                ),
                {
                    "court_id": court_id,
                    **merged,
                },
            )
            .mappings()
            .first()
        )
        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.post("/{court_id}/image-upload", response_model=CourtOut)
async def upload_court_image(
    court_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    image_file: Annotated[UploadFile, File(...)],
):
    _require_admin(db, user_id)

    current = _get_court_or_404(db, court_id)

    content_type = (image_file.content_type or "").lower()
    if content_type not in _ALLOWED_COURT_IMAGE_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Envie a imagem da quadra em PNG, JPG ou WEBP.",
        )

    file_bytes = await image_file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O arquivo da imagem está vazio.",
        )

    if len(file_bytes) > _COURT_IMAGE_MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A imagem da quadra deve ter no máximo 10 MB antes da otimização.",
        )

    optimized_bytes = _optimize_court_image(file_bytes)

    storage_dir = _court_image_storage_root() / str(court_id)
    storage_dir.mkdir(parents=True, exist_ok=True)

    stored_file_name = f"{datetime.now():%Y%m%d%H%M%S}_{UUID(user_id).hex}.webp"
    absolute_path = storage_dir / stored_file_name
    absolute_path.write_bytes(optimized_bytes)

    relative_media_path = Path("courts") / str(court_id) / stored_file_name
    image_url = str(request.url_for("media", path=relative_media_path.as_posix()))

    try:
        row = (
            db.execute(
                text(
                    f"""
                    UPDATE public.courts
                    SET
                      image_url = :image_url,
                      updated_at = now()
                    WHERE id = :court_id
                    RETURNING
                      {_COURT_SELECT_COLUMNS}
                    """
                ),
                {
                    "court_id": court_id,
                    "image_url": image_url,
                },
            )
            .mappings()
            .first()
        )
        db.commit()
    except Exception:
        if absolute_path.exists():
            absolute_path.unlink()
        db.rollback()
        raise

    _remove_managed_court_image_if_exists(court_id=court_id, image_url=current["image_url"])
    return row


@router.patch("/{court_id}/deactivate", response_model=CourtOut)
def deactivate_court(
    court_id: UUID,
    payload: CourtStatusChangeIn | None,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _validate_status_change_payload(payload)
    current = _get_court_or_404(db, court_id)

    if not current["is_active"]:
        return current

    row = (
        db.execute(
            text(
                f"""
                UPDATE public.courts
                SET
                  is_active = FALSE,
                  updated_at = now()
                WHERE id = :court_id
                RETURNING
                  {_COURT_SELECT_COLUMNS}
                """
            ),
            {"court_id": court_id},
        )
        .mappings()
        .first()
    )

    _insert_court_status_history(
        db,
        court_id=court_id,
        status_value="inactive",
        changed_by_user_id=user_id,
        reason_code=payload.reason_code if payload else None,
        reason_note=payload.reason_note if payload else None,
    )

    db.commit()
    return row


@router.patch("/{court_id}/reactivate", response_model=CourtOut)
def reactivate_court(
    court_id: UUID,
    payload: CourtStatusChangeIn | None,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _validate_status_change_payload(payload)
    current = _get_court_or_404(db, court_id)

    if current["is_active"]:
        return current

    row = (
        db.execute(
            text(
                f"""
                UPDATE public.courts
                SET
                  is_active = TRUE,
                  updated_at = now()
                WHERE id = :court_id
                RETURNING
                  {_COURT_SELECT_COLUMNS}
                """
            ),
            {"court_id": court_id},
        )
        .mappings()
        .first()
    )

    _insert_court_status_history(
        db,
        court_id=court_id,
        status_value="active",
        changed_by_user_id=user_id,
        reason_code=payload.reason_code if payload else None,
        reason_note=payload.reason_note if payload else None,
    )

    db.commit()
    return row

from __future__ import annotations

import csv
import io
import re
import unicodedata
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.bookable_slots import (
    BookableSlotBulkCreateIn,
    BookableSlotBulkCreateOut,
    BookableSlotBulkErrorOut,
    BookableSlotBulkRowIn,
    BookableSlotCreateIn,
    BookableSlotListItemOut,
    BookableSlotOut,
    BookableSlotUpdateIn,
)

router = APIRouter(prefix="/bookable-slots")

CSV_HEADERS = [
    "modality",
    "court_id",
    "teacher_id",
    "weekday",
    "start_time",
    "end_time",
    "starts_on",
    "ends_on",
    "slot_capacity",
    "is_active",
    "notes",
]

CSV_HUMAN_HEADERS = [
    "modalidade",
    "quadra",
    "professor",
    "dia_semana",
    "hora_inicio",
    "hora_fim",
    "data_inicio",
    "data_fim",
    "capacidade",
    "ativo",
    "observacoes",
]


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

    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem gerenciar horários ofertáveis.",
        )


def _validate_payload(
    payload: BookableSlotCreateIn | BookableSlotUpdateIn | BookableSlotBulkRowIn,
) -> None:
    modality = getattr(payload, "modality", None)
    teacher_id = getattr(payload, "teacher_id", None)
    start_time = getattr(payload, "start_time", None)
    end_time = getattr(payload, "end_time", None)
    starts_on = getattr(payload, "starts_on", None)
    ends_on = getattr(payload, "ends_on", None)

    if modality == "trial_lesson" and teacher_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="teacher_id é obrigatório para modality=trial_lesson",
        )

    if start_time is not None and end_time is not None and end_time <= start_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_time precisa ser maior que start_time",
        )

    if starts_on is not None and ends_on is not None and ends_on < starts_on:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ends_on não pode ser menor que starts_on",
        )


def _integrity_to_http(e: IntegrityError) -> HTTPException:
    orig = getattr(e, "orig", None)
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)

    if pgcode == "23503":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Referência inválida (court_id, teacher_id ou outro relacionamento).",
        )

    if pgcode == "23505":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um horário ofertável igual para os mesmos parâmetros.",
        )

    if pgcode == "23514":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Violação de regra de validação do banco.",
        )

    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Erro ao salvar horário ofertável: {str(orig) if orig else str(e)}",
    )


def _get_slot_or_404(db: Session, slot_id: UUID):
    row = (
        db.execute(
            text(
                """
                SELECT
                  bs.id,
                  bs.modality,
                  bs.court_id,
                  c.name AS court_name,
                  bs.teacher_id,
                  t.full_name AS teacher_name,
                  bs.weekday,
                  bs.start_time,
                  bs.end_time,
                  bs.starts_on,
                  bs.ends_on,
                  bs.slot_capacity,
                  bs.is_active,
                  bs.notes,
                  bs.created_at,
                  bs.updated_at
                FROM public.bookable_slots bs
                JOIN public.courts c
                  ON c.id = bs.court_id
                LEFT JOIN public.teachers t
                  ON t.id = bs.teacher_id
                WHERE bs.id = :slot_id
                """
            ),
            {"slot_id": slot_id},
        )
        .mappings()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Horário ofertável não encontrado.",
        )

    return row


def _nullify_csv_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned != "" else None


def _normalize_lookup_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    collapsed = re.sub(r"\s+", " ", without_accents).strip().lower()
    return collapsed


def _format_validation_error(e: ValidationError) -> str:
    messages: list[str] = []
    for err in e.errors():
        loc = ".".join(str(part) for part in err.get("loc", []))
        msg = err.get("msg", "valor inválido")
        messages.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(messages)


def _human_modality_to_value(value: str) -> str:
    normalized = _normalize_lookup_key(value)

    mapping = {
        "aula gratis": "trial_lesson",
        "aula gratuita": "trial_lesson",
        "trial lesson": "trial_lesson",
        "trial_lesson": "trial_lesson",
        "locacao de quadra": "court_rental",
        "locacao quadra": "court_rental",
        "locacao": "court_rental",
        "court rental": "court_rental",
        "court_rental": "court_rental",
    }

    mapped = mapping.get(normalized)
    if mapped is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Modalidade inválida: {value}",
        )
    return mapped


def _human_weekday_to_value(value: str) -> int:
    normalized = _normalize_lookup_key(value)

    mapping = {
        "1": 1,
        "segunda": 1,
        "segunda feira": 1,
        "segunda-feira": 1,
        "2": 2,
        "terca": 2,
        "terca feira": 2,
        "terca-feira": 2,
        "3": 3,
        "quarta": 3,
        "quarta feira": 3,
        "quarta-feira": 3,
        "4": 4,
        "quinta": 4,
        "quinta feira": 4,
        "quinta-feira": 4,
        "5": 5,
        "sexta": 5,
        "sexta feira": 5,
        "sexta-feira": 5,
        "6": 6,
        "sabado": 6,
        "7": 7,
        "domingo": 7,
    }

    mapped = mapping.get(normalized)
    if mapped is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Dia da semana inválido: {value}",
        )
    return mapped


def _human_bool_to_value(value: str | None) -> bool:
    if value is None:
        return True

    normalized = _normalize_lookup_key(value)

    truthy = {"1", "true", "t", "sim", "s", "yes", "y"}
    falsy = {"0", "false", "f", "nao", "n", "no"}

    if normalized in truthy:
        return True
    if normalized in falsy:
        return False

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Valor inválido para ativo: {value}",
    )


def _resolve_unique_id_by_name(
    db: Session,
    *,
    table_name: str,
    label_column: str,
    raw_value: str,
    entity_label: str,
) -> UUID:
    rows = (
        db.execute(
            text(
                f"""
                SELECT
                  id,
                  {label_column} AS label
                FROM public.{table_name}
                ORDER BY {label_column}
                """
            )
        )
        .mappings()
        .all()
    )

    target = _normalize_lookup_key(raw_value)
    matches = [row for row in rows if _normalize_lookup_key(str(row["label"])) == target]

    if not matches:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{entity_label} não encontrado(a): {raw_value}",
        )

    if len(matches) > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{entity_label} ambíguo(a): {raw_value}",
        )

    return matches[0]["id"]


def _build_bulk_result(
    db: Session,
    items: list[BookableSlotBulkRowIn],
    row_numbers: list[int] | None = None,
) -> BookableSlotBulkCreateOut:
    created_count = 0
    errors: list[BookableSlotBulkErrorOut] = []

    insert_sql = text(
        """
        INSERT INTO public.bookable_slots (
          modality,
          court_id,
          teacher_id,
          weekday,
          start_time,
          end_time,
          starts_on,
          ends_on,
          slot_capacity,
          is_active,
          notes
        )
        VALUES (
          :modality,
          :court_id,
          :teacher_id,
          :weekday,
          :start_time,
          :end_time,
          :starts_on,
          :ends_on,
          :slot_capacity,
          :is_active,
          :notes
        )
        """
    )

    for idx, item in enumerate(items, start=1):
        current_row_number = row_numbers[idx - 1] if row_numbers else idx

        try:
            _validate_payload(item)

            with db.begin_nested():
                db.execute(
                    insert_sql,
                    {
                        "modality": item.modality,
                        "court_id": item.court_id,
                        "teacher_id": item.teacher_id,
                        "weekday": item.weekday,
                        "start_time": item.start_time,
                        "end_time": item.end_time,
                        "starts_on": item.starts_on,
                        "ends_on": item.ends_on,
                        "slot_capacity": item.slot_capacity,
                        "is_active": item.is_active,
                        "notes": item.notes,
                    },
                )

            created_count += 1

        except HTTPException as e:
            errors.append(
                BookableSlotBulkErrorOut(
                    row_number=current_row_number,
                    message=str(e.detail),
                )
            )
        except IntegrityError as e:
            errors.append(
                BookableSlotBulkErrorOut(
                    row_number=current_row_number,
                    message=_integrity_to_http(e).detail,
                )
            )

    if created_count > 0:
        db.commit()
    else:
        db.rollback()

    return BookableSlotBulkCreateOut(
        created_count=created_count,
        errors=errors,
    )


@router.get("/template/csv")
def download_bookable_slots_csv_template(
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    lines = [
        ",".join(CSV_HEADERS),
        "trial_lesson,d58d46ff-ea6f-47b1-b390-d3dd844ac36e,f83be340-bb1d-480c-b80c-43e8149ca574,3,19:00:00,19:30:00,2026-03-18,,1,true,Slot aula grátis",
        "court_rental,c8f969b5-56a2-455f-9cfa-04de381ec7d2,,6,09:00:00,10:00:00,2026-03-21,,1,true,Locação sábado manhã",
    ]
    content = "\n".join(lines)

    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="bookable_slots_template.csv"'},
    )


@router.get("/template/csv-human")
def download_bookable_slots_csv_human_template(
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    lines = [
        ",".join(CSV_HUMAN_HEADERS),
        "Aula grátis,Quadra 1,Professor Teste,Quarta-feira,19:00,19:30,2026-03-18,,1,sim,Slot aula grátis",
        "Locação de quadra,Quadra 2,,Sábado,09:00,10:00,2026-03-21,,1,sim,Locação sábado manhã",
    ]
    content = "\n".join(lines)

    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="bookable_slots_template_human.csv"'},
    )


@router.get("/", response_model=list[BookableSlotListItemOut])
def list_bookable_slots(
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
    modality: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    weekday: Annotated[int | None, Query(ge=1, le=7)] = None,
    court_id: Annotated[UUID | None, Query()] = None,
    teacher_id: Annotated[UUID | None, Query()] = None,
):
    where_clauses = []
    params: dict[str, object] = {}

    if modality is not None:
        where_clauses.append("bs.modality = :modality")
        params["modality"] = modality

    if is_active is not None:
        where_clauses.append("bs.is_active = :is_active")
        params["is_active"] = is_active

    if weekday is not None:
        where_clauses.append("bs.weekday = :weekday")
        params["weekday"] = weekday

    if court_id is not None:
        where_clauses.append("bs.court_id = :court_id")
        params["court_id"] = court_id

    if teacher_id is not None:
        where_clauses.append("bs.teacher_id = :teacher_id")
        params["teacher_id"] = teacher_id

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    sql = text(
        f"""
        SELECT
          bs.id,
          bs.modality,
          bs.court_id,
          c.name AS court_name,
          bs.teacher_id,
          t.full_name AS teacher_name,
          bs.weekday,
          bs.start_time,
          bs.end_time,
          bs.starts_on,
          bs.ends_on,
          bs.slot_capacity,
          bs.is_active,
          bs.notes,
          bs.created_at,
          bs.updated_at
        FROM public.bookable_slots bs
        JOIN public.courts c
          ON c.id = bs.court_id
        LEFT JOIN public.teachers t
          ON t.id = bs.teacher_id
        {where_sql}
        ORDER BY
          bs.modality,
          bs.weekday,
          bs.start_time,
          c.name,
          t.full_name NULLS LAST
        """
    )

    rows = db.execute(sql, params).mappings().all()
    return rows


@router.get("/{slot_id}", response_model=BookableSlotListItemOut)
def get_bookable_slot(
    slot_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    return _get_slot_or_404(db, slot_id)


@router.post("/", response_model=BookableSlotOut, status_code=status.HTTP_201_CREATED)
def create_bookable_slot(
    payload: BookableSlotCreateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _validate_payload(payload)

    try:
        row = (
            db.execute(
                text(
                    """
                    INSERT INTO public.bookable_slots (
                      modality,
                      court_id,
                      teacher_id,
                      weekday,
                      start_time,
                      end_time,
                      starts_on,
                      ends_on,
                      slot_capacity,
                      is_active,
                      notes
                    )
                    VALUES (
                      :modality,
                      :court_id,
                      :teacher_id,
                      :weekday,
                      :start_time,
                      :end_time,
                      :starts_on,
                      :ends_on,
                      :slot_capacity,
                      :is_active,
                      :notes
                    )
                    RETURNING
                      id,
                      modality,
                      court_id,
                      teacher_id,
                      weekday,
                      start_time,
                      end_time,
                      starts_on,
                      ends_on,
                      slot_capacity,
                      is_active,
                      notes,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "modality": payload.modality,
                    "court_id": payload.court_id,
                    "teacher_id": payload.teacher_id,
                    "weekday": payload.weekday,
                    "start_time": payload.start_time,
                    "end_time": payload.end_time,
                    "starts_on": payload.starts_on,
                    "ends_on": payload.ends_on,
                    "slot_capacity": payload.slot_capacity,
                    "is_active": payload.is_active,
                    "notes": payload.notes,
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


@router.patch("/{slot_id}", response_model=BookableSlotOut)
def update_bookable_slot(
    slot_id: UUID,
    payload: BookableSlotUpdateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

    current = _get_slot_or_404(db, slot_id)

    merged = {
        "modality": payload.modality if payload.modality is not None else current["modality"],
        "court_id": payload.court_id if payload.court_id is not None else current["court_id"],
        "teacher_id": payload.teacher_id
        if payload.teacher_id is not None
        else current["teacher_id"],
        "weekday": payload.weekday if payload.weekday is not None else current["weekday"],
        "start_time": payload.start_time
        if payload.start_time is not None
        else current["start_time"],
        "end_time": payload.end_time if payload.end_time is not None else current["end_time"],
        "starts_on": payload.starts_on if payload.starts_on is not None else current["starts_on"],
        "ends_on": payload.ends_on if payload.ends_on is not None else current["ends_on"],
        "slot_capacity": (
            payload.slot_capacity if payload.slot_capacity is not None else current["slot_capacity"]
        ),
        "is_active": payload.is_active if payload.is_active is not None else current["is_active"],
        "notes": payload.notes if payload.notes is not None else current["notes"],
    }

    _validate_payload(BookableSlotCreateIn(**merged))

    try:
        row = (
            db.execute(
                text(
                    """
                    UPDATE public.bookable_slots
                    SET
                      modality = :modality,
                      court_id = :court_id,
                      teacher_id = :teacher_id,
                      weekday = :weekday,
                      start_time = :start_time,
                      end_time = :end_time,
                      starts_on = :starts_on,
                      ends_on = :ends_on,
                      slot_capacity = :slot_capacity,
                      is_active = :is_active,
                      notes = :notes,
                      updated_at = now()
                    WHERE id = :slot_id
                    RETURNING
                      id,
                      modality,
                      court_id,
                      teacher_id,
                      weekday,
                      start_time,
                      end_time,
                      starts_on,
                      ends_on,
                      slot_capacity,
                      is_active,
                      notes,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "slot_id": slot_id,
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


@router.patch("/{slot_id}/deactivate", response_model=BookableSlotOut)
def deactivate_bookable_slot(
    slot_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_slot_or_404(db, slot_id)

    row = (
        db.execute(
            text(
                """
                UPDATE public.bookable_slots
                SET
                  is_active = FALSE,
                  updated_at = now()
                WHERE id = :slot_id
                RETURNING
                  id,
                  modality,
                  court_id,
                  teacher_id,
                  weekday,
                  start_time,
                  end_time,
                  starts_on,
                  ends_on,
                  slot_capacity,
                  is_active,
                  notes,
                  created_at,
                  updated_at
                """
            ),
            {"slot_id": slot_id},
        )
        .mappings()
        .first()
    )

    db.commit()
    return row


@router.post("/bulk", response_model=BookableSlotBulkCreateOut, status_code=status.HTTP_201_CREATED)
def bulk_create_bookable_slots(
    payload: BookableSlotBulkCreateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    return _build_bulk_result(db, payload.items)


@router.post(
    "/bulk/csv", response_model=BookableSlotBulkCreateOut, status_code=status.HTTP_201_CREATED
)
def bulk_create_bookable_slots_from_csv(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Envie um arquivo CSV válido.",
        )

    raw = file.file.read()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Não foi possível ler o CSV em UTF-8.",
        ) from e

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV sem cabeçalho.",
        )

    missing_headers = [header for header in CSV_HEADERS if header not in reader.fieldnames]
    if missing_headers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cabeçalhos obrigatórios ausentes: {', '.join(missing_headers)}",
        )

    items: list[BookableSlotBulkRowIn] = []
    valid_row_numbers: list[int] = []
    parse_errors: list[BookableSlotBulkErrorOut] = []

    for row_number, row in enumerate(reader, start=2):
        payload_data: dict[str, object] = {
            "modality": _nullify_csv_value(row.get("modality")),
            "court_id": _nullify_csv_value(row.get("court_id")),
            "teacher_id": _nullify_csv_value(row.get("teacher_id")),
            "weekday": _nullify_csv_value(row.get("weekday")),
            "start_time": _nullify_csv_value(row.get("start_time")),
            "end_time": _nullify_csv_value(row.get("end_time")),
            "starts_on": _nullify_csv_value(row.get("starts_on")),
            "ends_on": _nullify_csv_value(row.get("ends_on")),
            "notes": _nullify_csv_value(row.get("notes")),
        }

        slot_capacity = _nullify_csv_value(row.get("slot_capacity"))
        if slot_capacity is not None:
            payload_data["slot_capacity"] = slot_capacity

        is_active = _nullify_csv_value(row.get("is_active"))
        if is_active is not None:
            payload_data["is_active"] = is_active

        try:
            item = BookableSlotBulkRowIn(**payload_data)
            _validate_payload(item)
            items.append(item)
            valid_row_numbers.append(row_number)
        except ValidationError as e:
            parse_errors.append(
                BookableSlotBulkErrorOut(
                    row_number=row_number,
                    message=_format_validation_error(e),
                )
            )
        except HTTPException as e:
            parse_errors.append(
                BookableSlotBulkErrorOut(
                    row_number=row_number,
                    message=str(e.detail),
                )
            )

    if not items and parse_errors:
        return BookableSlotBulkCreateOut(
            created_count=0,
            errors=parse_errors,
        )

    if not items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV sem linhas válidas para importação.",
        )

    result = _build_bulk_result(db, items, valid_row_numbers)
    result.errors.extend(parse_errors)
    return result


@router.post(
    "/bulk/csv-human", response_model=BookableSlotBulkCreateOut, status_code=status.HTTP_201_CREATED
)
def bulk_create_bookable_slots_from_csv_human(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Envie um arquivo CSV válido.",
        )

    raw = file.file.read()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Não foi possível ler o CSV em UTF-8.",
        ) from e

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV sem cabeçalho.",
        )

    missing_headers = [header for header in CSV_HUMAN_HEADERS if header not in reader.fieldnames]
    if missing_headers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cabeçalhos obrigatórios ausentes: {', '.join(missing_headers)}",
        )

    items: list[BookableSlotBulkRowIn] = []
    valid_row_numbers: list[int] = []
    parse_errors: list[BookableSlotBulkErrorOut] = []

    for row_number, row in enumerate(reader, start=2):
        try:
            modalidade = _nullify_csv_value(row.get("modalidade"))
            quadra = _nullify_csv_value(row.get("quadra"))
            professor = _nullify_csv_value(row.get("professor"))
            dia_semana = _nullify_csv_value(row.get("dia_semana"))
            hora_inicio = _nullify_csv_value(row.get("hora_inicio"))
            hora_fim = _nullify_csv_value(row.get("hora_fim"))
            data_inicio = _nullify_csv_value(row.get("data_inicio"))
            data_fim = _nullify_csv_value(row.get("data_fim"))
            capacidade = _nullify_csv_value(row.get("capacidade"))
            ativo = _nullify_csv_value(row.get("ativo"))
            observacoes = _nullify_csv_value(row.get("observacoes"))

            if modalidade is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="modalidade é obrigatória",
                )

            if quadra is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="quadra é obrigatória",
                )

            if dia_semana is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="dia_semana é obrigatório",
                )

            payload_data: dict[str, object] = {
                "modality": _human_modality_to_value(modalidade),
                "court_id": _resolve_unique_id_by_name(
                    db,
                    table_name="courts",
                    label_column="name",
                    raw_value=quadra,
                    entity_label="Quadra",
                ),
                "teacher_id": None,
                "weekday": _human_weekday_to_value(dia_semana),
                "start_time": hora_inicio,
                "end_time": hora_fim,
                "starts_on": data_inicio,
                "ends_on": data_fim,
                "slot_capacity": capacidade if capacidade is not None else 1,
                "is_active": _human_bool_to_value(ativo),
                "notes": observacoes,
            }

            if professor is not None:
                payload_data["teacher_id"] = _resolve_unique_id_by_name(
                    db,
                    table_name="teachers",
                    label_column="full_name",
                    raw_value=professor,
                    entity_label="Professor",
                )

            item = BookableSlotBulkRowIn(**payload_data)
            _validate_payload(item)
            items.append(item)
            valid_row_numbers.append(row_number)

        except ValidationError as e:
            parse_errors.append(
                BookableSlotBulkErrorOut(
                    row_number=row_number,
                    message=_format_validation_error(e),
                )
            )
        except HTTPException as e:
            parse_errors.append(
                BookableSlotBulkErrorOut(
                    row_number=row_number,
                    message=str(e.detail),
                )
            )

    if not items and parse_errors:
        return BookableSlotBulkCreateOut(
            created_count=0,
            errors=parse_errors,
        )

    if not items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV sem linhas válidas para importação.",
        )

    result = _build_bulk_result(db, items, valid_row_numbers)
    result.errors.extend(parse_errors)
    return result

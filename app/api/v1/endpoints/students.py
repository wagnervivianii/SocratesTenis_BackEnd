from __future__ import annotations

import csv
import io
from collections import Counter
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.student_imports import (
    StudentImportCommitOut,
    StudentImportPreviewOut,
    StudentImportRowPreviewOut,
)
from app.schemas.students import (
    StudentCreateIn,
    StudentHomeOut,
    StudentListItemOut,
    StudentOut,
    StudentStatusChangeIn,
    StudentStatusHistoryItemOut,
    StudentUpdateIn,
)

router = APIRouter(prefix="/students")

_IMPORT_HEADERS = [
    "full_name",
    "email",
    "phone",
    "notes",
    "profession",
    "instagram_handle",
    "share_profession",
    "share_instagram",
    "is_active",
]

_BOOLEAN_TRUE_VALUES = {"1", "true", "t", "yes", "y", "sim", "s"}
_BOOLEAN_FALSE_VALUES = {"0", "false", "f", "no", "n", "nao", "não"}

_WEEKDAY_LABELS = {
    1: "Segunda-feira",
    2: "Terça-feira",
    3: "Quarta-feira",
    4: "Quinta-feira",
    5: "Sexta-feira",
    6: "Sábado",
    7: "Domingo",
}


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
            detail="Apenas administradores podem gerenciar alunos.",
        )


def _require_active_user(db: Session, user_id: str):
    user = _get_current_user_row(db, user_id)
    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário inválido",
        )
    return user


def _find_student_by_user_or_email(
    db: Session,
    *,
    user_id: str,
    email: str | None,
):
    direct_match = (
        db.execute(
            text(
                """
                SELECT
                  s.id,
                  s.user_id,
                  COALESCE(NULLIF(TRIM(s.full_name), ''), NULLIF(TRIM(u.full_name), '')) AS full_name,
                  COALESCE(NULLIF(TRIM(s.email), ''), NULLIF(TRIM(u.email), '')) AS email,
                  COALESCE(NULLIF(TRIM(s.phone), ''), NULLIF(TRIM(u.whatsapp), '')) AS phone,
                  s.notes,
                  s.profession,
                  s.instagram_handle,
                  s.share_profession,
                  s.share_instagram,
                  s.is_active,
                  s.created_at,
                  s.updated_at,
                  NULL::text AS avatar_url
                FROM public.students s
                LEFT JOIN public.users u
                  ON u.id = s.user_id
                WHERE s.user_id = :user_id
                ORDER BY s.created_at ASC
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
        .mappings()
        .first()
    )
    if direct_match:
        return direct_match

    normalized_email = _normalize_optional_email(email)
    if not normalized_email:
        return None

    return (
        db.execute(
            text(
                """
                SELECT
                  s.id,
                  s.user_id,
                  COALESCE(NULLIF(TRIM(s.full_name), ''), NULLIF(TRIM(u.full_name), '')) AS full_name,
                  COALESCE(NULLIF(TRIM(s.email), ''), NULLIF(TRIM(u.email), '')) AS email,
                  COALESCE(NULLIF(TRIM(s.phone), ''), NULLIF(TRIM(u.whatsapp), '')) AS phone,
                  s.notes,
                  s.profession,
                  s.instagram_handle,
                  s.share_profession,
                  s.share_instagram,
                  s.is_active,
                  s.created_at,
                  s.updated_at,
                  NULL::text AS avatar_url
                FROM public.students s
                LEFT JOIN public.users u
                  ON u.id = s.user_id
                WHERE lower(s.email) = :email
                ORDER BY s.created_at ASC
                LIMIT 1
                """
            ),
            {"email": normalized_email},
        )
        .mappings()
        .first()
    )


def _get_student_home_class_group_rows(db: Session, *, student_id: UUID):
    return (
        db.execute(
            text(
                """
                SELECT
                  cge.id AS enrollment_id,
                  cg.id AS class_group_id,
                  cg.name AS class_group_name,
                  cg.class_type AS class_type,
                  cg.level AS level,
                  cge.status AS enrollment_status,
                  cge.starts_on AS enrollment_starts_on,
                  cge.ends_on AS enrollment_ends_on,
                  cg.teacher_id AS teacher_id,
                  t.full_name AS teacher_name,
                  cg.court_id AS court_id,
                  c.name AS court_name
                FROM public.class_group_enrollments cge
                JOIN public.class_groups cg
                  ON cg.id = cge.class_group_id
                LEFT JOIN public.teachers t
                  ON t.id = cg.teacher_id
                LEFT JOIN public.courts c
                  ON c.id = cg.court_id
                WHERE cge.student_id = :student_id
                  AND cge.status = 'active'
                  AND cg.is_active = TRUE
                  AND cge.starts_on <= current_date
                  AND (cge.ends_on IS NULL OR cge.ends_on >= current_date)
                ORDER BY
                  cg.name ASC,
                  cge.starts_on ASC,
                  cge.created_at ASC
                """
            ),
            {"student_id": student_id},
        )
        .mappings()
        .all()
    )


def _get_student_home_schedule_rows(db: Session, *, class_group_ids: list[UUID]):
    if not class_group_ids:
        return []

    return (
        db.execute(
            text(
                """
                SELECT
                  cgs.id AS schedule_id,
                  cgs.class_group_id AS class_group_id,
                  cgs.weekday AS weekday,
                  cgs.start_time AS start_time,
                  cgs.end_time AS end_time,
                  cgs.starts_on AS starts_on,
                  cgs.ends_on AS ends_on,
                  cgs.is_active AS is_active,
                  cgs.notes AS notes
                FROM public.class_group_schedules cgs
                WHERE cgs.class_group_id = ANY(:class_group_ids)
                  AND cgs.is_active = TRUE
                  AND cgs.starts_on <= current_date
                  AND (cgs.ends_on IS NULL OR cgs.ends_on >= current_date)
                ORDER BY
                  cgs.class_group_id ASC,
                  cgs.weekday ASC,
                  cgs.start_time ASC
                """
            ),
            {"class_group_ids": class_group_ids},
        )
        .mappings()
        .all()
    )


def _get_student_home_classmate_rows(
    db: Session,
    *,
    class_group_ids: list[UUID],
    student_id: UUID,
):
    if not class_group_ids:
        return []

    return (
        db.execute(
            text(
                """
                SELECT
                  cge.class_group_id AS class_group_id,
                  s.id AS student_id,
                  COALESCE(NULLIF(TRIM(s.full_name), ''), NULLIF(TRIM(u.full_name), '')) AS full_name,
                  NULL::text AS avatar_url
                FROM public.class_group_enrollments cge
                JOIN public.class_groups cg
                  ON cg.id = cge.class_group_id
                JOIN public.students s
                  ON s.id = cge.student_id
                LEFT JOIN public.users u
                  ON u.id = s.user_id
                WHERE cge.class_group_id = ANY(:class_group_ids)
                  AND cge.status = 'active'
                  AND cg.is_active = TRUE
                  AND cge.starts_on <= current_date
                  AND (cge.ends_on IS NULL OR cge.ends_on >= current_date)
                  AND s.id <> :student_id
                ORDER BY
                  cge.class_group_id ASC,
                  full_name ASC
                """
            ),
            {"class_group_ids": class_group_ids, "student_id": student_id},
        )
        .mappings()
        .all()
    )


def _get_student_home_upcoming_rental_rows(
    db: Session,
    *,
    user_id: str,
    student_id: UUID,
):
    return (
        db.execute(
            text(
                """
                SELECT
                  cr.id AS rental_id,
                  e.court_id AS court_id,
                  c.name AS court_name,
                  e.start_at AS start_at,
                  e.end_at AS end_at,
                  cr.status AS status,
                  cr.payment_status AS payment_status,
                  cr.payment_evidence_status AS payment_evidence_status,
                  cr.pricing_profile AS pricing_profile,
                  cr.billing_mode AS billing_mode,
                  cr.origin AS origin,
                  cr.total_amount AS total_amount,
                  cr.price_per_hour AS price_per_hour,
                  cr.requested_at AS requested_at,
                  cr.scheduled_at AS scheduled_at,
                  cr.confirmed_at AS confirmed_at,
                  cr.cancelled_at AS cancelled_at,
                  cr.payment_expires_at AS payment_expires_at
                FROM public.court_rentals cr
                JOIN public.events e
                  ON e.id = cr.event_id
                LEFT JOIN public.courts c
                  ON c.id = e.court_id
                WHERE (
                  cr.customer_student_id = :student_id
                  OR COALESCE(cr.customer_user_id, cr.user_id) = :user_id
                )
                  AND e.kind = 'locacao'
                  AND e.end_at > now()
                  AND cr.status IN (
                    'requested',
                    'awaiting_payment',
                    'awaiting_proof',
                    'awaiting_admin_review',
                    'scheduled',
                    'confirmed'
                  )
                ORDER BY
                  e.start_at ASC,
                  cr.created_at DESC
                """
            ),
            {"user_id": user_id, "student_id": student_id},
        )
        .mappings()
        .all()
    )


def _get_student_home_recent_rental_history_rows(
    db: Session,
    *,
    user_id: str,
    student_id: UUID,
):
    return (
        db.execute(
            text(
                """
                SELECT
                  cr.id AS rental_id,
                  e.court_id AS court_id,
                  c.name AS court_name,
                  e.start_at AS start_at,
                  e.end_at AS end_at,
                  cr.status AS status,
                  cr.payment_status AS payment_status,
                  cr.payment_evidence_status AS payment_evidence_status,
                  cr.pricing_profile AS pricing_profile,
                  cr.billing_mode AS billing_mode,
                  cr.origin AS origin,
                  cr.total_amount AS total_amount,
                  cr.price_per_hour AS price_per_hour,
                  cr.requested_at AS requested_at,
                  cr.scheduled_at AS scheduled_at,
                  cr.confirmed_at AS confirmed_at,
                  cr.cancelled_at AS cancelled_at,
                  cr.payment_expires_at AS payment_expires_at
                FROM public.court_rentals cr
                LEFT JOIN public.events e
                  ON e.id = cr.event_id
                LEFT JOIN public.courts c
                  ON c.id = e.court_id
                WHERE (
                  cr.customer_student_id = :student_id
                  OR COALESCE(cr.customer_user_id, cr.user_id) = :user_id
                )
                  AND (
                    cr.status IN ('cancelled', 'completed', 'rejected')
                    OR e.end_at <= now()
                  )
                ORDER BY
                  COALESCE(e.start_at, cr.requested_at, cr.created_at) DESC,
                  cr.created_at DESC
                LIMIT 10
                """
            ),
            {"user_id": user_id, "student_id": student_id},
        )
        .mappings()
        .all()
    )


def _build_student_home_payload(
    db: Session,
    *,
    user: dict,
    student_row: dict,
):
    class_group_rows = _get_student_home_class_group_rows(db, student_id=student_row["id"])
    class_group_ids = [row["class_group_id"] for row in class_group_rows]

    schedule_rows = _get_student_home_schedule_rows(db, class_group_ids=class_group_ids)
    classmate_rows = _get_student_home_classmate_rows(
        db,
        class_group_ids=class_group_ids,
        student_id=student_row["id"],
    )

    schedules_by_group: dict[UUID, list[dict[str, object]]] = {}
    for row in schedule_rows:
        schedules_by_group.setdefault(row["class_group_id"], []).append(
            {
                "schedule_id": row["schedule_id"],
                "weekday": row["weekday"],
                "weekday_label": _WEEKDAY_LABELS.get(row["weekday"], "Dia não informado"),
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "starts_on": row["starts_on"],
                "ends_on": row["ends_on"],
                "is_active": row["is_active"],
                "notes": row["notes"],
            }
        )

    classmates_by_group: dict[UUID, list[dict[str, object]]] = {}
    for row in classmate_rows:
        classmates_by_group.setdefault(row["class_group_id"], []).append(
            {
                "student_id": row["student_id"],
                "full_name": row["full_name"],
                "avatar_url": row["avatar_url"],
            }
        )

    class_groups = [
        {
            "enrollment_id": row["enrollment_id"],
            "class_group_id": row["class_group_id"],
            "class_group_name": row["class_group_name"],
            "class_type": row["class_type"],
            "level": row["level"],
            "enrollment_status": row["enrollment_status"],
            "enrollment_starts_on": row["enrollment_starts_on"],
            "enrollment_ends_on": row["enrollment_ends_on"],
            "teacher_id": row["teacher_id"],
            "teacher_name": row["teacher_name"],
            "court_id": row["court_id"],
            "court_name": row["court_name"],
            "classmates": classmates_by_group.get(row["class_group_id"], []),
            "schedules": schedules_by_group.get(row["class_group_id"], []),
        }
        for row in class_group_rows
    ]

    upcoming_rentals = [
        {
            "rental_id": row["rental_id"],
            "court_id": row["court_id"],
            "court_name": row["court_name"],
            "start_at": row["start_at"],
            "end_at": row["end_at"],
            "status": row["status"],
            "payment_status": row["payment_status"],
            "payment_evidence_status": row["payment_evidence_status"],
            "pricing_profile": row["pricing_profile"],
            "billing_mode": row["billing_mode"],
            "origin": row["origin"],
            "total_amount": row["total_amount"],
            "price_per_hour": row["price_per_hour"],
            "requested_at": row["requested_at"],
            "scheduled_at": row["scheduled_at"],
            "confirmed_at": row["confirmed_at"],
            "cancelled_at": row["cancelled_at"],
            "payment_expires_at": row["payment_expires_at"],
        }
        for row in _get_student_home_upcoming_rental_rows(
            db,
            user_id=user["id"],
            student_id=student_row["id"],
        )
    ]

    recent_rental_history = [
        {
            "rental_id": row["rental_id"],
            "court_id": row["court_id"],
            "court_name": row["court_name"],
            "start_at": row["start_at"],
            "end_at": row["end_at"],
            "status": row["status"],
            "payment_status": row["payment_status"],
            "payment_evidence_status": row["payment_evidence_status"],
            "pricing_profile": row["pricing_profile"],
            "billing_mode": row["billing_mode"],
            "origin": row["origin"],
            "total_amount": row["total_amount"],
            "price_per_hour": row["price_per_hour"],
            "requested_at": row["requested_at"],
            "scheduled_at": row["scheduled_at"],
            "confirmed_at": row["confirmed_at"],
            "cancelled_at": row["cancelled_at"],
            "payment_expires_at": row["payment_expires_at"],
        }
        for row in _get_student_home_recent_rental_history_rows(
            db,
            user_id=user["id"],
            student_id=student_row["id"],
        )
    ]

    return {
        "profile": {
            "id": student_row["id"],
            "user_id": student_row["user_id"],
            "full_name": student_row["full_name"],
            "email": student_row["email"],
            "phone": student_row["phone"],
            "profession": student_row["profession"],
            "instagram_handle": student_row["instagram_handle"],
            "share_profession": student_row["share_profession"],
            "share_instagram": student_row["share_instagram"],
            "is_active": student_row["is_active"],
            "avatar_url": student_row["avatar_url"],
        },
        "class_groups": class_groups,
        "upcoming_rentals": upcoming_rentals,
        "recent_rental_history": recent_rental_history,
    }


def _integrity_to_http(e: IntegrityError) -> HTTPException:
    orig = getattr(e, "orig", None)
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)

    constraint = None
    diag = getattr(orig, "diag", None)
    if diag is not None:
        constraint = getattr(diag, "constraint_name", None)

    if pgcode == "23503":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Referência inválida para relacionamento informado.",
        )

    if pgcode == "23505":
        if constraint and "email" in constraint.lower():
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um aluno com este e-mail.",
            )

        if constraint and "user_id" in constraint.lower():
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este usuário já está vinculado a outro aluno.",
            )

        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um registro igual para os mesmos parâmetros.",
        )

    if pgcode == "23514":
        if constraint == "chk_instagram_handle":
            return HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "instagram_handle inválido. Use apenas letras, números, "
                    "ponto e underscore, sem @."
                ),
            )

        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Violação de regra de validação do banco.",
        )

    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Erro ao salvar dados do aluno: {str(orig) if orig else str(e)}",
    )


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def _normalize_optional_email(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    return normalized.lower() if normalized else None


def _normalize_instagram_handle(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if not normalized:
        return None

    return normalized.removeprefix("@").strip().lower() or None


def _find_teacher_by_email(db: Session, *, email: str):
    return (
        db.execute(
            text(
                """
                SELECT id, full_name, email, user_id, is_active
                FROM public.teachers
                WHERE lower(email) = :email
                LIMIT 1
                """
            ),
            {"email": email.lower()},
        )
        .mappings()
        .first()
    )


def _ensure_email_not_used_by_teacher(db: Session, *, email: str | None) -> None:
    normalized_email = _normalize_optional_email(email)
    if not normalized_email:
        return

    conflict = _find_teacher_by_email(db, email=normalized_email)
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este e-mail já está cadastrado para um professor. "
                "Cada e-mail pode pertencer a apenas um grupo no sistema."
            ),
        )


def _get_student_or_404(db: Session, student_id: UUID):
    row = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  user_id,
                  full_name,
                  email,
                  phone,
                  notes,
                  profession,
                  instagram_handle,
                  share_profession,
                  share_instagram,
                  is_active,
                  created_at,
                  updated_at
                FROM public.students
                WHERE id = :student_id
                """
            ),
            {"student_id": student_id},
        )
        .mappings()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado.",
        )

    return row


def _validate_status_change_payload(
    payload: StudentStatusChangeIn | None,
) -> tuple[str | None, str | None]:
    if payload is None:
        return None, None

    reason_code = payload.reason_code.strip() if payload.reason_code else None
    reason_note = payload.reason_note.strip() if payload.reason_note else None

    if reason_code == "other" and not reason_note:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Informe o motivo complementar quando o motivo for 'other'.",
        )

    return reason_code, reason_note


def _insert_student_status_history(
    db: Session,
    *,
    student_id: UUID,
    status_value: str,
    changed_by_user_id: str,
    reason_code: str | None = None,
    reason_note: str | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO public.student_status_history (
              student_id,
              status,
              reason_code,
              reason_note,
              changed_by_user_id
            )
            VALUES (
              :student_id,
              :status,
              :reason_code,
              :reason_note,
              :changed_by_user_id
            )
            """
        ),
        {
            "student_id": student_id,
            "status": status_value,
            "reason_code": reason_code.strip() if reason_code else None,
            "reason_note": reason_note.strip() if reason_note else None,
            "changed_by_user_id": changed_by_user_id,
        },
    )


def _student_import_template_content() -> str:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(_IMPORT_HEADERS)
    writer.writerow(
        [
            "Aluno Exemplo",
            "aluno.exemplo@socratestenis.com",
            "11999999999",
            "Observação opcional",
            "Engenheiro",
            "aluno.exemplo",
            "false",
            "false",
            "true",
        ]
    )
    return output.getvalue()


def _decode_import_bytes(raw_bytes: bytes) -> str:
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Arquivo vazio. Envie um CSV com pelo menos o cabeçalho.",
        )

    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Não foi possível ler o arquivo. Salve a planilha como CSV UTF-8 ou CSV padrão.",
    )


def _detect_csv_delimiter(text_content: str) -> str:
    sample = text_content[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t,")
        return dialect.delimiter
    except csv.Error:
        return ";"


def _parse_import_bool(
    raw_value: str | None,
    *,
    field_label: str,
    default: bool,
    errors: list[str],
) -> bool:
    normalized = _normalize_optional_text(raw_value)
    if normalized is None:
        return default

    lowered = normalized.lower()
    if lowered in _BOOLEAN_TRUE_VALUES:
        return True
    if lowered in _BOOLEAN_FALSE_VALUES:
        return False

    errors.append(f"Valor inválido para {field_label}. Use true/false, sim/não, yes/no ou 1/0.")
    return default


def _normalize_import_row(raw_row: dict[str, str | None]) -> dict[str, object]:
    return {
        "full_name": _normalize_optional_text(raw_row.get("full_name")),
        "email": _normalize_optional_email(raw_row.get("email")),
        "phone": _normalize_optional_text(raw_row.get("phone")),
        "notes": _normalize_optional_text(raw_row.get("notes")),
        "profession": _normalize_optional_text(raw_row.get("profession")),
        "instagram_handle": _normalize_instagram_handle(raw_row.get("instagram_handle")),
    }


def _extract_csv_rows(
    file_name: str | None, raw_bytes: bytes
) -> tuple[str | None, list[dict[str, str | None]]]:
    text_content = _decode_import_bytes(raw_bytes)
    delimiter = _detect_csv_delimiter(text_content)
    reader = csv.DictReader(io.StringIO(text_content), delimiter=delimiter)

    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O arquivo precisa ter cabeçalho.",
        )

    normalized_headers = [
        header.strip() for header in reader.fieldnames if header and header.strip()
    ]
    missing_headers = [header for header in _IMPORT_HEADERS if header not in normalized_headers]
    if missing_headers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Cabeçalho inválido. Colunas obrigatórias/esperadas ausentes: "
                + ", ".join(missing_headers)
            ),
        )

    rows: list[dict[str, str | None]] = []
    for raw_row in reader:
        if raw_row is None:
            continue

        normalized_row = {
            (key.strip() if key else ""): (value if value is not None else None)
            for key, value in raw_row.items()
        }

        if not any(_normalize_optional_text(value) for value in normalized_row.values()):
            continue

        rows.append(normalized_row)

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O arquivo não possui linhas de dados para importar.",
        )

    return file_name, rows


def _build_student_import_preview(
    db: Session,
    *,
    file_name: str | None,
    raw_bytes: bytes,
) -> StudentImportPreviewOut:
    file_name, extracted_rows = _extract_csv_rows(file_name, raw_bytes)

    normalized_rows_for_checks: list[dict[str, object]] = []
    emails_in_file: list[str] = []

    for raw_row in extracted_rows:
        normalized = _normalize_import_row(raw_row)
        email = normalized["email"]
        if isinstance(email, str):
            emails_in_file.append(email)
        normalized_rows_for_checks.append(normalized)

    duplicate_email_counter = Counter(emails_in_file)
    existing_emails = set()
    teacher_emails = set()
    unique_emails = sorted({email for email in emails_in_file if email})
    if unique_emails:
        existing_email_rows = (
            db.execute(
                text(
                    """
                    SELECT email
                    FROM public.students
                    WHERE email = ANY(:emails)
                    """
                ),
                {"emails": unique_emails},
            )
            .scalars()
            .all()
        )
        existing_emails = {str(email).lower() for email in existing_email_rows if email}

        teacher_email_rows = (
            db.execute(
                text(
                    """
                    SELECT email
                    FROM public.teachers
                    WHERE email = ANY(:emails)
                    """
                ),
                {"emails": unique_emails},
            )
            .scalars()
            .all()
        )
        teacher_emails = {str(email).lower() for email in teacher_email_rows if email}

    preview_rows: list[StudentImportRowPreviewOut] = []

    for index, raw_row in enumerate(extracted_rows, start=2):
        errors: list[str] = []
        normalized = normalized_rows_for_checks[index - 2]

        share_profession = _parse_import_bool(
            raw_row.get("share_profession"),
            field_label="share_profession",
            default=False,
            errors=errors,
        )
        share_instagram = _parse_import_bool(
            raw_row.get("share_instagram"),
            field_label="share_instagram",
            default=False,
            errors=errors,
        )
        is_active = _parse_import_bool(
            raw_row.get("is_active"),
            field_label="is_active",
            default=True,
            errors=errors,
        )

        payload_data = {
            "full_name": normalized["full_name"],
            "email": normalized["email"],
            "phone": normalized["phone"],
            "notes": normalized["notes"],
            "profession": normalized["profession"],
            "instagram_handle": normalized["instagram_handle"],
            "share_profession": share_profession,
            "share_instagram": share_instagram,
            "is_active": is_active,
        }

        try:
            validated = StudentCreateIn(**payload_data)
            payload_data = validated.model_dump()
        except ValidationError as e:
            for item in e.errors():
                field_name = ".".join(str(loc) for loc in item.get("loc", []))
                message = item.get("msg", "valor inválido")
                errors.append(f"{field_name}: {message}")

        email = payload_data.get("email")
        if isinstance(email, str):
            if duplicate_email_counter[email] > 1:
                errors.append("E-mail duplicado dentro do arquivo.")
            if email.lower() in existing_emails:
                errors.append("Já existe aluno cadastrado com este e-mail.")
            if email.lower() in teacher_emails:
                errors.append(
                    "Este e-mail já está cadastrado para um professor. Cada e-mail pode pertencer a apenas um grupo no sistema."
                )

        preview_rows.append(
            StudentImportRowPreviewOut(
                row_number=index,
                full_name=payload_data.get("full_name"),
                email=payload_data.get("email"),
                phone=payload_data.get("phone"),
                notes=payload_data.get("notes"),
                profession=payload_data.get("profession"),
                instagram_handle=payload_data.get("instagram_handle"),
                share_profession=payload_data.get("share_profession"),
                share_instagram=payload_data.get("share_instagram"),
                is_active=payload_data.get("is_active"),
                errors=errors,
            )
        )

    valid_rows = sum(1 for row in preview_rows if not row.errors)
    invalid_rows = len(preview_rows) - valid_rows

    return StudentImportPreviewOut(
        file_name=file_name,
        total_rows=len(preview_rows),
        valid_rows=valid_rows,
        invalid_rows=invalid_rows,
        rows=preview_rows,
    )


@router.get(
    "/import/template",
    response_class=Response,
)
def download_student_import_template(
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

    return Response(
        content=_student_import_template_content(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="students_import_template.csv"'},
    )


@router.post("/import/preview", response_model=StudentImportPreviewOut)
def preview_student_import(
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    uploaded_file: Annotated[UploadFile, File(...)],
):
    _require_admin(db, user_id)

    if not uploaded_file.filename or not uploaded_file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Envie um arquivo CSV gerado a partir da planilha.",
        )

    raw_bytes = uploaded_file.file.read()
    return _build_student_import_preview(
        db,
        file_name=uploaded_file.filename,
        raw_bytes=raw_bytes,
    )


@router.post("/import/commit", response_model=StudentImportCommitOut)
def commit_student_import(
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    uploaded_file: Annotated[UploadFile, File(...)],
):
    _require_admin(db, user_id)

    if not uploaded_file.filename or not uploaded_file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Envie um arquivo CSV gerado a partir da planilha.",
        )

    raw_bytes = uploaded_file.file.read()
    preview = _build_student_import_preview(
        db,
        file_name=uploaded_file.filename,
        raw_bytes=raw_bytes,
    )

    if preview.invalid_rows > 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "O arquivo possui linhas inválidas. Corrija antes de importar.",
                "preview": preview.model_dump(mode="json"),
            },
        )

    imported_rows = 0

    try:
        for row in preview.rows:
            inserted = (
                db.execute(
                    text(
                        """
                        INSERT INTO public.students (
                          full_name,
                          email,
                          phone,
                          notes,
                          profession,
                          instagram_handle,
                          share_profession,
                          share_instagram,
                          is_active
                        )
                        VALUES (
                          :full_name,
                          :email,
                          :phone,
                          :notes,
                          :profession,
                          :instagram_handle,
                          :share_profession,
                          :share_instagram,
                          :is_active
                        )
                        RETURNING id, is_active
                        """
                    ),
                    {
                        "full_name": row.full_name,
                        "email": row.email,
                        "phone": row.phone,
                        "notes": row.notes,
                        "profession": row.profession,
                        "instagram_handle": row.instagram_handle,
                        "share_profession": row.share_profession,
                        "share_instagram": row.share_instagram,
                        "is_active": row.is_active,
                    },
                )
                .mappings()
                .first()
            )

            _insert_student_status_history(
                db,
                student_id=inserted["id"],
                status_value="active" if inserted["is_active"] else "inactive",
                changed_by_user_id=user_id,
                reason_code="imported",
                reason_note=f"Importação em massa via arquivo {preview.file_name or 'students.csv'}.",
            )
            imported_rows += 1

        db.commit()

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e

    return StudentImportCommitOut(
        file_name=preview.file_name,
        total_rows=preview.total_rows,
        imported_rows=imported_rows,
        invalid_rows=0,
        rows=preview.rows,
    )


@router.get("/me/home", response_model=StudentHomeOut)
def get_student_home(
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    user = _require_active_user(db, user_id)
    student_row = _find_student_by_user_or_email(db, user_id=user_id, email=user["email"])

    if not student_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhum aluno vinculado foi encontrado para este usuário.",
        )

    if not student_row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="O cadastro deste aluno está inativo no momento.",
        )

    return _build_student_home_payload(db, user=user, student_row=student_row)


@router.get("/", response_model=list[StudentListItemOut])
def list_students(
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    is_active: bool | None = None,
    q: str | None = Query(
        default=None,
        description="Busca por nome, e-mail ou telefone",
    ),
):
    _require_admin(db, user_id)

    params: dict[str, object] = {"is_active": is_active}
    where_parts = ["1 = 1"]

    if is_active is not None:
        where_parts.append("is_active = :is_active")

    if q and q.strip():
        params["q"] = f"%{q.strip()}%"
        where_parts.append(
            """
            (
              full_name ILIKE :q
              OR CAST(email AS text) ILIKE :q
              OR COALESCE(phone, '') ILIKE :q
            )
            """
        )

    where_sql = " AND ".join(where_parts)

    rows = (
        db.execute(
            text(
                f"""
                SELECT
                  id,
                  user_id,
                  full_name,
                  email,
                  phone,
                  notes,
                  profession,
                  instagram_handle,
                  share_profession,
                  share_instagram,
                  is_active,
                  created_at,
                  updated_at
                FROM public.students
                WHERE {where_sql}
                ORDER BY
                  is_active DESC,
                  full_name
                """
            ),
            params,
        )
        .mappings()
        .all()
    )

    return rows


@router.get("/{student_id}", response_model=StudentOut)
def get_student(
    student_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    return _get_student_or_404(db, student_id)


@router.get(
    "/{student_id}/status-history",
    response_model=list[StudentStatusHistoryItemOut],
)
def get_student_status_history(
    student_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    _get_student_or_404(db, student_id)

    rows = (
        db.execute(
            text(
                """
                SELECT
                  id,
                  student_id,
                  status,
                  reason_code,
                  reason_note,
                  changed_by_user_id,
                  created_at
                FROM public.student_status_history
                WHERE student_id = :student_id
                ORDER BY created_at DESC, id DESC
                """
            ),
            {"student_id": student_id},
        )
        .mappings()
        .all()
    )

    return rows


@router.post("/", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

    email = _normalize_optional_email(str(payload.email) if payload.email else None)
    _ensure_email_not_used_by_teacher(db, email=email)

    try:
        row = (
            db.execute(
                text(
                    """
                    INSERT INTO public.students (
                      full_name,
                      email,
                      phone,
                      notes,
                      profession,
                      instagram_handle,
                      share_profession,
                      share_instagram,
                      is_active
                    )
                    VALUES (
                      :full_name,
                      :email,
                      :phone,
                      :notes,
                      :profession,
                      :instagram_handle,
                      :share_profession,
                      :share_instagram,
                      :is_active
                    )
                    RETURNING
                      id,
                      user_id,
                      full_name,
                      email,
                      phone,
                      notes,
                      profession,
                      instagram_handle,
                      share_profession,
                      share_instagram,
                      is_active,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "full_name": payload.full_name.strip(),
                    "email": email,
                    "phone": _normalize_optional_text(payload.phone),
                    "notes": _normalize_optional_text(payload.notes),
                    "profession": _normalize_optional_text(payload.profession),
                    "instagram_handle": _normalize_instagram_handle(payload.instagram_handle),
                    "share_profession": payload.share_profession,
                    "share_instagram": payload.share_instagram,
                    "is_active": payload.is_active,
                },
            )
            .mappings()
            .first()
        )

        _insert_student_status_history(
            db,
            student_id=row["id"],
            status_value="active" if row["is_active"] else "inactive",
            changed_by_user_id=user_id,
            reason_code="created",
            reason_note="Cadastro inicial do aluno.",
        )

        db.commit()
        return row

    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e


@router.patch("/{student_id}", response_model=StudentOut)
def update_student(
    student_id: UUID,
    payload: StudentUpdateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)

    current = _get_student_or_404(db, student_id)

    merged = {
        "full_name": (
            payload.full_name.strip() if payload.full_name is not None else current["full_name"]
        ),
        "email": _normalize_optional_email(
            str(payload.email) if payload.email is not None else current["email"]
        ),
        "phone": (
            _normalize_optional_text(payload.phone)
            if payload.phone is not None
            else current["phone"]
        ),
        "notes": (
            _normalize_optional_text(payload.notes)
            if payload.notes is not None
            else current["notes"]
        ),
        "profession": (
            _normalize_optional_text(payload.profession)
            if payload.profession is not None
            else current["profession"]
        ),
        "instagram_handle": (
            _normalize_instagram_handle(payload.instagram_handle)
            if payload.instagram_handle is not None
            else current["instagram_handle"]
        ),
        "share_profession": (
            payload.share_profession
            if payload.share_profession is not None
            else current["share_profession"]
        ),
        "share_instagram": (
            payload.share_instagram
            if payload.share_instagram is not None
            else current["share_instagram"]
        ),
        "is_active": (payload.is_active if payload.is_active is not None else current["is_active"]),
    }

    _ensure_email_not_used_by_teacher(db, email=merged["email"])

    try:
        row = (
            db.execute(
                text(
                    """
                    UPDATE public.students
                    SET
                      full_name = :full_name,
                      email = :email,
                      phone = :phone,
                      notes = :notes,
                      profession = :profession,
                      instagram_handle = :instagram_handle,
                      share_profession = :share_profession,
                      share_instagram = :share_instagram,
                      is_active = :is_active,
                      updated_at = now()
                    WHERE id = :student_id
                    RETURNING
                      id,
                      user_id,
                      full_name,
                      email,
                      phone,
                      notes,
                      profession,
                      instagram_handle,
                      share_profession,
                      share_instagram,
                      is_active,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "student_id": student_id,
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


@router.patch("/{student_id}/deactivate", response_model=StudentOut)
def deactivate_student(
    student_id: UUID,
    payload: StudentStatusChangeIn | None,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    current = _get_student_or_404(db, student_id)

    if not current["is_active"]:
        return current

    reason_code, reason_note = _validate_status_change_payload(payload)

    row = (
        db.execute(
            text(
                """
                UPDATE public.students
                SET
                  is_active = FALSE,
                  updated_at = now()
                WHERE id = :student_id
                RETURNING
                  id,
                  user_id,
                  full_name,
                  email,
                  phone,
                  notes,
                  profession,
                  instagram_handle,
                  share_profession,
                  share_instagram,
                  is_active,
                  created_at,
                  updated_at
                """
            ),
            {"student_id": student_id},
        )
        .mappings()
        .first()
    )

    _insert_student_status_history(
        db,
        student_id=student_id,
        status_value="inactive",
        changed_by_user_id=user_id,
        reason_code=reason_code,
        reason_note=reason_note,
    )

    db.commit()
    return row


@router.patch("/{student_id}/reactivate", response_model=StudentOut)
def reactivate_student(
    student_id: UUID,
    payload: StudentStatusChangeIn | None,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    current = _get_student_or_404(db, student_id)

    if current["is_active"]:
        return current

    reason_code, reason_note = _validate_status_change_payload(payload)

    row = (
        db.execute(
            text(
                """
                UPDATE public.students
                SET
                  is_active = TRUE,
                  updated_at = now()
                WHERE id = :student_id
                RETURNING
                  id,
                  user_id,
                  full_name,
                  email,
                  phone,
                  notes,
                  profession,
                  instagram_handle,
                  share_profession,
                  share_instagram,
                  is_active,
                  created_at,
                  updated_at
                """
            ),
            {"student_id": student_id},
        )
        .mappings()
        .first()
    )

    _insert_student_status_history(
        db,
        student_id=student_id,
        status_value="active",
        changed_by_user_id=user_id,
        reason_code=reason_code,
        reason_note=reason_note,
    )

    db.commit()
    return row

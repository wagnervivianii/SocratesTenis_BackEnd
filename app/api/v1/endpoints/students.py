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
                    "email": _normalize_optional_email(
                        str(payload.email) if payload.email else None
                    ),
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

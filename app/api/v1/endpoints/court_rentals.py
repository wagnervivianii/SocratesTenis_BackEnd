from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.models.court_rental import CourtRental
from app.models.student import Student
from app.models.user import User
from app.schemas.court_rentals import (
    CourtRentalAdminCreateIn,
    CourtRentalAdminListItemOut,
    CourtRentalAdminListOut,
    CourtRentalAdminPaymentDefinitionIn,
    CourtRentalAdminPaymentDefinitionOut,
    CourtRentalAdminUpdateIn,
    CourtRentalCancelOut,
    CourtRentalCourtCardOut,
    CourtRentalEligibilityOut,
    CourtRentalOut,
    CourtRentalPaymentInstructionOut,
    CourtRentalPaymentReviewIn,
    CourtRentalPaymentReviewOut,
    CourtRentalProofSubmissionIn,
    CourtRentalProofSubmissionOut,
    CourtRentalRescheduleIn,
    CourtRentalRescheduleOut,
    CourtRentalScheduleIn,
    CourtRentalScheduleOut,
    CourtRentalSlotOut,
    CourtRentalUpcomingItemOut,
    CourtRentalUpcomingListOut,
)
from app.services.email_sender import (
    ConsoleEmailSender,
    EmailSendError,
    SmtpConfig,
    SmtpEmailSender,
)
from app.services.pix_payload import PixPayloadError, generate_pix_payload

router = APIRouter(prefix="/court-rentals", tags=["court-rentals"])


def _integrity_to_http(e: IntegrityError) -> HTTPException:
    orig = getattr(e, "orig", None)
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)

    constraint = None
    diag = getattr(orig, "diag", None)
    if diag is not None:
        constraint = getattr(diag, "constraint_name", None)

    if pgcode == "23P01":
        if constraint == "ex_events_no_overlap_court":
            return HTTPException(
                status_code=409,
                detail={
                    "code": "COURT_ALREADY_OCCUPIED",
                    "message": "A quadra selecionada já não está mais disponível nesse horário.",
                },
            )

        return HTTPException(
            status_code=409,
            detail={
                "code": "TIME_SLOT_UNAVAILABLE",
                "message": "Esse horário não está mais disponível.",
            },
        )

    if pgcode == "23503":
        return HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_REFERENCE",
                "message": "Referência inválida para a quadra selecionada.",
            },
        )

    return HTTPException(
        status_code=400,
        detail={
            "code": "EVENT_CREATE_ERROR",
            "message": f"Erro ao salvar locação: {str(orig) if orig else str(e)}",
        },
    )


def _normalize_notes(notes: str | None) -> str | None:
    if notes is None:
        return None
    value = notes.strip()
    return value or None


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_optional_whatsapp(value: str | None) -> str | None:
    cleaned = _normalize_optional_text(value)
    if not cleaned:
        return None
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    return digits or cleaned


def _local_tz() -> ZoneInfo:
    return ZoneInfo("America/Sao_Paulo")


def _court_rental_last_allowed_date() -> date:
    tz = _local_tz()
    today = datetime.now(tz).date()
    return today + timedelta(days=60)


def _round_up_to_next_slot(dt: datetime, slot_minutes: int) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    remainder = dt.minute % slot_minutes
    if remainder == 0:
        return dt
    return dt + timedelta(minutes=slot_minutes - remainder)


def _validate_court_rental_date_window(target_date: date) -> None:
    tz = _local_tz()
    today = datetime.now(tz).date()
    max_date = _court_rental_last_allowed_date()

    if target_date < today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "COURT_RENTAL_DATE_BEFORE_TODAY",
                "message": "A locação só pode ser agendada a partir de hoje.",
            },
        )

    if target_date > max_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "COURT_RENTAL_DATE_OUT_OF_WINDOW",
                "message": "A locação só pode ser agendada em até 60 dias a partir de hoje.",
            },
        )


def _validate_court_rental_slot_duration(start_at: datetime, end_at: datetime) -> None:
    duration_minutes = int((end_at - start_at).total_seconds() / 60)
    if duration_minutes < 60 or duration_minutes % 60 != 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_RENTAL_DURATION",
                "message": "A locação deve ter duração mínima de 1 hora e respeitar blocos de 60 minutos.",
            },
        )


def _validate_court_rental_not_in_past(start_at: datetime) -> None:
    now = datetime.now(_local_tz())
    if start_at.astimezone(_local_tz()) <= now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "COURT_RENTAL_TIME_IN_PAST",
                "message": "Não é possível agendar ou remarcar locação para horário passado.",
            },
        )


def _get_user_or_404(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")
    return user


def _get_student_or_404(db: Session, student_id: UUID) -> Student:
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aluno não encontrado")
    return student


def _get_current_user_row(db: Session, user_id: str):
    return (
        db.execute(
            text(
                """
                SELECT id, email, role, is_active, full_name, whatsapp
                FROM public.users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        .mappings()
        .first()
    )


def _require_admin(db: Session, user_id: str):
    user = _get_current_user_row(db, user_id)
    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário inválido",
        )
    if not str(user["role"]).startswith("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem gerenciar locações de quadra.",
        )
    return user


def _find_student_id_for_user(db: Session, user_id: UUID) -> UUID | None:
    return db.execute(
        text(
            """
            SELECT id
            FROM public.students
            WHERE user_id = :user_id
            ORDER BY created_at ASC
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    ).scalar_one_or_none()


def _get_court_name(db: Session, court_id: UUID) -> str:
    court_name = db.execute(
        text("SELECT name FROM public.courts WHERE id = :court_id"),
        {"court_id": court_id},
    ).scalar_one_or_none()
    if not court_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "COURT_NOT_FOUND", "message": "Quadra não encontrada."},
        )
    return str(court_name)


def _list_available_courts(db: Session, start_at: datetime, end_at: datetime):
    sql = text("SELECT * FROM public.fn_quadras_disponiveis(:p_from, :p_to)")
    return db.execute(sql, {"p_from": start_at, "p_to": end_at}).mappings().all()


def _list_active_courts(db: Session):
    sql = text(
        """
        SELECT
          c.id AS court_id,
          c.name AS court_name,
          c.surface_type AS surface_type,
          c.cover_type AS cover_type,
          c.image_url AS image_url,
          c.short_description AS short_description
        FROM public.courts c
        WHERE c.is_active IS TRUE
        ORDER BY c.name
        """
    )
    return db.execute(sql).mappings().all()


def _court_slot_is_still_available(
    db: Session,
    start_at: datetime,
    end_at: datetime,
    court_id: UUID,
) -> bool:
    available_courts = _list_available_courts(db, start_at, end_at)
    return any(item["court_id"] == court_id for item in available_courts)


def _build_legacy_rental_slots(
    db: Session,
    *,
    start_day: date,
    days: int,
    slot_minutes: int,
    day_start_hour: int,
    day_end_hour: int,
    max_allowed_date: date,
    court_id: UUID | None = None,
) -> list[CourtRentalSlotOut]:
    tz = _local_tz()
    today = datetime.now(tz).date()
    slots: list[CourtRentalSlotOut] = []
    seen: set[tuple[datetime, UUID]] = set()

    for day_offset in range(days):
        current_day = start_day + timedelta(days=day_offset)
        if current_day > max_allowed_date:
            break

        window_start = datetime.combine(current_day, time(hour=day_start_hour), tzinfo=tz)
        window_end = datetime.combine(current_day, time(hour=day_end_hour), tzinfo=tz)
        slot_delta = timedelta(minutes=slot_minutes)

        if current_day == today:
            now_local = datetime.now(tz)
            earliest_start = _round_up_to_next_slot(now_local, slot_minutes)
            slot_start = max(window_start, earliest_start)
        else:
            slot_start = window_start

        while slot_start + slot_delta <= window_end:
            slot_end = slot_start + slot_delta
            available_courts = _list_available_courts(db, slot_start, slot_end)
            for court in available_courts:
                if court_id is not None and court["court_id"] != court_id:
                    continue
                dedupe_key = (slot_start, court["court_id"])
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                slots.append(
                    CourtRentalSlotOut(
                        start_at=slot_start,
                        end_at=slot_end,
                        court_id=court["court_id"],
                        court_name=court["court_name"],
                    )
                )
            slot_start = slot_end

    slots.sort(key=lambda item: (item.start_at, item.court_name))
    return slots


def _get_court_rental_slots_for_range(
    db: Session,
    *,
    start_day: date,
    days: int,
    slot_minutes: int,
    day_start_hour: int,
    day_end_hour: int,
    max_allowed_date: date,
    court_id: UUID | None = None,
) -> list[CourtRentalSlotOut]:
    return _build_legacy_rental_slots(
        db,
        start_day=start_day,
        days=days,
        slot_minutes=slot_minutes,
        day_start_hour=day_start_hour,
        day_end_hour=day_end_hour,
        max_allowed_date=max_allowed_date,
        court_id=court_id,
    )


def _build_court_rental_court_cards(
    db: Session,
    *,
    start_day: date,
    days: int,
    slot_minutes: int,
    day_start_hour: int,
    day_end_hour: int,
    max_allowed_date: date,
) -> list[CourtRentalCourtCardOut]:
    active_courts = _list_active_courts(db)
    cards: list[CourtRentalCourtCardOut] = []

    for court in active_courts:
        court_slots = _get_court_rental_slots_for_range(
            db,
            start_day=start_day,
            days=days,
            slot_minutes=slot_minutes,
            day_start_hour=day_start_hour,
            day_end_hour=day_end_hour,
            max_allowed_date=max_allowed_date,
            court_id=court["court_id"],
        )
        has_slots = len(court_slots) > 0
        first_slot = court_slots[0] if has_slots else None
        cards.append(
            CourtRentalCourtCardOut(
                court_id=court["court_id"],
                court_name=court["court_name"],
                surface_type=court["surface_type"],
                cover_type=court["cover_type"],
                image_url=court["image_url"],
                short_description=court["short_description"],
                has_slots_in_range=has_slots,
                available_slots_count=len(court_slots),
                next_available_start_at=first_slot.start_at if first_slot else None,
                next_available_end_at=first_slot.end_at if first_slot else None,
                availability_message=(
                    "Tem horários disponíveis no período selecionado."
                    if has_slots
                    else "Sem horários disponíveis no período selecionado."
                ),
            )
        )

    return cards


def _get_change_policy(start_at: datetime) -> tuple[bool, bool, datetime | None, str, str]:
    tz = _local_tz()
    now = datetime.now(tz)
    local_start = start_at.astimezone(tz)

    if local_start <= now:
        return (
            False,
            False,
            None,
            (
                "Cancelamentos podem ser feitos até o início da locação. "
                "Remarcações respeitam a antecedência mínima definida pela escola."
            ),
            "A locação já começou ou já passou. Não é mais possível cancelar ou remarcar.",
        )

    today = now.date()
    rental_date = local_start.date()

    if rental_date == today:
        reschedule_deadline = local_start - timedelta(hours=2)
        reschedule_rule = (
            "Para locações agendadas no mesmo dia, a remarcação deve ocorrer "
            "com no mínimo 2 horas de antecedência."
        )
    elif rental_date == today + timedelta(days=1):
        reschedule_deadline = local_start - timedelta(hours=6)
        reschedule_rule = (
            "Para locações agendadas para o dia seguinte, a remarcação deve ocorrer "
            "com no mínimo 6 horas de antecedência."
        )
    else:
        reschedule_deadline = local_start - timedelta(hours=48)
        reschedule_rule = (
            "Para locações agendadas a partir de dois dias à frente, a remarcação deve ocorrer "
            "com no mínimo 48 horas de antecedência."
        )

    can_cancel = now < local_start
    can_reschedule = now <= reschedule_deadline
    combined_rule = f"Cancelamentos podem ser feitos até o início da locação. {reschedule_rule}"

    if can_reschedule:
        status_message = (
            "Você ainda pode cancelar esta locação até o início do horário agendado "
            "e também remarcar dentro do prazo atual."
        )
    else:
        status_message = (
            "Você ainda pode cancelar esta locação até o início do horário agendado, "
            "mas o prazo para remarcação já expirou."
        )

    return can_cancel, can_reschedule, reschedule_deadline, combined_rule, status_message


def _get_email_sender():
    if settings.email_sender_backend.lower() == "smtp":
        cfg = SmtpConfig(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            mail_from=settings.smtp_from,
            use_tls=settings.smtp_use_tls,
        )
        return SmtpEmailSender(cfg)
    return ConsoleEmailSender()


def _format_when_label(start_at: datetime, end_at: datetime) -> str:
    tz = _local_tz()
    start_local = start_at.astimezone(tz)
    end_local = end_at.astimezone(tz)
    return f"{start_local.strftime('%d/%m/%Y')} das {start_local.strftime('%H:%M')} às {end_local.strftime('%H:%M')}"


def _build_email_content(
    *,
    action: str,
    recipient_name: str | None,
    start_at: datetime,
    end_at: datetime,
    court_name: str,
    total_amount: Decimal | None = None,
    pix_key: str | None = None,
    pix_qr_code_payload: str | None = None,
) -> tuple[str, str, str]:
    person_name = recipient_name or "cliente"
    amount_label = f"R$ {total_amount:.2f}" if total_amount is not None else None

    if action == "scheduled":
        subject = "Sócrates Tênis — locação de quadra confirmada"
        intro = "Sua locação foi confirmada com sucesso."
        extra = ""
    elif action == "rescheduled":
        subject = "Sócrates Tênis — locação de quadra remarcada"
        intro = "Sua locação foi remarcada com sucesso."
        extra = ""
    elif action == "cancelled":
        subject = "Sócrates Tênis — locação de quadra cancelada"
        intro = "Sua locação foi cancelada com sucesso."
        extra = ""
    elif action == "payment_pending":
        subject = "Sócrates Tênis — pagamento pendente da locação"
        intro = "Recebemos sua solicitação de locação e ela está aguardando pagamento/comprovante."
        parts = []
        if amount_label:
            parts.append(f"Valor previsto: {amount_label}")
        if pix_key:
            parts.append(f"Chave Pix: {pix_key}")
        if pix_qr_code_payload:
            parts.append(f"Código Pix/QR: {pix_qr_code_payload}")
        parts.append("Após o pagamento, envie o comprovante pelo WhatsApp indicado pela escola.")
        extra = "\n".join(parts)
    elif action == "proof_received":
        subject = "Sócrates Tênis — comprovante recebido"
        intro = "Recebemos seu comprovante e a locação está aguardando validação da administração."
        parts = []
        if amount_label:
            parts.append(f"Valor informado: {amount_label}")
        parts.append(
            "Assim que a administração concluir a análise, você receberá a confirmação final por e-mail."
        )
        extra = "\n".join(parts)
    elif action == "payment_approved":
        subject = "Sócrates Tênis — pagamento aprovado e locação confirmada"
        intro = "Seu pagamento foi aprovado e a locação está confirmada."
        extra = f"Valor aprovado: {amount_label}\n" if amount_label else ""
    elif action == "payment_rejected":
        subject = "Sócrates Tênis — comprovante reprovado"
        intro = "A locação não pôde ser confirmada porque o pagamento/comprovante foi reprovado."
        extra = "Entre em contato com a escola para regularizar a reserva."
    else:
        subject = "Sócrates Tênis — atualização na sua locação"
        intro = "Houve uma atualização na sua locação de quadra."
        extra = "Confira os dados atualizados abaixo."

    when_label = _format_when_label(start_at, end_at)
    text_body = (
        f"Olá, {person_name}!\n\n"
        f"{intro}\n\n"
        f"Quadra: {court_name}\n"
        f"Horário: {when_label}\n"
        + (f"{extra}\n\n" if extra else "\n")
        + "Em caso de dúvida, entre em contato com a escola.\n"
    )

    extra_html = f"<p>{extra.replace(chr(10), '<br/>')}</p>" if extra else ""
    html_body = f"""
    <div style=\"font-family:Arial,sans-serif;line-height:1.5\">
      <h2>Sócrates Tênis</h2>
      <p>Olá, <strong>{person_name}</strong>!</p>
      <p>{intro}</p>
      <ul>
        <li><strong>Quadra:</strong> {court_name}</li>
        <li><strong>Horário:</strong> {when_label}</li>
      </ul>
      {extra_html}
      <p>Em caso de dúvida, entre em contato com a escola.</p>
    </div>
    """

    return subject, text_body, html_body


def _send_court_rental_email(
    *,
    to_email: str | None,
    recipient_name: str | None,
    action: str,
    start_at: datetime,
    end_at: datetime,
    court_name: str,
    total_amount: Decimal | None = None,
    pix_key: str | None = None,
    pix_qr_code_payload: str | None = None,
) -> bool:
    if not to_email:
        return False

    subject, text_body, html_body = _build_email_content(
        action=action,
        recipient_name=recipient_name,
        start_at=start_at,
        end_at=end_at,
        court_name=court_name,
        total_amount=total_amount,
        pix_key=pix_key,
        pix_qr_code_payload=pix_qr_code_payload,
    )

    try:
        sender = _get_email_sender()
        sender.send_email(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )
        return True
    except EmailSendError:
        return False


def _serialize_rental(rental: CourtRental) -> CourtRentalOut:
    return CourtRentalOut(
        id=rental.id,
        user_id=rental.user_id,
        created_by_user_id=rental.created_by_user_id,
        customer_user_id=rental.customer_user_id,
        customer_student_id=rental.customer_student_id,
        payment_reviewed_by_user_id=rental.payment_reviewed_by_user_id,
        event_id=rental.event_id,
        origin=rental.origin,
        status=rental.status,
        payment_status=rental.payment_status,
        customer_name=rental.customer_name,
        customer_email=rental.customer_email,
        customer_whatsapp=rental.customer_whatsapp,
        price_per_hour=rental.price_per_hour,
        total_amount=rental.total_amount,
        payment_received_amount=rental.payment_received_amount,
        pix_key=rental.pix_key,
        pix_qr_code_payload=rental.pix_qr_code_payload,
        requested_at=rental.requested_at,
        scheduled_at=rental.scheduled_at,
        confirmed_at=rental.confirmed_at,
        completed_at=rental.completed_at,
        cancelled_at=rental.cancelled_at,
        confirmation_email_sent_at=rental.confirmation_email_sent_at,
        payment_proof_submitted_at=rental.payment_proof_submitted_at,
        payment_reviewed_at=rental.payment_reviewed_at,
        payment_amount_matches_expected=rental.payment_amount_matches_expected,
        payment_review_notes=rental.payment_review_notes,
        notes=rental.notes,
        created_at=rental.created_at,
        updated_at=rental.updated_at,
    )


def _create_event(
    db: Session,
    *,
    court_id: UUID,
    student_id: UUID | None,
    created_by: UUID | None,
    start_at: datetime,
    end_at: datetime,
    notes: str | None,
):
    return (
        db.execute(
            text(
                """
                INSERT INTO public.events (
                  court_id, teacher_id, student_id, created_by,
                  kind, status, start_at, end_at, notes
                )
                VALUES (
                  :court_id, NULL, :student_id, :created_by,
                  'locacao', 'confirmado', :start_at, :end_at, :notes
                )
                RETURNING id, court_id, start_at, end_at, notes
                """
            ),
            {
                "court_id": court_id,
                "student_id": student_id,
                "created_by": created_by,
                "start_at": start_at,
                "end_at": end_at,
                "notes": notes,
            },
        )
        .mappings()
        .first()
    )


def _cancel_event(db: Session, event_id: UUID | None) -> None:
    if event_id is None:
        return
    db.execute(
        text(
            """
            UPDATE public.events
            SET status = 'cancelado'
            WHERE id = :event_id
            """
        ),
        {"event_id": event_id},
    )


def _load_customer_identity(
    db: Session,
    *,
    customer_user_id: UUID | None,
    customer_student_id: UUID | None,
    customer_name: str | None,
    customer_email: str | None,
    customer_whatsapp: str | None,
) -> dict[str, Any]:
    resolved_name = _normalize_optional_text(customer_name)
    resolved_email = _normalize_optional_text(customer_email)
    resolved_whatsapp = _normalize_optional_whatsapp(customer_whatsapp)
    resolved_user_id = customer_user_id
    resolved_student_id = customer_student_id
    legacy_user_id: UUID | None = customer_user_id

    if customer_user_id is not None:
        linked_user = _get_user_or_404(db, customer_user_id)
        if resolved_name is None:
            resolved_name = _normalize_optional_text(linked_user.full_name)
        if resolved_email is None:
            resolved_email = _normalize_optional_text(linked_user.email)
        if resolved_whatsapp is None:
            resolved_whatsapp = _normalize_optional_whatsapp(linked_user.whatsapp)
        if resolved_student_id is None:
            resolved_student_id = _find_student_id_for_user(db, linked_user.id)

    if customer_student_id is not None:
        linked_student = _get_student_or_404(db, customer_student_id)
        if resolved_name is None:
            resolved_name = _normalize_optional_text(linked_student.full_name)
        if resolved_email is None:
            resolved_email = _normalize_optional_text(linked_student.email)
        if resolved_whatsapp is None:
            resolved_whatsapp = _normalize_optional_whatsapp(linked_student.phone)
        if legacy_user_id is None and linked_student.user_id is not None:
            legacy_user_id = linked_student.user_id
        if resolved_user_id is None and linked_student.user_id is not None:
            resolved_user_id = linked_student.user_id

    if (
        resolved_name is None
        and resolved_email is None
        and resolved_whatsapp is None
        and resolved_user_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Informe ao menos um vínculo de cliente ou dados mínimos de contato.",
        )

    return {
        "user_id": legacy_user_id,
        "customer_user_id": resolved_user_id,
        "customer_student_id": resolved_student_id,
        "customer_name": resolved_name,
        "customer_email": resolved_email,
        "customer_whatsapp": resolved_whatsapp,
    }


def _resolve_payment_state_for_admin_create(
    data: CourtRentalAdminCreateIn,
) -> tuple[str, str, datetime | None]:
    has_payment_context = any(
        value is not None
        for value in [
            data.price_per_hour,
            data.total_amount,
            data.pix_key,
            data.pix_qr_code_payload,
        ]
    )
    if has_payment_context:
        return "awaiting_payment", "pending", None
    return "scheduled", "not_required", datetime.now(_local_tz())


def _ensure_slot_available_or_409(
    db: Session, *, court_id: UUID, start_at: datetime, end_at: datetime
) -> None:
    if not _court_slot_is_still_available(
        db=db,
        start_at=start_at,
        end_at=end_at,
        court_id=court_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SLOT_NO_LONGER_AVAILABLE",
                "message": "O horário selecionado não está mais disponível. Atualize a agenda e escolha outro slot.",
            },
        )


def _build_pending_payment_message(
    total_amount: Decimal | None, pix_key: str | None, pix_qr_code_payload: str | None
) -> str:
    if total_amount is not None and (pix_key or pix_qr_code_payload):
        return "Siga as instruções abaixo para pagamento e envio do comprovante."
    return (
        "Sua reserva foi registrada e está aguardando definição das instruções de pagamento pela administração. "
        "Você pode acompanhar o status aqui e enviar o comprovante assim que receber a cobrança."
    )


def _resolve_public_pending_payment_context(
    *,
    court_name: str,
    start_at: datetime,
    end_at: datetime,
) -> tuple[Decimal | None, Decimal | None, str | None, str | None]:
    # Nesta etapa, a locação pública já nasce pendente de pagamento/aprovação,
    # mas o valor/hora definitivo ainda será parametrizado pela administração.
    # Mantemos os campos preparados para a próxima fase sem inventar cobrança real.
    when_label = _format_when_label(start_at, end_at)
    pix_qr_code_payload = f"PENDENTE_ADMIN::{court_name}::{when_label}"
    return None, None, None, pix_qr_code_payload


def _get_upcoming_rental_rows(db: Session, owner_user_id: UUID):
    return (
        db.execute(
            text(
                """
                SELECT
                  cr.id AS rental_id,
                  cr.event_id AS event_id,
                  cr.status AS status,
                  cr.payment_status AS payment_status,
                  cr.origin AS origin,
                  cr.customer_name AS customer_name,
                  cr.customer_email AS customer_email,
                  cr.customer_whatsapp AS customer_whatsapp,
                  cr.notes AS notes,
                  e.start_at AS start_at,
                  e.end_at AS end_at,
                  e.court_id AS court_id,
                  c.name AS court_name
                FROM public.court_rentals cr
                JOIN public.events e
                  ON e.id = cr.event_id
                JOIN public.courts c
                  ON c.id = e.court_id
                WHERE COALESCE(cr.customer_user_id, cr.user_id) = :user_id
                  AND cr.status IN ('scheduled', 'confirmed', 'awaiting_payment', 'awaiting_proof', 'awaiting_admin_review')
                  AND e.kind = 'locacao'
                  AND e.status = 'confirmado'
                  AND e.end_at > now()
                ORDER BY e.start_at ASC, cr.created_at DESC
                """
            ),
            {"user_id": owner_user_id},
        )
        .mappings()
        .all()
    )


def _get_owned_rental_row(db: Session, owner_user_id: UUID, rental_id: UUID):
    return (
        db.execute(
            text(
                """
                SELECT
                  cr.id AS rental_id,
                  cr.event_id AS event_id,
                  cr.status AS status,
                  cr.payment_status AS payment_status,
                  cr.origin AS origin,
                  cr.customer_name AS customer_name,
                  cr.customer_email AS customer_email,
                  cr.customer_whatsapp AS customer_whatsapp,
                  cr.total_amount AS total_amount,
                  cr.pix_key AS pix_key,
                  cr.pix_qr_code_payload AS pix_qr_code_payload,
                  cr.notes AS notes,
                  e.start_at AS start_at,
                  e.end_at AS end_at,
                  e.court_id AS court_id,
                  c.name AS court_name
                FROM public.court_rentals cr
                JOIN public.events e
                  ON e.id = cr.event_id
                JOIN public.courts c
                  ON c.id = e.court_id
                WHERE COALESCE(cr.customer_user_id, cr.user_id) = :user_id
                  AND cr.id = :rental_id
                  AND cr.status IN ('scheduled', 'confirmed', 'awaiting_payment', 'awaiting_proof', 'awaiting_admin_review')
                  AND e.kind = 'locacao'
                  AND e.status = 'confirmado'
                LIMIT 1
                """
            ),
            {"user_id": owner_user_id, "rental_id": rental_id},
        )
        .mappings()
        .first()
    )


def _get_admin_rental_row(db: Session, rental_id: UUID):
    return (
        db.execute(
            text(
                """
                SELECT
                  cr.id,
                  cr.event_id,
                  cr.origin,
                  cr.status,
                  cr.payment_status,
                  cr.customer_name,
                  cr.customer_email,
                  cr.customer_whatsapp,
                  cr.total_amount,
                  cr.payment_amount_matches_expected,
                  cr.payment_proof_submitted_at,
                  cr.payment_reviewed_at,
                  cr.confirmed_at,
                  cr.created_at,
                  e.court_id,
                  c.name AS court_name,
                  e.start_at,
                  e.end_at
                FROM public.court_rentals cr
                LEFT JOIN public.events e
                  ON e.id = cr.event_id
                LEFT JOIN public.courts c
                  ON c.id = e.court_id
                WHERE cr.id = :rental_id
                LIMIT 1
                """
            ),
            {"rental_id": rental_id},
        )
        .mappings()
        .first()
    )


def _mark_confirmation_email_if_sent(db: Session, rental: CourtRental, email_sent: bool) -> None:
    if not email_sent:
        return
    rental.confirmation_email_sent_at = datetime.now(_local_tz())
    db.commit()
    db.refresh(rental)


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _calculate_total_amount(
    start_at: datetime, end_at: datetime, price_per_hour: Decimal
) -> Decimal:
    duration_seconds = Decimal(str((end_at - start_at).total_seconds()))
    hours = duration_seconds / Decimal("3600")
    return _quantize_money(price_per_hour * hours)


def _build_admin_pix_payload(
    *,
    pix_key: str,
    total_amount: Decimal,
    court_name: str,
    start_at: datetime,
    end_at: datetime,
) -> str:
    txid_source = f"CTR{start_at:%Y%m%d%H%M}{end_at:%H%M}"
    txid = "".join(ch for ch in txid_source if ch.isalnum())[:25] or "***"

    try:
        return generate_pix_payload(
            pix_key=pix_key,
            merchant_name="Socrates Tenis",
            merchant_city="Sao Paulo",
            amount=total_amount,
            txid=txid,
        )
    except PixPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Nao foi possivel gerar o payload Pix: {exc}",
        ) from exc


def _get_rental_event_snapshot_or_404(db: Session, event_id: UUID | None):
    if event_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evento da locação não encontrado."
        )

    row = (
        db.execute(
            text(
                """
                SELECT e.id, e.start_at, e.end_at, e.court_id, c.name AS court_name
                FROM public.events e
                JOIN public.courts c
                  ON c.id = e.court_id
                WHERE e.id = :event_id
                LIMIT 1
                """
            ),
            {"event_id": event_id},
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evento da locação não encontrado."
        )
    return row


@router.get("/eligibility", response_model=CourtRentalEligibilityOut)
def court_rental_eligibility(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    _get_user_or_404(db, UUID(user_id))
    return CourtRentalEligibilityOut(
        eligible=True,
        message="Você pode solicitar locações de quadra conforme a disponibilidade da agenda.",
    )


@router.get("/upcoming", response_model=CourtRentalUpcomingListOut)
def upcoming_court_rentals(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    current_user = _get_user_or_404(db, UUID(user_id))
    rows = _get_upcoming_rental_rows(db, current_user.id)

    if not rows:
        return CourtRentalUpcomingListOut(
            items=[], message="Você não possui locações agendadas no momento."
        )

    items: list[CourtRentalUpcomingItemOut] = []
    for row in rows:
        can_cancel, can_reschedule, deadline_at, rule_message, status_message = _get_change_policy(
            row["start_at"]
        )
        items.append(
            CourtRentalUpcomingItemOut(
                rental_id=row["rental_id"],
                event_id=row["event_id"],
                status=row["status"],
                payment_status=row["payment_status"],
                origin=row["origin"],
                start_at=row["start_at"],
                end_at=row["end_at"],
                court_id=row["court_id"],
                court_name=row["court_name"],
                customer_name=row["customer_name"],
                customer_email=row["customer_email"],
                customer_whatsapp=row["customer_whatsapp"],
                notes=row["notes"],
                can_cancel=can_cancel,
                can_reschedule=can_reschedule,
                change_deadline_at=deadline_at,
                change_rule_message=rule_message,
                change_status_message=status_message,
            )
        )

    return CourtRentalUpcomingListOut(
        items=items, message="Locações agendadas localizadas com sucesso."
    )


@router.get("/courts", response_model=list[CourtRentalCourtCardOut])
def court_rental_courts_overview(
    db: Annotated[Session, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=7)] = 7,
    slot_minutes: Annotated[int, Query(ge=60, le=60)] = 60,
    day_start_hour: Annotated[int, Query(ge=6, le=22)] = 8,
    day_end_hour: Annotated[int, Query(ge=7, le=23)] = 22,
):
    if day_start_hour >= day_end_hour:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="day_start_hour precisa ser menor que day_end_hour",
        )

    tz = _local_tz()
    today = datetime.now(tz).date()
    max_allowed_date = _court_rental_last_allowed_date()
    start_day = from_date or today
    _validate_court_rental_date_window(start_day)

    return _build_court_rental_court_cards(
        db,
        start_day=start_day,
        days=days,
        slot_minutes=slot_minutes,
        day_start_hour=day_start_hour,
        day_end_hour=day_end_hour,
        max_allowed_date=max_allowed_date,
    )


@router.get("/courts/{court_id}/slots", response_model=list[CourtRentalSlotOut])
def court_rental_slots_by_court(
    court_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=7)] = 7,
    slot_minutes: Annotated[int, Query(ge=60, le=60)] = 60,
    day_start_hour: Annotated[int, Query(ge=6, le=22)] = 8,
    day_end_hour: Annotated[int, Query(ge=7, le=23)] = 22,
):
    if day_start_hour >= day_end_hour:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="day_start_hour precisa ser menor que day_end_hour",
        )

    active_courts = _list_active_courts(db)
    if not any(item["court_id"] == court_id for item in active_courts):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "COURT_NOT_FOUND",
                "message": "Quadra ativa não encontrada para locação.",
            },
        )

    tz = _local_tz()
    today = datetime.now(tz).date()
    max_allowed_date = _court_rental_last_allowed_date()
    start_day = from_date or today
    _validate_court_rental_date_window(start_day)

    return _get_court_rental_slots_for_range(
        db,
        start_day=start_day,
        days=days,
        slot_minutes=slot_minutes,
        day_start_hour=day_start_hour,
        day_end_hour=day_end_hour,
        max_allowed_date=max_allowed_date,
        court_id=court_id,
    )


@router.get("/slots", response_model=list[CourtRentalSlotOut])
def court_rental_slots(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=30)] = 7,
    slot_minutes: Annotated[int, Query(ge=60, le=60)] = 60,
    day_start_hour: Annotated[int, Query(ge=6, le=22)] = 8,
    day_end_hour: Annotated[int, Query(ge=7, le=23)] = 22,
):
    _get_user_or_404(db, UUID(user_id))
    if day_start_hour >= day_end_hour:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="day_start_hour precisa ser menor que day_end_hour",
        )

    tz = _local_tz()
    today = datetime.now(tz).date()
    max_allowed_date = _court_rental_last_allowed_date()
    start_day = from_date or today
    _validate_court_rental_date_window(start_day)

    return _get_court_rental_slots_for_range(
        db,
        start_day=start_day,
        days=days,
        slot_minutes=slot_minutes,
        day_start_hour=day_start_hour,
        day_end_hour=day_end_hour,
        max_allowed_date=max_allowed_date,
    )


@router.get("/{rental_id}/payment-instructions", response_model=CourtRentalPaymentInstructionOut)
def get_court_rental_payment_instructions(
    rental_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    current_user = _get_user_or_404(db, UUID(user_id))
    row = _get_owned_rental_row(db, current_user.id, rental_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locação não encontrada.")
    return CourtRentalPaymentInstructionOut(
        rental_id=row["rental_id"],
        payment_status=row["payment_status"],
        total_amount=row["total_amount"],
        pix_key=row["pix_key"],
        pix_qr_code_payload=row["pix_qr_code_payload"],
        message=(
            _build_pending_payment_message(
                row["total_amount"],
                row["pix_key"],
                row["pix_qr_code_payload"],
            )
            if row["payment_status"] in {"pending", "proof_sent", "under_review"}
            else "Esta locação não possui cobrança pendente no momento."
        ),
    )


@router.post(
    "/schedule", response_model=CourtRentalScheduleOut, status_code=status.HTTP_201_CREATED
)
def schedule_court_rental(
    data: CourtRentalScheduleIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    current_user = _get_user_or_404(db, UUID(user_id))

    if data.end_at <= data.start_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_TIME_RANGE",
                "message": "end_at precisa ser maior que start_at.",
            },
        )

    _validate_court_rental_slot_duration(data.start_at, data.end_at)
    _validate_court_rental_date_window(data.start_at.astimezone(_local_tz()).date())
    _validate_court_rental_not_in_past(data.start_at)
    _ensure_slot_available_or_409(
        db, court_id=data.court_id, start_at=data.start_at, end_at=data.end_at
    )

    student_id = _find_student_id_for_user(db, current_user.id)
    court_name = _get_court_name(db, data.court_id)
    price_per_hour, total_amount, pix_key, pix_qr_code_payload = (
        _resolve_public_pending_payment_context(
            court_name=court_name,
            start_at=data.start_at,
            end_at=data.end_at,
        )
    )

    try:
        event_row = _create_event(
            db,
            court_id=data.court_id,
            student_id=student_id,
            created_by=current_user.id,
            start_at=data.start_at,
            end_at=data.end_at,
            notes=_normalize_notes(data.notes)
            or "Solicitação pública de locação de quadra aguardando pagamento.",
        )
        rental = CourtRental(
            user_id=current_user.id,
            created_by_user_id=current_user.id,
            customer_user_id=current_user.id,
            customer_student_id=student_id,
            customer_name=_normalize_optional_text(current_user.full_name),
            customer_email=_normalize_optional_text(current_user.email),
            customer_whatsapp=_normalize_optional_whatsapp(current_user.whatsapp),
            event_id=event_row["id"],
            origin="public_landing",
            status="awaiting_payment",
            payment_status="pending",
            price_per_hour=price_per_hour,
            total_amount=total_amount,
            pix_key=pix_key,
            pix_qr_code_payload=pix_qr_code_payload,
            scheduled_at=data.start_at,
            confirmed_at=None,
            notes=_normalize_notes(data.notes),
        )
        db.add(rental)
        db.commit()
        db.refresh(rental)
    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e

    email_sent = _send_court_rental_email(
        to_email=current_user.email,
        recipient_name=current_user.full_name,
        action="payment_pending",
        start_at=event_row["start_at"],
        end_at=event_row["end_at"],
        court_name=court_name,
        total_amount=total_amount,
        pix_key=pix_key,
        pix_qr_code_payload=pix_qr_code_payload,
    )
    _mark_confirmation_email_if_sent(db, rental, email_sent)

    message = _build_pending_payment_message(total_amount, pix_key, pix_qr_code_payload)
    if email_sent:
        message = f"{message} Enviamos também um e-mail com as orientações atuais para o cadastro informado."

    return CourtRentalScheduleOut(
        rental_id=rental.id,
        event_id=event_row["id"],
        status=rental.status,
        payment_status=rental.payment_status,
        origin=rental.origin,
        start_at=event_row["start_at"],
        end_at=event_row["end_at"],
        court_id=event_row["court_id"],
        message=message,
        email_sent=email_sent,
    )


@router.post("/{rental_id}/payment-proof", response_model=CourtRentalProofSubmissionOut)
def submit_court_rental_payment_proof(
    rental_id: UUID,
    data: CourtRentalProofSubmissionIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    current_user = _get_user_or_404(db, UUID(user_id))
    row = _get_owned_rental_row(db, current_user.id, rental_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locação não encontrada.")

    rental = db.get(CourtRental, row["rental_id"])
    if not rental:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Registro da locação não encontrado."
        )

    if rental.status in {
        "cancelled",
        "completed",
        "rejected",
        "confirmed",
    } or rental.payment_status in {"approved", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Esta locação não está mais apta a receber comprovante.",
        )

    received_amount = (
        _quantize_money(Decimal(str(data.payment_received_amount)))
        if data.payment_received_amount is not None
        else rental.payment_received_amount
    )
    proof_notes = _normalize_notes(data.payment_review_notes)

    rental.payment_status = "proof_sent"
    rental.status = "awaiting_admin_review"
    rental.payment_proof_submitted_at = datetime.now(_local_tz())
    rental.payment_received_amount = received_amount
    if proof_notes is not None:
        rental.payment_review_notes = proof_notes

    db.commit()
    db.refresh(rental)

    email_sent = _send_court_rental_email(
        to_email=rental.customer_email,
        recipient_name=rental.customer_name,
        action="proof_received",
        start_at=row["start_at"],
        end_at=row["end_at"],
        court_name=row["court_name"],
        total_amount=received_amount or rental.total_amount,
        pix_key=rental.pix_key,
        pix_qr_code_payload=rental.pix_qr_code_payload,
    )
    _mark_confirmation_email_if_sent(db, rental, email_sent)

    message = "Recebemos o seu comprovante e a locação agora está aguardando a validação da administração."
    if email_sent:
        message = f"{message} Enviamos também um e-mail confirmando o recebimento para o cadastro informado."

    return CourtRentalProofSubmissionOut(
        rental_id=rental.id,
        status=rental.status,
        payment_status=rental.payment_status,
        payment_proof_submitted_at=rental.payment_proof_submitted_at,
        payment_received_amount=rental.payment_received_amount,
        message=message,
        email_sent=email_sent,
    )


@router.post("/{rental_id}/cancel", response_model=CourtRentalCancelOut)
def cancel_court_rental(
    rental_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    current_user = _get_user_or_404(db, UUID(user_id))
    row = _get_owned_rental_row(db, current_user.id, rental_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "COURT_RENTAL_NOT_FOUND",
                "message": "Locação agendada não encontrada.",
            },
        )

    can_cancel, _can_reschedule, _deadline_at, _rule_message, status_message = _get_change_policy(
        row["start_at"]
    )
    if not can_cancel:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "COURT_RENTAL_CANCEL_WINDOW_EXPIRED", "message": status_message},
        )

    rental = db.get(CourtRental, row["rental_id"])
    if not rental:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "COURT_RENTAL_NOT_FOUND",
                "message": "Registro da locação não encontrado.",
            },
        )

    _cancel_event(db, row["event_id"])
    rental.status = "cancelled"
    rental.cancelled_at = datetime.now(_local_tz())
    db.commit()
    db.refresh(rental)

    email_sent = _send_court_rental_email(
        to_email=row["customer_email"],
        recipient_name=row["customer_name"],
        action="cancelled",
        start_at=row["start_at"],
        end_at=row["end_at"],
        court_name=row["court_name"],
    )
    _mark_confirmation_email_if_sent(db, rental, email_sent)

    message = "Sua locação de quadra foi cancelada com sucesso."
    if email_sent:
        message = f"{message} Enviamos também um e-mail de confirmação para o cadastro informado."

    return CourtRentalCancelOut(
        rental_id=rental.id,
        event_id=row["event_id"],
        status=rental.status,
        payment_status=rental.payment_status,
        message=message,
        email_sent=email_sent,
    )


@router.post("/{rental_id}/reschedule", response_model=CourtRentalRescheduleOut)
def reschedule_court_rental(
    rental_id: UUID,
    data: CourtRentalRescheduleIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    current_user = _get_user_or_404(db, UUID(user_id))
    row = _get_owned_rental_row(db, current_user.id, rental_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "COURT_RENTAL_NOT_FOUND",
                "message": "Locação agendada não encontrada.",
            },
        )

    _can_cancel, can_reschedule, _deadline_at, _rule_message, status_message = _get_change_policy(
        row["start_at"]
    )
    if not can_reschedule:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "COURT_RENTAL_RESCHEDULE_WINDOW_EXPIRED", "message": status_message},
        )

    if data.end_at <= data.start_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_TIME_RANGE",
                "message": "end_at precisa ser maior que start_at.",
            },
        )

    _validate_court_rental_slot_duration(data.start_at, data.end_at)
    _validate_court_rental_date_window(data.start_at.astimezone(_local_tz()).date())
    _validate_court_rental_not_in_past(data.start_at)
    _ensure_slot_available_or_409(
        db, court_id=data.court_id, start_at=data.start_at, end_at=data.end_at
    )

    rental = db.get(CourtRental, row["rental_id"])
    if not rental:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "COURT_RENTAL_NOT_FOUND",
                "message": "Registro da locação não encontrado.",
            },
        )

    old_event_id = row["event_id"]

    try:
        _cancel_event(db, old_event_id)
        new_event_row = _create_event(
            db,
            court_id=data.court_id,
            student_id=rental.customer_student_id,
            created_by=rental.created_by_user_id,
            start_at=data.start_at,
            end_at=data.end_at,
            notes=_normalize_notes(data.notes) or "Locação de quadra remarcada.",
        )
        rental.event_id = new_event_row["id"]
        if rental.status in {"scheduled", "confirmed"}:
            rental.status = "scheduled"
        rental.scheduled_at = data.start_at
        rental.notes = _normalize_notes(data.notes)
        db.commit()
        db.refresh(rental)
    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e

    court_name = _get_court_name(db, data.court_id)
    email_sent = _send_court_rental_email(
        to_email=rental.customer_email,
        recipient_name=rental.customer_name,
        action="rescheduled",
        start_at=new_event_row["start_at"],
        end_at=new_event_row["end_at"],
        court_name=court_name,
    )
    _mark_confirmation_email_if_sent(db, rental, email_sent)

    message = "Sua locação de quadra foi remarcada com sucesso."
    if email_sent:
        message = f"{message} Enviamos também um e-mail de confirmação para o cadastro informado."

    return CourtRentalRescheduleOut(
        rental_id=rental.id,
        old_event_id=old_event_id,
        new_event_id=new_event_row["id"],
        status=rental.status,
        payment_status=rental.payment_status,
        start_at=new_event_row["start_at"],
        end_at=new_event_row["end_at"],
        court_id=new_event_row["court_id"],
        message=message,
        email_sent=email_sent,
    )


@router.get("/admin/bookings", response_model=CourtRentalAdminListOut)
def admin_list_court_rentals(
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    payment_status_filter: Annotated[str | None, Query(alias="payment_status")] = None,
    origin: Annotated[str | None, Query()] = None,
):
    _require_admin(db, user_id)

    where_parts = ["1 = 1"]
    params: dict[str, Any] = {}

    if from_date is not None:
        where_parts.append("(e.start_at IS NULL OR e.start_at >= :from_dt)")
        params["from_dt"] = datetime.combine(from_date, time.min, tzinfo=_local_tz())
    if to_date is not None:
        where_parts.append("(e.start_at IS NULL OR e.start_at < :to_dt)")
        params["to_dt"] = datetime.combine(
            to_date + timedelta(days=1), time.min, tzinfo=_local_tz()
        )
    if status_filter:
        where_parts.append("cr.status = :status_filter")
        params["status_filter"] = status_filter
    if payment_status_filter:
        where_parts.append("cr.payment_status = :payment_status_filter")
        params["payment_status_filter"] = payment_status_filter
    if origin:
        where_parts.append("cr.origin = :origin")
        params["origin"] = origin

    rows = (
        db.execute(
            text(
                f"""
                SELECT
                  cr.id,
                  cr.origin,
                  cr.status,
                  cr.payment_status,
                  e.court_id,
                  c.name AS court_name,
                  e.start_at,
                  e.end_at,
                  cr.customer_name,
                  cr.customer_email,
                  cr.customer_whatsapp,
                  cr.total_amount,
                  cr.payment_amount_matches_expected,
                  cr.payment_proof_submitted_at,
                  cr.payment_reviewed_at,
                  cr.confirmed_at,
                  cr.created_at
                FROM public.court_rentals cr
                LEFT JOIN public.events e
                  ON e.id = cr.event_id
                LEFT JOIN public.courts c
                  ON c.id = e.court_id
                WHERE {" AND ".join(where_parts)}
                ORDER BY COALESCE(e.start_at, cr.created_at) DESC, cr.created_at DESC
                """
            ),
            params,
        )
        .mappings()
        .all()
    )

    items = [CourtRentalAdminListItemOut(**row) for row in rows]
    return CourtRentalAdminListOut(
        items=items, total=len(items), from_date=from_date, to_date=to_date
    )


@router.get("/admin/bookings/{rental_id}", response_model=CourtRentalOut)
def admin_get_court_rental(
    rental_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    rental = db.get(CourtRental, rental_id)
    if not rental:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locação não encontrada.")
    return _serialize_rental(rental)


@router.post(
    "/admin/bookings/{rental_id}/payment-definition",
    response_model=CourtRentalAdminPaymentDefinitionOut,
)
def admin_define_court_rental_payment(
    rental_id: UUID,
    data: CourtRentalAdminPaymentDefinitionIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    rental = db.get(CourtRental, rental_id)
    if not rental:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locação não encontrada.")

    if rental.status in {"cancelled", "completed", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Não é possível definir cobrança para uma locação encerrada, cancelada ou rejeitada.",
        )

    event_info = _get_rental_event_snapshot_or_404(db, rental.event_id)
    normalized_pix_key = _normalize_optional_text(data.pix_key)
    if not normalized_pix_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Informe uma chave Pix válida para gerar a cobrança.",
        )

    price_per_hour = _quantize_money(Decimal(str(data.price_per_hour)))
    total_amount = (
        _quantize_money(Decimal(str(data.total_amount)))
        if data.total_amount is not None
        else _calculate_total_amount(event_info["start_at"], event_info["end_at"], price_per_hour)
    )
    pix_qr_code_payload = _normalize_optional_text(
        data.pix_qr_code_payload
    ) or _build_admin_pix_payload(
        pix_key=normalized_pix_key,
        total_amount=total_amount,
        court_name=str(event_info["court_name"]),
        start_at=event_info["start_at"],
        end_at=event_info["end_at"],
    )

    rental.price_per_hour = price_per_hour
    rental.total_amount = total_amount
    rental.pix_key = normalized_pix_key
    rental.pix_qr_code_payload = pix_qr_code_payload
    rental.payment_status = "pending"
    rental.status = "awaiting_payment"
    rental.confirmed_at = None
    if data.notes is not None:
        rental.notes = _normalize_notes(data.notes)
        db.execute(
            text("UPDATE public.events SET notes = :notes WHERE id = :event_id"),
            {"notes": rental.notes, "event_id": rental.event_id},
        )

    db.commit()
    db.refresh(rental)

    email_sent = _send_court_rental_email(
        to_email=rental.customer_email,
        recipient_name=rental.customer_name,
        action="payment_pending",
        start_at=event_info["start_at"],
        end_at=event_info["end_at"],
        court_name=str(event_info["court_name"]),
        total_amount=rental.total_amount,
        pix_key=rental.pix_key,
        pix_qr_code_payload=rental.pix_qr_code_payload,
    )
    _mark_confirmation_email_if_sent(db, rental, email_sent)

    message = "Cobrança Pix definida com sucesso para a locação."
    if email_sent:
        message = (
            f"{message} Enviamos também um e-mail com as instruções de pagamento para o cliente."
        )

    return CourtRentalAdminPaymentDefinitionOut(
        rental_id=rental.id,
        status=rental.status,
        payment_status=rental.payment_status,
        price_per_hour=rental.price_per_hour,
        total_amount=rental.total_amount,
        pix_key=rental.pix_key,
        pix_qr_code_payload=rental.pix_qr_code_payload,
        message=message,
        email_sent=email_sent,
    )


@router.post("/admin/bookings", response_model=CourtRentalOut, status_code=status.HTTP_201_CREATED)
def admin_create_court_rental(
    data: CourtRentalAdminCreateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    admin_user = _require_admin(db, user_id)

    if data.end_at <= data.start_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_TIME_RANGE",
                "message": "end_at precisa ser maior que start_at.",
            },
        )

    _validate_court_rental_slot_duration(data.start_at, data.end_at)
    _validate_court_rental_date_window(data.start_at.astimezone(_local_tz()).date())
    _validate_court_rental_not_in_past(data.start_at)
    _ensure_slot_available_or_409(
        db, court_id=data.court_id, start_at=data.start_at, end_at=data.end_at
    )

    customer = _load_customer_identity(
        db,
        customer_user_id=data.customer_user_id,
        customer_student_id=data.customer_student_id,
        customer_name=data.customer_name,
        customer_email=data.customer_email,
        customer_whatsapp=data.customer_whatsapp,
    )
    status_value, payment_status_value, confirmed_at_value = (
        _resolve_payment_state_for_admin_create(data)
    )

    try:
        event_row = _create_event(
            db,
            court_id=data.court_id,
            student_id=customer["customer_student_id"],
            created_by=UUID(str(admin_user["id"])),
            start_at=data.start_at,
            end_at=data.end_at,
            notes=_normalize_notes(data.notes) or "Locação criada pelo painel administrativo.",
        )
        rental = CourtRental(
            user_id=customer["user_id"],
            created_by_user_id=UUID(str(admin_user["id"])),
            customer_user_id=customer["customer_user_id"],
            customer_student_id=customer["customer_student_id"],
            event_id=event_row["id"],
            origin=data.origin,
            status=status_value,
            payment_status=payment_status_value,
            customer_name=customer["customer_name"],
            customer_email=customer["customer_email"],
            customer_whatsapp=customer["customer_whatsapp"],
            price_per_hour=data.price_per_hour,
            total_amount=data.total_amount,
            pix_key=_normalize_optional_text(data.pix_key),
            pix_qr_code_payload=_normalize_optional_text(data.pix_qr_code_payload),
            scheduled_at=data.start_at,
            confirmed_at=confirmed_at_value,
            notes=_normalize_notes(data.notes),
        )
        db.add(rental)
        db.commit()
        db.refresh(rental)
    except IntegrityError as e:
        db.rollback()
        raise _integrity_to_http(e) from e

    court_name = _get_court_name(db, data.court_id)
    email_action = "payment_pending" if rental.payment_status == "pending" else "scheduled"
    email_sent = _send_court_rental_email(
        to_email=rental.customer_email,
        recipient_name=rental.customer_name,
        action=email_action,
        start_at=data.start_at,
        end_at=data.end_at,
        court_name=court_name,
        total_amount=rental.total_amount,
        pix_key=rental.pix_key,
        pix_qr_code_payload=rental.pix_qr_code_payload,
    )
    _mark_confirmation_email_if_sent(db, rental, email_sent)

    return _serialize_rental(rental)


@router.patch("/admin/bookings/{rental_id}", response_model=CourtRentalOut)
def admin_update_court_rental(
    rental_id: UUID,
    data: CourtRentalAdminUpdateIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    _require_admin(db, user_id)
    rental = db.get(CourtRental, rental_id)
    if not rental:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locação não encontrada.")

    payload = data.model_dump(exclude_unset=True)

    if {
        "customer_user_id",
        "customer_student_id",
        "customer_name",
        "customer_email",
        "customer_whatsapp",
    } & set(payload.keys()):
        customer = _load_customer_identity(
            db,
            customer_user_id=payload.get("customer_user_id", rental.customer_user_id),
            customer_student_id=payload.get("customer_student_id", rental.customer_student_id),
            customer_name=payload.get("customer_name", rental.customer_name),
            customer_email=payload.get("customer_email", rental.customer_email),
            customer_whatsapp=payload.get("customer_whatsapp", rental.customer_whatsapp),
        )
        rental.user_id = customer["user_id"]
        rental.customer_user_id = customer["customer_user_id"]
        rental.customer_student_id = customer["customer_student_id"]
        rental.customer_name = customer["customer_name"]
        rental.customer_email = customer["customer_email"]
        rental.customer_whatsapp = customer["customer_whatsapp"]

    if "price_per_hour" in payload:
        rental.price_per_hour = payload["price_per_hour"]
    if "total_amount" in payload:
        rental.total_amount = payload["total_amount"]
    if "pix_key" in payload:
        rental.pix_key = _normalize_optional_text(payload["pix_key"])
    if "pix_qr_code_payload" in payload:
        rental.pix_qr_code_payload = _normalize_optional_text(payload["pix_qr_code_payload"])
    if "notes" in payload:
        rental.notes = _normalize_notes(payload["notes"])
        if rental.event_id is not None:
            db.execute(
                text("UPDATE public.events SET notes = :notes WHERE id = :event_id"),
                {"notes": rental.notes, "event_id": rental.event_id},
            )

    if "payment_status" in payload and payload["payment_status"] is not None:
        rental.payment_status = payload["payment_status"]

    if "status" in payload and payload["status"] is not None:
        new_status = payload["status"]
        if new_status in {"cancelled", "rejected"}:
            _cancel_event(db, rental.event_id)
            rental.cancelled_at = datetime.now(_local_tz())
        if new_status in {"confirmed", "scheduled"} and rental.confirmed_at is None:
            rental.confirmed_at = datetime.now(_local_tz())
        rental.status = new_status

    db.commit()
    db.refresh(rental)

    event_info = (
        db.execute(
            text("SELECT start_at, end_at, court_id FROM public.events WHERE id = :event_id"),
            {"event_id": rental.event_id},
        )
        .mappings()
        .first()
    )
    if event_info and rental.customer_email:
        court_name = _get_court_name(db, event_info["court_id"])
        email_action = "updated"
        if rental.status == "cancelled":
            email_action = "cancelled"
        email_sent = _send_court_rental_email(
            to_email=rental.customer_email,
            recipient_name=rental.customer_name,
            action=email_action,
            start_at=event_info["start_at"],
            end_at=event_info["end_at"],
            court_name=court_name,
            total_amount=rental.total_amount,
            pix_key=rental.pix_key,
            pix_qr_code_payload=rental.pix_qr_code_payload,
        )
        _mark_confirmation_email_if_sent(db, rental, email_sent)

    return _serialize_rental(rental)


@router.post(
    "/admin/bookings/{rental_id}/payment-review", response_model=CourtRentalPaymentReviewOut
)
def admin_review_court_rental_payment(
    rental_id: UUID,
    data: CourtRentalPaymentReviewIn,
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    admin_user = _require_admin(db, user_id)
    rental = db.get(CourtRental, rental_id)
    if not rental:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locação não encontrada.")

    event_info = _get_rental_event_snapshot_or_404(db, rental.event_id)

    received_amount = (
        _quantize_money(Decimal(str(data.payment_received_amount)))
        if data.payment_received_amount is not None
        else rental.payment_received_amount
    )

    rental.payment_status = data.payment_status
    rental.payment_received_amount = received_amount
    rental.payment_reviewed_at = datetime.now(_local_tz())
    rental.payment_reviewed_by_user_id = UUID(str(admin_user["id"]))
    rental.payment_review_notes = _normalize_notes(data.payment_review_notes)

    if data.payment_amount_matches_expected is not None:
        rental.payment_amount_matches_expected = data.payment_amount_matches_expected
    elif received_amount is not None and rental.total_amount is not None:
        rental.payment_amount_matches_expected = received_amount == rental.total_amount

    if data.payment_status == "approved":
        rental.status = "confirmed"
        if rental.confirmed_at is None:
            rental.confirmed_at = datetime.now(_local_tz())
        message = "Pagamento aprovado com sucesso e locação confirmada."
        email_action = "payment_approved"
    else:
        rental.status = "rejected"
        rental.cancelled_at = datetime.now(_local_tz())
        _cancel_event(db, rental.event_id)
        message = "Pagamento rejeitado e locação encerrada."
        email_action = "payment_rejected"

    db.commit()
    db.refresh(rental)

    email_sent = _send_court_rental_email(
        to_email=rental.customer_email,
        recipient_name=rental.customer_name,
        action=email_action,
        start_at=event_info["start_at"],
        end_at=event_info["end_at"],
        court_name=str(event_info["court_name"]),
        total_amount=rental.total_amount,
        pix_key=rental.pix_key,
        pix_qr_code_payload=rental.pix_qr_code_payload,
    )
    _mark_confirmation_email_if_sent(db, rental, email_sent)

    if email_sent:
        message = f"{message} Enviamos também um e-mail com o resultado da análise para o cliente."

    return CourtRentalPaymentReviewOut(
        rental_id=rental.id,
        status=rental.status,
        payment_status=rental.payment_status,
        payment_reviewed_at=rental.payment_reviewed_at,
        payment_amount_matches_expected=rental.payment_amount_matches_expected,
        payment_received_amount=rental.payment_received_amount,
        confirmed_at=rental.confirmed_at,
        message=message,
        email_sent=email_sent,
    )

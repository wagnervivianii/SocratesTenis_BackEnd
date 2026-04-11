from __future__ import annotations

import smtplib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import parseaddr
from html import escape
from typing import Protocol

from app.core.config import settings


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    mail_from: str
    use_tls: bool = True


@dataclass(frozen=True)
class InlineImage:
    cid: str
    data: bytes
    content_type: str = "image/png"
    filename: str | None = None


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    data: bytes
    content_type: str = "application/octet-stream"


class EmailSendError(RuntimeError):
    pass


class EmailSender(Protocol):
    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
        inline_images: Sequence[InlineImage] | None = None,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None: ...

    def send_verification_email(self, to_email: str, verify_link: str) -> None: ...

    def send_password_reset_email(self, to_email: str, reset_link: str) -> None: ...

    def send_student_signup_received_email(self, to_email: str, student_name: str) -> None: ...

    def send_student_signup_approved_email(
        self,
        to_email: str,
        student_name: str,
        login_link: str,
    ) -> None: ...

    def send_student_signup_rejected_email(
        self,
        to_email: str,
        student_name: str,
        contact_email: str | None = None,
    ) -> None: ...

    def send_student_makeup_request_received_email(
        self,
        *,
        to_email: str,
        student_name: str,
        original_class_group_name: str | None,
        original_start_at: datetime | None,
    ) -> None: ...

    def send_student_makeup_request_scheduled_email(
        self,
        *,
        to_email: str,
        student_name: str,
        original_class_group_name: str | None,
        original_start_at: datetime | None,
        replacement_class_group_name: str | None,
        replacement_start_at: datetime | None,
    ) -> None: ...

    def send_student_makeup_request_rejected_email(
        self,
        *,
        to_email: str,
        student_name: str,
        original_class_group_name: str | None,
        original_start_at: datetime | None,
    ) -> None: ...

    def send_student_makeup_request_cancelled_email(
        self,
        *,
        to_email: str,
        student_name: str,
        original_class_group_name: str | None,
        original_start_at: datetime | None,
    ) -> None: ...


class BaseEmailSender:
    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
        inline_images: Sequence[InlineImage] | None = None,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        raise NotImplementedError

    def send_verification_email(self, to_email: str, verify_link: str) -> None:
        subject = "Sócrates Tênis — Confirme seu e-mail"
        text_body = (
            "Olá!\n\n"
            "Para confirmar seu e-mail e ativar seu cadastro, clique no link abaixo:\n\n"
            f"{verify_link}\n\n"
            "Se você não solicitou este cadastro, ignore esta mensagem.\n\n"
            f"{_email_signature_text()}\n"
        )
        html_body = _build_brand_email_html(
            preheader="Confirme seu e-mail para ativar seu cadastro.",
            eyebrow="Confirmação de cadastro",
            title="Confirme seu e-mail",
            greeting="Olá!",
            intro_html="<p>Para ativar seu cadastro e liberar o acesso ao sistema, confirme seu e-mail pelo botão abaixo.</p>",
            cta_label="Confirmar e-mail",
            cta_url=verify_link,
            secondary_html="<p>Se você não solicitou este cadastro, pode ignorar esta mensagem.</p>",
        )
        self.send_email(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

    def send_password_reset_email(self, to_email: str, reset_link: str) -> None:
        subject = "Sócrates Tênis — Redefina sua senha"
        text_body = (
            "Olá!\n\n"
            "Recebemos uma solicitação para redefinir sua senha."
            " Clique no link abaixo para continuar:\n\n"
            f"{reset_link}\n\n"
            "Se você não solicitou a redefinição de senha, ignore este e-mail.\n"
            "Por segurança, o link expira automaticamente após um curto período.\n\n"
            f"{_email_signature_text()}\n"
        )
        html_body = _build_brand_email_html(
            preheader="Recebemos uma solicitação para redefinir sua senha.",
            eyebrow="Segurança da conta",
            title="Redefina sua senha",
            greeting="Olá!",
            intro_html=(
                "<p>Recebemos uma solicitação para redefinir sua senha.</p>"
                "<p>Use o botão abaixo para escolher uma nova senha com segurança.</p>"
            ),
            cta_label="Redefinir senha",
            cta_url=reset_link,
            secondary_html=(
                "<p>Se você não solicitou a redefinição de senha, ignore este e-mail.</p>"
                "<p>Por segurança, o link expira automaticamente após um curto período.</p>"
            ),
        )
        self.send_email(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

    def send_student_signup_received_email(self, to_email: str, student_name: str) -> None:
        safe_student_name = escape(student_name)
        subject = "Sócrates Tênis — Recebemos seu cadastro"
        text_body = (
            f"Olá, {student_name}!\n\n"
            "Recebemos sua solicitação de cadastro como aluno na Sócrates Tênis.\n\n"
            "Seu pedido passará por uma conferência da equipe antes da liberação. "
            "Assim que houver uma decisão, você receberá um novo e-mail informando se poderá prosseguir com o acesso ao sistema.\n\n"
            "Por enquanto, não é necessário tentar fazer login.\n\n"
            f"{_email_signature_text()}\n"
        )
        html_body = _build_brand_email_html(
            preheader="Recebemos sua solicitação de cadastro como aluno.",
            eyebrow="Cadastro recebido",
            title="Recebemos sua solicitação",
            greeting=f"Olá, <strong>{safe_student_name}</strong>!",
            intro_html=(
                "<p>Recebemos sua solicitação de cadastro como aluno na Sócrates Tênis.</p>"
                "<p>Seu pedido passará por uma conferência da equipe antes da liberação. Assim que houver uma decisão, você receberá um novo e-mail com a próxima orientação.</p>"
            ),
            secondary_html="<p>Por enquanto, não é necessário tentar fazer login.</p>",
        )
        self.send_email(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

    def send_student_signup_approved_email(
        self,
        to_email: str,
        student_name: str,
        login_link: str,
    ) -> None:
        safe_student_name = escape(student_name)
        subject = "Sócrates Tênis — Cadastro aprovado"
        text_body = (
            f"Olá, {student_name}!\n\n"
            "Seu cadastro foi aprovado pela equipe da Sócrates Tênis.\n\n"
            "Agora você já pode acessar o sistema pelo link abaixo:\n\n"
            f"{login_link}\n\n"
            "No primeiro acesso, o sistema poderá solicitar a criação da sua senha antes de liberar sua área de aluno.\n\n"
            f"{_email_signature_text()}\n"
        )
        html_body = _build_brand_email_html(
            preheader="Seu cadastro foi aprovado pela equipe da Sócrates Tênis.",
            eyebrow="Cadastro aprovado",
            title="Seu acesso foi liberado",
            greeting=f"Olá, <strong>{safe_student_name}</strong>!",
            intro_html=(
                "<p>Seu cadastro foi aprovado pela equipe da Sócrates Tênis.</p>"
                "<p>Agora você já pode acessar o sistema pelo botão abaixo.</p>"
            ),
            cta_label="Acessar sistema",
            cta_url=login_link,
            secondary_html=(
                "<p>No primeiro acesso, o sistema poderá solicitar a criação da sua senha antes de liberar sua área de aluno.</p>"
            ),
        )
        self.send_email(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

    def send_student_signup_rejected_email(
        self,
        to_email: str,
        student_name: str,
        contact_email: str | None = None,
    ) -> None:
        safe_student_name = escape(student_name)
        safe_contact_email = escape(contact_email) if contact_email else None
        contact_line = (
            f"Em caso de dúvida, entre em contato com a escola pelo e-mail {contact_email}.\n"
            if contact_email
            else "Em caso de dúvida, entre em contato com a escola.\n"
        )
        subject = "Sócrates Tênis — Atualização do seu cadastro"
        text_body = (
            f"Olá, {student_name}!\n\n"
            "Neste momento, sua solicitação de cadastro não foi liberada pela equipe da Sócrates Tênis.\n\n"
            f"{contact_line}\n"
            f"{_email_signature_text()}\n"
        )
        contact_html = (
            f"<p>Em caso de dúvida, entre em contato com a escola pelo e-mail <strong>{safe_contact_email}</strong>.</p>"
            if safe_contact_email
            else "<p>Em caso de dúvida, entre em contato com a escola.</p>"
        )
        html_body = _build_brand_email_html(
            preheader="Sua solicitação de cadastro ainda não foi liberada.",
            eyebrow="Atualização do cadastro",
            title="Status da sua solicitação",
            greeting=f"Olá, <strong>{safe_student_name}</strong>!",
            intro_html=(
                "<p>Neste momento, sua solicitação de cadastro não foi liberada pela equipe da Sócrates Tênis.</p>"
            ),
            secondary_html=contact_html,
        )
        self.send_email(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

    def send_student_makeup_request_received_email(
        self,
        *,
        to_email: str,
        student_name: str,
        original_class_group_name: str | None,
        original_start_at: datetime | None,
    ) -> None:
        class_group_name = original_class_group_name or "Turma não informada"
        lesson_datetime = _format_email_datetime(original_start_at)
        safe_student_name = escape(student_name)
        safe_class_group_name = escape(class_group_name)
        safe_lesson_datetime = escape(lesson_datetime)
        subject = "Sócrates Tênis — Recebemos seu pedido de reposição"
        text_body = (
            f"Olá, {student_name}!\n\n"
            "Recebemos seu pedido de reposição.\n\n"
            f"Aula original: {class_group_name}\n"
            f"Data e horário: {lesson_datetime}\n\n"
            "Nossa equipe vai analisar a disponibilidade e retornará com a decisão.\n\n"
            f"{_email_signature_text()}\n"
        )
        html_body = _build_brand_email_html(
            preheader="Recebemos seu pedido de reposição.",
            eyebrow="Reposição registrada",
            title="Pedido recebido",
            greeting=f"Olá, <strong>{safe_student_name}</strong>!",
            intro_html="<p>Recebemos seu pedido de reposição e ele já está em análise pela equipe.</p>",
            info_rows=[
                ("Aula original", safe_class_group_name),
                ("Data e horário", safe_lesson_datetime),
            ],
            secondary_html="<p>Nossa equipe vai analisar a disponibilidade e retornará com a decisão.</p>",
        )
        self.send_email(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

    def send_student_makeup_request_scheduled_email(
        self,
        *,
        to_email: str,
        student_name: str,
        original_class_group_name: str | None,
        original_start_at: datetime | None,
        replacement_class_group_name: str | None,
        replacement_start_at: datetime | None,
    ) -> None:
        original_class = original_class_group_name or "Turma não informada"
        original_datetime = _format_email_datetime(original_start_at)
        replacement_class = replacement_class_group_name or "Turma não informada"
        replacement_datetime = _format_email_datetime(replacement_start_at)
        safe_student_name = escape(student_name)
        subject = "Sócrates Tênis — Sua reposição foi agendada"
        text_body = (
            f"Olá, {student_name}!\n\n"
            "Seu pedido de reposição foi aprovado e agendado.\n\n"
            f"Aula original: {original_class}\n"
            f"Data original: {original_datetime}\n\n"
            f"Reposição: {replacement_class}\n"
            f"Nova data e horário: {replacement_datetime}\n\n"
            f"{_email_signature_text()}\n"
        )
        html_body = _build_brand_email_html(
            preheader="Seu pedido de reposição foi aprovado e agendado.",
            eyebrow="Reposição confirmada",
            title="Sua reposição foi agendada",
            greeting=f"Olá, <strong>{safe_student_name}</strong>!",
            intro_html="<p>Seu pedido de reposição foi aprovado e a nova aula já está definida.</p>",
            info_rows=[
                ("Aula original", escape(original_class)),
                ("Data original", escape(original_datetime)),
                ("Reposição", escape(replacement_class)),
                ("Nova data e horário", escape(replacement_datetime)),
            ],
        )
        self.send_email(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

    def send_student_makeup_request_rejected_email(
        self,
        *,
        to_email: str,
        student_name: str,
        original_class_group_name: str | None,
        original_start_at: datetime | None,
    ) -> None:
        class_group_name = original_class_group_name or "Turma não informada"
        lesson_datetime = _format_email_datetime(original_start_at)
        safe_student_name = escape(student_name)
        subject = "Sócrates Tênis — Seu pedido de reposição foi rejeitado"
        text_body = (
            f"Olá, {student_name}!\n\n"
            "Seu pedido de reposição não pôde ser atendido neste momento.\n\n"
            f"Aula original: {class_group_name}\n"
            f"Data e horário: {lesson_datetime}\n\n"
            f"{_email_signature_text()}\n"
        )
        html_body = _build_brand_email_html(
            preheader="Seu pedido de reposição não pôde ser atendido neste momento.",
            eyebrow="Reposição não aprovada",
            title="Não foi possível aprovar a reposição",
            greeting=f"Olá, <strong>{safe_student_name}</strong>!",
            intro_html="<p>Neste momento, não foi possível atender ao seu pedido de reposição.</p>",
            info_rows=[
                ("Aula original", escape(class_group_name)),
                ("Data e horário", escape(lesson_datetime)),
            ],
            secondary_html="<p>Se precisar, entre em contato com a equipe da escola para verificar novas possibilidades.</p>",
        )
        self.send_email(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

    def send_student_makeup_request_cancelled_email(
        self,
        *,
        to_email: str,
        student_name: str,
        original_class_group_name: str | None,
        original_start_at: datetime | None,
    ) -> None:
        class_group_name = original_class_group_name or "Turma não informada"
        lesson_datetime = _format_email_datetime(original_start_at)
        safe_student_name = escape(student_name)
        subject = "Sócrates Tênis — Seu pedido de reposição foi cancelado"
        text_body = (
            f"Olá, {student_name}!\n\n"
            "Seu pedido de reposição foi cancelado.\n\n"
            f"Aula original: {class_group_name}\n"
            f"Data e horário: {lesson_datetime}\n\n"
            f"{_email_signature_text()}\n"
        )
        html_body = _build_brand_email_html(
            preheader="Seu pedido de reposição foi cancelado.",
            eyebrow="Reposição cancelada",
            title="Pedido cancelado",
            greeting=f"Olá, <strong>{safe_student_name}</strong>!",
            intro_html="<p>Seu pedido de reposição foi cancelado.</p>",
            info_rows=[
                ("Aula original", escape(class_group_name)),
                ("Data e horário", escape(lesson_datetime)),
            ],
        )
        self.send_email(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )


class ConsoleEmailSender(BaseEmailSender):
    """Dev / custo zero: só loga a mensagem."""

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
        inline_images: Sequence[InlineImage] | None = None,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        print("[EMAIL][DEV]")
        print(f"to={to_email}")
        print(f"subject={subject}")
        print(text_body)
        if html_body:
            print("[EMAIL][DEV][HTML]")
            print(html_body)
        if inline_images:
            print("[EMAIL][DEV][INLINE_IMAGES]")
            for image in inline_images:
                print(f"cid={image.cid} content_type={image.content_type} bytes={len(image.data)}")
        if attachments:
            print("[EMAIL][DEV][ATTACHMENTS]")
            for attachment in attachments:
                print(
                    f"filename={attachment.filename} content_type={attachment.content_type} bytes={len(attachment.data)}"
                )


class SmtpEmailSender(BaseEmailSender):
    def __init__(self, cfg: SmtpConfig) -> None:
        self.cfg = cfg

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
        inline_images: Sequence[InlineImage] | None = None,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.cfg.mail_from
        msg["To"] = to_email

        msg.set_content(text_body)
        html_part: EmailMessage | None = None
        if html_body:
            msg.add_alternative(html_body, subtype="html")
            html_part = msg.get_payload()[-1]

        if html_part and inline_images:
            for image in inline_images:
                maintype, subtype = _split_content_type(image.content_type)
                html_part.add_related(
                    image.data,
                    maintype=maintype,
                    subtype=subtype,
                    cid=f"<{image.cid}>",
                    filename=image.filename or f"{image.cid}.{subtype}",
                    disposition="inline",
                )

        if attachments:
            for attachment in attachments:
                maintype, subtype = _split_content_type(attachment.content_type)
                msg.add_attachment(
                    attachment.data,
                    maintype=maintype,
                    subtype=subtype,
                    filename=attachment.filename,
                )

        try:
            if self.cfg.use_tls:
                with smtplib.SMTP(self.cfg.host, self.cfg.port, timeout=20) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.ehlo()
                    smtp.login(self.cfg.username, self.cfg.password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP_SSL(self.cfg.host, self.cfg.port, timeout=20) as smtp:
                    smtp.login(self.cfg.username, self.cfg.password)
                    smtp.send_message(msg)
        except Exception as e:
            raise EmailSendError(f"Falha ao enviar e-mail: {e}") from e


def _format_email_datetime(value: datetime | date | None) -> str:
    if value is None:
        return "Data e horário não informados"

    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y às %H:%M")

    return value.strftime("%d/%m/%Y")


def _extract_contact_email() -> str | None:
    _, parsed_email = parseaddr(settings.smtp_from or "")
    if parsed_email:
        return parsed_email

    username = (settings.smtp_username or "").strip()
    return username or None


def _brand_logo_url() -> str:
    base_url = (settings.frontend_url or "").rstrip("/")
    if not base_url:
        return ""

    return f"{base_url}/assets/logoGeral.png"


def _email_signature_text() -> str:
    lines = [
        "Abraço,",
        "Equipe Sócrates Tênis",
    ]
    contact_email = _extract_contact_email()
    if contact_email:
        lines.append(f"Contato: {contact_email}")

    frontend_url = (settings.frontend_url or "").strip()
    if frontend_url:
        lines.append(frontend_url)

    return "\n".join(lines)


def _build_brand_email_html(
    *,
    preheader: str,
    eyebrow: str,
    title: str,
    greeting: str,
    intro_html: str,
    cta_label: str | None = None,
    cta_url: str | None = None,
    info_rows: Sequence[tuple[str, str]] | None = None,
    secondary_html: str | None = None,
) -> str:
    logo_url = escape(_brand_logo_url())
    safe_preheader = escape(preheader)
    safe_eyebrow = escape(eyebrow)
    safe_title = escape(title)
    safe_contact_email = escape(_extract_contact_email() or "")
    safe_frontend_url = escape((settings.frontend_url or "").strip())

    button_html = ""
    if cta_label and cta_url:
        button_html = (
            '<div style="margin:28px 0 0">'
            f'<a href="{escape(cta_url)}" '
            'style="display:inline-block;border-radius:999px;background:#3c1498;padding:14px 24px;color:#ffffff;text-decoration:none;font-size:14px;font-weight:700;">'
            f"{escape(cta_label)}</a></div>"
        )

    info_table_html = ""
    if info_rows:
        rendered_rows = "".join(
            (
                "<tr>"
                f'<td style="padding:12px 0 6px;color:#64748b;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;vertical-align:top;">{escape(label)}</td>'
                "</tr>"
                "<tr>"
                f'<td style="padding:0 0 14px;color:#0f172a;font-size:15px;line-height:1.6;vertical-align:top;">{value}</td>'
                "</tr>"
            )
            for label, value in info_rows
        )
        info_table_html = (
            '<div style="margin:28px 0;border:1px solid #dbe7f5;border-radius:20px;background:#f8fbff;padding:20px 22px;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
            f"{rendered_rows}"
            "</table>"
            "</div>"
        )

    contact_html = (
        f'<a href="mailto:{safe_contact_email}" style="color:#3c1498;text-decoration:none;">{safe_contact_email}</a>'
        if safe_contact_email
        else ""
    )
    website_html = (
        f'<a href="{safe_frontend_url}" style="color:#3c1498;text-decoration:none;">{safe_frontend_url}</a>'
        if safe_frontend_url
        else ""
    )

    footer_parts = [
        '<p style="margin:0 0 6px;font-size:14px;font-weight:700;color:#0f172a;">Equipe Sócrates Tênis</p>'
    ]
    if contact_html:
        footer_parts.append(
            f'<p style="margin:0 0 4px;font-size:13px;color:#475569;">Contato: {contact_html}</p>'
        )
    if website_html:
        footer_parts.append(f'<p style="margin:0;font-size:13px;color:#475569;">{website_html}</p>')

    logo_block = (
        f'<img src="{logo_url}" alt="Sócrates Tênis" style="display:block;max-width:150px;width:100%;height:auto;border:0;">'
        if logo_url
        else '<div style="font-size:24px;font-weight:800;color:#ffffff;letter-spacing:0.06em;">Sócrates Tênis</div>'
    )

    secondary_section = secondary_html or ""

    return f"""
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_title}</title>
  </head>
  <body style="margin:0;padding:0;background:#eef3f9;font-family:Arial,sans-serif;color:#0f172a;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{safe_preheader}</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef3f9;">
      <tr>
        <td align="center" style="padding:32px 16px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;">
            <tr>
              <td style="border-radius:28px;background:linear-gradient(135deg,#0b1f2a 0%,#0d3550 58%,#3c1498 100%);padding:28px 28px 22px;">
                {logo_block}
                <p style="margin:24px 0 0;font-size:11px;font-weight:700;letter-spacing:0.24em;text-transform:uppercase;color:#86efac;">{safe_eyebrow}</p>
                <h1 style="margin:10px 0 0;font-size:30px;line-height:1.2;color:#ffffff;">{safe_title}</h1>
              </td>
            </tr>
            <tr>
              <td style="padding-top:18px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-radius:28px;background:#ffffff;border:1px solid #d8e2ee;overflow:hidden;box-shadow:0 18px 42px rgba(15,23,42,0.08);">
                  <tr>
                    <td style="padding:32px 30px 12px;font-size:16px;line-height:1.7;color:#0f172a;">{greeting}</td>
                  </tr>
                  <tr>
                    <td style="padding:0 30px 8px;font-size:15px;line-height:1.8;color:#334155;">{intro_html}</td>
                  </tr>
                  <tr>
                    <td style="padding:0 30px;">{button_html}{info_table_html}</td>
                  </tr>
                  <tr>
                    <td style="padding:0 30px 30px;font-size:14px;line-height:1.8;color:#475569;">{secondary_section}</td>
                  </tr>
                  <tr>
                    <td style="border-top:1px solid #e2e8f0;padding:24px 30px 28px;background:#f8fbff;">{"".join(footer_parts)}</td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""".strip()


def _split_content_type(content_type: str) -> tuple[str, str]:
    normalized = content_type.strip().lower()
    if "/" not in normalized:
        return "application", "octet-stream"

    maintype, subtype = normalized.split("/", 1)
    if not maintype or not subtype:
        return "application", "octet-stream"

    return maintype, subtype

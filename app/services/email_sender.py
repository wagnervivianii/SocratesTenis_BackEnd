from __future__ import annotations

import smtplib
from collections.abc import Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol


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
            "Se você não solicitou este cadastro, ignore esta mensagem.\n"
        )
        html_body = f"""
        <div style=\"font-family:Arial,sans-serif;line-height:1.4\">
          <h2>Sócrates Tênis</h2>
          <p>Para confirmar seu e-mail e ativar seu cadastro, clique no botão abaixo:</p>
          <p>
            <a href=\"{verify_link}\"
               style=\"display:inline-block;padding:10px 14px;background:#0b5fff;color:#fff;text-decoration:none;border-radius:8px\">
              Confirmar e-mail
            </a>
          </p>
          <p style=\"font-size:12px;color:#666\">Se você não solicitou este cadastro, ignore esta mensagem.</p>
        </div>
        """
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
            "Recebemos uma solicitação para redefinir sua senha. "
            "Clique no link abaixo para continuar:\n\n"
            f"{reset_link}\n\n"
            "Se você não solicitou a redefinição de senha, ignore este e-mail.\n"
            "Por segurança, o link expira automaticamente após um curto período.\n"
        )
        html_body = f"""
        <div style=\"font-family:Arial,sans-serif;line-height:1.4\">
          <h2>Sócrates Tênis</h2>
          <p>Recebemos uma solicitação para redefinir sua senha.</p>
          <p>Clique no botão abaixo para escolher uma nova senha:</p>
          <p>
            <a href=\"{reset_link}\"
               style=\"display:inline-block;padding:10px 14px;background:#0b5fff;color:#fff;text-decoration:none;border-radius:8px\">
              Redefinir senha
            </a>
          </p>
          <p style=\"font-size:12px;color:#666\">
            Se você não solicitou a redefinição de senha, ignore este e-mail.
            Por segurança, o link expira automaticamente após um curto período.
          </p>
        </div>
        """
        self.send_email(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

    def send_student_signup_received_email(self, to_email: str, student_name: str) -> None:
        subject = "Sócrates Tênis — Recebemos seu cadastro"
        text_body = (
            f"Olá, {student_name}!\n\n"
            "Recebemos sua solicitação de cadastro como aluno na Sócrates Tênis.\n\n"
            "Seu pedido passará por uma conferência da equipe antes da liberação. "
            "Assim que houver uma decisão, você receberá um novo e-mail informando se poderá prosseguir com o acesso ao sistema.\n\n"
            "Por enquanto, não é necessário tentar fazer login.\n"
        )
        html_body = f"""
        <div style=\"font-family:Arial,sans-serif;line-height:1.5;color:#0f172a\">
          <h2 style=\"margin:0 0 12px;color:#0b5fff\">Sócrates Tênis</h2>
          <p>Olá, <strong>{student_name}</strong>!</p>
          <p>Recebemos sua solicitação de cadastro como aluno.</p>
          <p>
            Seu pedido passará por uma conferência da equipe antes da liberação.
            Assim que houver uma decisão, você receberá um novo e-mail informando
            se poderá prosseguir com o acesso ao sistema.
          </p>
          <p style=\"font-size:12px;color:#475569\">Por enquanto, não é necessário tentar fazer login.</p>
        </div>
        """
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
        subject = "Sócrates Tênis — Cadastro aprovado"
        text_body = (
            f"Olá, {student_name}!\n\n"
            "Seu cadastro foi aprovado pela equipe da Sócrates Tênis.\n\n"
            "Agora você já pode acessar o sistema pelo link abaixo:\n\n"
            f"{login_link}\n\n"
            "No primeiro acesso, o sistema poderá solicitar a criação da sua senha antes de liberar sua área de aluno.\n"
        )
        html_body = f"""
        <div style=\"font-family:Arial,sans-serif;line-height:1.5;color:#0f172a\">
          <h2 style=\"margin:0 0 12px;color:#0b5fff\">Sócrates Tênis</h2>
          <p>Olá, <strong>{student_name}</strong>!</p>
          <p>Seu cadastro foi aprovado pela equipe da Sócrates Tênis.</p>
          <p>Agora você já pode acessar o sistema pelo botão abaixo:</p>
          <p>
            <a href=\"{login_link}\"
               style=\"display:inline-block;padding:10px 14px;background:#0b5fff;color:#fff;text-decoration:none;border-radius:8px\">
              Acessar sistema
            </a>
          </p>
          <p style=\"font-size:12px;color:#475569\">
            No primeiro acesso, o sistema poderá solicitar a criação da sua senha antes de liberar sua área de aluno.
          </p>
        </div>
        """
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
        subject = "Sócrates Tênis — Atualização do seu cadastro"
        contact_line = (
            f"Em caso de dúvida, entre em contato com a escola pelo e-mail {contact_email}.\n"
            if contact_email
            else "Em caso de dúvida, entre em contato com a escola.\n"
        )
        text_body = (
            f"Olá, {student_name}!\n\n"
            "Neste momento, sua solicitação de cadastro não foi liberada pela equipe da Sócrates Tênis.\n\n"
            f"{contact_line}"
        )
        contact_html = (
            f'<p style="font-size:12px;color:#475569">Em caso de dúvida, entre em contato com a escola pelo e-mail <strong>{contact_email}</strong>.</p>'
            if contact_email
            else '<p style="font-size:12px;color:#475569">Em caso de dúvida, entre em contato com a escola.</p>'
        )
        html_body = f"""
        <div style=\"font-family:Arial,sans-serif;line-height:1.5;color:#0f172a\">
          <h2 style=\"margin:0 0 12px;color:#0b5fff\">Sócrates Tênis</h2>
          <p>Olá, <strong>{student_name}</strong>!</p>
          <p>Neste momento, sua solicitação de cadastro não foi liberada pela equipe da Sócrates Tênis.</p>
          {contact_html}
        </div>
        """
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


def _split_content_type(content_type: str) -> tuple[str, str]:
    normalized = content_type.strip().lower()
    if "/" not in normalized:
        return "application", "octet-stream"

    maintype, subtype = normalized.split("/", 1)
    if not maintype or not subtype:
        return "application", "octet-stream"

    return maintype, subtype

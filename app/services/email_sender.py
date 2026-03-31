from __future__ import annotations

import smtplib
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
    ) -> None: ...

    def send_verification_email(self, to_email: str, verify_link: str) -> None: ...

    def send_password_reset_email(self, to_email: str, reset_link: str) -> None: ...


class BaseEmailSender:
    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
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


class ConsoleEmailSender(BaseEmailSender):
    """Dev / custo zero: só loga a mensagem."""

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> None:
        print("[EMAIL][DEV]")
        print(f"to={to_email}")
        print(f"subject={subject}")
        print(text_body)
        if html_body:
            print("[EMAIL][DEV][HTML]")
            print(html_body)


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
    ) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.cfg.mail_from
        msg["To"] = to_email

        msg.set_content(text_body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")

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

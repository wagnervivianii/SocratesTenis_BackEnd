# app/services/email_sender.py
from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage


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


class EmailSender:
    def send_verification_email(self, to_email: str, verify_link: str) -> None:
        raise NotImplementedError


class ConsoleEmailSender(EmailSender):
    """Dev / custo zero: só loga o link."""

    def send_verification_email(self, to_email: str, verify_link: str) -> None:
        print(f"[EMAIL][DEV] to={to_email} verify_link={verify_link}")


class SmtpEmailSender(EmailSender):
    def __init__(self, cfg: SmtpConfig) -> None:
        self.cfg = cfg

    def send_verification_email(self, to_email: str, verify_link: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = "Sócrates Tênis — Confirme seu e-mail"
        msg["From"] = self.cfg.mail_from
        msg["To"] = to_email

        text_body = (
            "Olá!\n\n"
            "Para confirmar seu e-mail e ativar seu cadastro, clique no link abaixo:\n\n"
            f"{verify_link}\n\n"
            "Se você não solicitou este cadastro, ignore esta mensagem.\n"
        )

        html_body = f"""
        <div style="font-family:Arial,sans-serif;line-height:1.4">
          <h2>Sócrates Tênis</h2>
          <p>Para confirmar seu e-mail e ativar seu cadastro, clique no botão abaixo:</p>
          <p>
            <a href="{verify_link}"
               style="display:inline-block;padding:10px 14px;background:#0b5fff;color:#fff;text-decoration:none;border-radius:8px">
              Confirmar e-mail
            </a>
          </p>
          <p style="font-size:12px;color:#666">Se você não solicitou este cadastro, ignore esta mensagem.</p>
        </div>
        """

        msg.set_content(text_body)
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

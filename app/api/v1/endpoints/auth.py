from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_password_hash,
    safe_get_subject,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.schemas.auth import (
    CompleteGoogleProfileIn,
    CompleteGoogleProfileOut,
    FirstAccessSetPasswordIn,
    ForgotPasswordRequestIn,
    GoogleAuthCallbackIn,
    GoogleAuthExchangeOut,
    GoogleAuthStartOut,
    LoginIn,
    MeOut,
    MessageOut,
    ResetPasswordIn,
    TokenOut,
)
from app.services.email_sender import (
    ConsoleEmailSender,
    EmailSendError,
    SmtpConfig,
    SmtpEmailSender,
)
from app.services.email_verification import (
    EmailVerificationExpired,
    EmailVerificationInvalid,
    EmailVerificationService,
)
from app.services.google_auth import GoogleAuthError, GoogleAuthService
from app.services.google_oauth import (
    GoogleOAuthConfigError,
    GoogleOAuthExchangeError,
    GoogleOAuthService,
    GoogleOAuthStateError,
)
from app.services.password_reset import (
    PasswordResetExpired,
    PasswordResetInvalid,
    PasswordResetService,
)

router = APIRouter(prefix="/auth")
DBSession = Annotated[Session, Depends(get_db)]


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
    )


def _only_digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def _normalize_instagram(s: str | None) -> str | None:
    if not s:
        return None
    v = s.strip()
    if not v:
        return None
    while v.startswith("@"):
        v = v[1:]
    v = v.strip()
    return v or None


def _normalize_guardian_relationship(s: str | None) -> str | None:
    if not s:
        return None
    v = s.strip()
    return v or None


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


def _raise_register_conflict(code: str, message: str) -> None:
    raise HTTPException(
        status_code=409,
        detail={
            "code": code,
            "message": message,
        },
    )


def _build_password_reset_link(token: str) -> str:
    reset_path = getattr(settings, "frontend_password_reset_path", "/reset-password")
    return f"{settings.frontend_url}{reset_path}?token={token}"


def _get_google_identity(db: Session, user_id: UUID) -> UserIdentity | None:
    return db.scalar(
        select(UserIdentity).where(
            UserIdentity.user_id == user_id,
            UserIdentity.provider == "google",
        )
    )


def _calculate_age(birth_date: date) -> int:
    today = datetime.now(UTC).date()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def _validate_birth_date(birth_date: date) -> None:
    today = datetime.now(UTC).date()
    if birth_date > today:
        raise HTTPException(status_code=400, detail="Data de nascimento inválida")


def _validate_zip_code(zip_code: str) -> str:
    digits = _only_digits(zip_code)
    if len(digits) != 8:
        raise HTTPException(status_code=400, detail="CEP inválido")
    return digits


def _validate_whatsapp(whatsapp: str, *, field_label: str = "WhatsApp") -> str:
    digits = _only_digits(whatsapp)
    if len(digits) not in (10, 11):
        raise HTTPException(status_code=400, detail=f"{field_label} inválido")
    return digits


def _normalize_name(name: str, *, field_label: str = "Nome") -> str:
    value = name.strip()
    if len(value) < 3:
        raise HTTPException(status_code=400, detail=f"{field_label} inválido")
    return value


def _is_minor(birth_date: date) -> bool:
    return _calculate_age(birth_date) < 18


def _is_student_like_role(role: str | None) -> bool:
    value = (role or "").strip().lower()
    return value in {"student", "aluno"}


def _apply_guardian_fields(
    *,
    user: User,
    birth_date: date,
    guardian_full_name: str | None,
    guardian_whatsapp: str | None,
    guardian_relationship: str | None,
) -> None:
    if _is_minor(birth_date):
        normalized_guardian_name = _normalize_name(
            guardian_full_name or "",
            field_label="Nome do responsável",
        )
        normalized_guardian_whatsapp = _validate_whatsapp(
            guardian_whatsapp or "",
            field_label="Telefone do responsável",
        )
        normalized_guardian_relationship = _normalize_guardian_relationship(guardian_relationship)

        if not normalized_guardian_relationship:
            raise HTTPException(status_code=400, detail="Parentesco do responsável é obrigatório")

        user.guardian_full_name = normalized_guardian_name
        user.guardian_whatsapp = normalized_guardian_whatsapp
        user.guardian_relationship = normalized_guardian_relationship
        return

    user.guardian_full_name = None
    user.guardian_whatsapp = None
    user.guardian_relationship = None


def _is_profile_completed(user: User) -> bool:
    if not user.whatsapp:
        return False
    if not user.birth_date:
        return False
    if not user.zip_code:
        return False

    if _is_minor(user.birth_date):
        return bool(
            user.guardian_full_name and user.guardian_whatsapp and user.guardian_relationship
        )

    return True


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    whatsapp: str = Field(min_length=10, max_length=20)
    instagram: str | None = Field(default=None, max_length=60)
    birth_date: date
    zip_code: str = Field(min_length=8, max_length=10)
    guardian_full_name: str | None = Field(default=None, max_length=120)
    guardian_whatsapp: str | None = Field(default=None, max_length=20)
    guardian_relationship: str | None = Field(default=None, max_length=80)
    intent: str = Field(pattern="^(lesson|rental|student)$")


class RegisterOut(BaseModel):
    user_id: str
    created: bool
    intent_added: bool
    intent: str
    email: EmailStr


class ResendVerificationIn(BaseModel):
    email: EmailStr


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, response: Response, db: DBSession):
    user = db.scalar(select(User).where(User.email == str(data.email)))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos",
        )

    if not user.password_hash:
        google_identity = _get_google_identity(db, user.id)
        if google_identity is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "GOOGLE_ACCOUNT_WITHOUT_PASSWORD",
                    "message": (
                        "Esta conta foi criada com Google e ainda não possui senha. "
                        "Entre com Google para concluir o cadastro e definir sua senha."
                    ),
                },
            )

        if _is_student_like_role(user.role):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "FIRST_ACCESS_PASSWORD_SETUP_REQUIRED",
                    "message": (
                        "Sua conta foi aprovada. Defina sua senha para concluir o primeiro acesso."
                    ),
                },
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "ACCOUNT_WITHOUT_PASSWORD",
                "message": (
                    "Esta conta ainda não possui uma senha cadastrada. "
                    "Use o método original de acesso ou conclua o cadastro antes de entrar."
                ),
            },
        )

    if not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuário inativo")

    access = create_access_token(subject=str(user.id))
    refresh = create_refresh_token(subject=str(user.id))
    _set_refresh_cookie(response, refresh)

    return TokenOut(access_token=access, expires_in=settings.access_token_expire_minutes * 60)


@router.get("/google/start", response_model=GoogleAuthStartOut)
def google_auth_start(
    request: Request,
    redirect_uri: Annotated[str, Query(min_length=1, max_length=2048)],
):
    service = GoogleOAuthService()

    try:
        result = service.build_authorization_url(
            redirect_uri=redirect_uri,
            origin=request.headers.get("origin"),
        )
    except GoogleOAuthConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return GoogleAuthStartOut(
        authorization_url=result.authorization_url,
        state=result.state,
    )


@router.post("/google/exchange", response_model=GoogleAuthExchangeOut)
def google_auth_exchange(data: GoogleAuthCallbackIn, response: Response, db: DBSession):
    oauth_service = GoogleOAuthService()
    auth_service = GoogleAuthService()

    try:
        oauth_service.parse_state(data.state, redirect_uri=data.redirect_uri)
        profile = oauth_service.exchange_code_for_profile(
            code=data.code,
            redirect_uri=data.redirect_uri,
        )
        result = auth_service.resolve_or_create_user(db, profile)
    except GoogleOAuthConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except GoogleOAuthStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except GoogleOAuthExchangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except GoogleAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if not result.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo",
        )

    access = create_access_token(subject=str(result.user.id))
    refresh = create_refresh_token(subject=str(result.user.id))
    _set_refresh_cookie(response, refresh)

    return GoogleAuthExchangeOut(
        access_token=access,
        expires_in=settings.access_token_expire_minutes * 60,
        avatar_url=result.avatar_url,
    )


@router.post("/google/complete-profile", response_model=CompleteGoogleProfileOut)
def complete_google_profile(
    data: CompleteGoogleProfileIn,
    user_id: str = Depends(get_current_user_id),
    db: DBSession = None,
):
    user = db.get(User, UUID(user_id))

    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    google_identity = _get_google_identity(db, user.id)
    if google_identity is None:
        raise HTTPException(
            status_code=400,
            detail="Este fluxo de complemento é exclusivo para contas com login Google",
        )

    birth_date = data.birth_date
    _validate_birth_date(birth_date)

    if not user.password_hash:
        raw_password = (data.password or "").strip()
        if len(raw_password) < 8:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Para concluir o primeiro acesso com Google, defina uma senha de pelo menos 8 caracteres"
                ),
            )
        user.password_hash = get_password_hash(raw_password)

    normalized_whatsapp = _validate_whatsapp(data.whatsapp)
    normalized_zip_code = _validate_zip_code(data.zip_code)
    normalized_instagram = _normalize_instagram(data.instagram)

    user.whatsapp = normalized_whatsapp
    user.instagram = normalized_instagram
    user.birth_date = birth_date
    user.zip_code = normalized_zip_code

    _apply_guardian_fields(
        user=user,
        birth_date=birth_date,
        guardian_full_name=data.guardian_full_name,
        guardian_whatsapp=data.guardian_whatsapp,
        guardian_relationship=data.guardian_relationship,
    )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Não foi possível salvar os dados complementares do perfil",
        ) from None

    db.refresh(user)

    return CompleteGoogleProfileOut(
        user_id=str(user.id),
        profile_completed=_is_profile_completed(user),
        message="Perfil complementar atualizado com sucesso",
    )


@router.post("/first-access/set-password", response_model=MessageOut)
def first_access_set_password(data: FirstAccessSetPasswordIn, db: DBSession):
    raw_email = str(data.email).strip().lower() if data.email else ""
    raw_token = (data.token or "").strip()

    if not raw_email and not raw_token:
        raise HTTPException(
            status_code=400,
            detail="Informe o e-mail da conta ou utilize o link enviado para o primeiro acesso.",
        )

    user: User | None = None
    svc = PasswordResetService(ttl_minutes=getattr(settings, "password_reset_ttl_minutes", 30))

    if raw_token:
        try:
            user_id = svc.validate_token(db, raw_token)
        except PasswordResetExpired:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "FIRST_ACCESS_TOKEN_EXPIRED",
                    "message": "O link de primeiro acesso expirou. Solicite um novo link à escola.",
                },
            ) from None
        except PasswordResetInvalid:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "FIRST_ACCESS_TOKEN_INVALID",
                    "message": "O link de primeiro acesso é inválido ou já foi utilizado.",
                },
            ) from None

        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Conta não encontrada")

        if raw_email and user.email != raw_email:
            raise HTTPException(
                status_code=400,
                detail="O link informado não corresponde ao e-mail desta conta.",
            )
    else:
        user = db.scalar(select(User).where(User.email == raw_email))

    if not user:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Sua conta ainda não está ativa. Aguarde a aprovação da escola.",
        )

    if user.password_hash:
        raise HTTPException(
            status_code=409,
            detail=(
                "Esta conta já possui senha cadastrada. Use o login normal ou redefina sua senha."
            ),
        )

    google_identity = _get_google_identity(db, user.id)
    if google_identity is not None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Esta conta utiliza o fluxo de Google. Entre com Google para concluir o cadastro e definir sua senha."
            ),
        )

    password_hash = get_password_hash(data.password)

    if raw_token:
        try:
            consumed_user_id = svc.consume_token(db, raw_token, password_hash=password_hash)
        except PasswordResetExpired:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "FIRST_ACCESS_TOKEN_EXPIRED",
                    "message": "O link de primeiro acesso expirou. Solicite um novo link à escola.",
                },
            ) from None
        except PasswordResetInvalid:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "FIRST_ACCESS_TOKEN_INVALID",
                    "message": "O link de primeiro acesso é inválido ou já foi utilizado.",
                },
            ) from None

        refreshed_user = db.get(User, consumed_user_id)
        if not refreshed_user:
            raise HTTPException(status_code=404, detail="Conta não encontrada")

        refreshed_user.email_verified_at = refreshed_user.email_verified_at or datetime.now(UTC)
        refreshed_user.updated_at = datetime.now(UTC)

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Não foi possível confirmar o e-mail e definir a senha do primeiro acesso.",
            ) from None
    else:
        user.password_hash = password_hash

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Não foi possível definir a senha do primeiro acesso",
            ) from None

    return MessageOut(
        message="Senha criada com sucesso. Agora você já pode entrar com seu e-mail e senha."
    )


@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, request: Request, db: DBSession):
    """
    Regras (UX forte):
    - Se WhatsApp já existe: informar especificamente que o WhatsApp já consta
    - Se Email já existe e está ativo/verificado: informar especificamente que o e-mail já consta
    - Se Email e WhatsApp já existem: informar ambos
    - Se Email existe mas NÃO verificou (e sem conflito de WhatsApp): reenvia e-mail de verificação
    - Se não existe: cria users (is_active=false) + envia verificação
    """
    input_email = str(data.email).strip().lower()
    whatsapp_digits = _validate_whatsapp(data.whatsapp)
    zip_code_digits = _validate_zip_code(data.zip_code)
    _validate_birth_date(data.birth_date)

    instagram = _normalize_instagram(data.instagram)
    full_name = _normalize_name(data.full_name)

    user_by_email = db.scalar(select(User).where(User.email == input_email))
    user_by_whatsapp = None
    if whatsapp_digits:
        user_by_whatsapp = db.scalar(select(User).where(User.whatsapp == whatsapp_digits))

    email_exists = user_by_email is not None
    whatsapp_exists = user_by_whatsapp is not None

    if email_exists and whatsapp_exists:
        same_user = user_by_email.id == user_by_whatsapp.id

        if same_user and (
            user_by_email.is_active is False or user_by_email.email_verified_at is None
        ):
            user = user_by_email
            created = False
        else:
            _raise_register_conflict(
                "EMAIL_AND_WHATSAPP_ALREADY_EXIST",
                "Este e-mail e este WhatsApp já constam no sistema. Faça login para continuar.",
            )

    elif whatsapp_exists:
        _raise_register_conflict(
            "WHATSAPP_ALREADY_EXISTS",
            "Já existe um cadastro com este WhatsApp.",
        )

    elif email_exists:
        if user_by_email.is_active and user_by_email.email_verified_at is not None:
            _raise_register_conflict(
                "EMAIL_ALREADY_EXISTS",
                "Este e-mail já está cadastrado. Faça login para continuar.",
            )

        user = user_by_email
        created = False

    else:
        user = User(
            email=input_email,
            password_hash=get_password_hash(data.password),
            full_name=full_name,
            role="staff",
            is_active=False,
            whatsapp=whatsapp_digits,
            instagram=instagram,
            birth_date=data.birth_date,
            zip_code=zip_code_digits,
        )
        _apply_guardian_fields(
            user=user,
            birth_date=data.birth_date,
            guardian_full_name=data.guardian_full_name,
            guardian_whatsapp=data.guardian_whatsapp,
            guardian_relationship=data.guardian_relationship,
        )
        db.add(user)

        try:
            db.commit()
        except Exception:
            db.rollback()

            retry_user_by_email = db.scalar(select(User).where(User.email == input_email))
            retry_user_by_whatsapp = None
            if whatsapp_digits:
                retry_user_by_whatsapp = db.scalar(
                    select(User).where(User.whatsapp == whatsapp_digits)
                )

            retry_email_exists = retry_user_by_email is not None
            retry_whatsapp_exists = retry_user_by_whatsapp is not None

            if retry_email_exists and retry_whatsapp_exists:
                _raise_register_conflict(
                    "EMAIL_AND_WHATSAPP_ALREADY_EXIST",
                    "Este e-mail e este WhatsApp já constam no sistema. Faça login para continuar.",
                )
            if retry_whatsapp_exists:
                _raise_register_conflict(
                    "WHATSAPP_ALREADY_EXISTS",
                    "Já existe um cadastro com este WhatsApp.",
                )
            if retry_email_exists:
                _raise_register_conflict(
                    "EMAIL_ALREADY_EXISTS",
                    "Este e-mail já está cadastrado. Faça login para continuar.",
                )

            raise HTTPException(status_code=409, detail="Usuário já cadastrado") from None

        db.refresh(user)
        created = True

    if not created:
        user.full_name = full_name
        user.whatsapp = whatsapp_digits
        user.instagram = instagram
        user.birth_date = data.birth_date
        user.zip_code = zip_code_digits
        _apply_guardian_fields(
            user=user,
            birth_date=data.birth_date,
            guardian_full_name=data.guardian_full_name,
            guardian_whatsapp=data.guardian_whatsapp,
            guardian_relationship=data.guardian_relationship,
        )
        db.commit()
        db.refresh(user)

    intent_added = False
    try:
        res = db.execute(
            text(
                """
                INSERT INTO user_intents (user_id, intent)
                VALUES (:user_id, :intent)
                ON CONFLICT (user_id, intent) DO NOTHING
                """
            ),
            {"user_id": str(user.id), "intent": data.intent},
        )
        db.commit()
        intent_added = bool(getattr(res, "rowcount", 0))
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Falha ao registrar intenção") from None

    svc = EmailVerificationService(ttl_minutes=settings.email_verify_ttl_minutes)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    issued = svc.issue_for_user(db, user.id, ip=ip, user_agent=ua)

    verify_link = f"{settings.public_api_url}/api/v1/auth/verify-email?token={issued.token}"

    sender = _get_email_sender()
    try:
        sender.send_verification_email(user.email, verify_link)
    except EmailSendError as e:
        print(f"[EMAIL][ERROR] to={user.email} user={user.id} err={e}")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível enviar o e-mail de verificação. Tente novamente em instantes.",
        ) from None

    print(
        f"[EMAIL-VERIFY] user={user.id} email={user.email} expires_at={issued.expires_at.isoformat()}"
    )

    return RegisterOut(
        user_id=str(user.id),
        created=created,
        intent_added=intent_added,
        intent=data.intent,
        email=user.email,
    )


@router.post("/resend-verification", response_model=MessageOut)
def resend_verification(data: ResendVerificationIn, request: Request, db: DBSession):
    input_email = str(data.email).strip().lower()

    user = db.scalar(select(User).where(User.email == input_email))

    if not user:
        return MessageOut(
            message="Se existir uma conta pendente para este e-mail, um novo link de verificação foi enviado."
        )

    if user.is_active and user.email_verified_at is not None:
        return MessageOut(message="Sua conta já está verificada. Faça login para continuar.")

    svc = EmailVerificationService(ttl_minutes=settings.email_verify_ttl_minutes)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    issued = svc.issue_for_user(db, user.id, ip=ip, user_agent=ua)

    verify_link = f"{settings.public_api_url}/api/v1/auth/verify-email?token={issued.token}"

    sender = _get_email_sender()
    try:
        sender.send_verification_email(user.email, verify_link)
    except EmailSendError as e:
        print(f"[EMAIL][ERROR][RESEND] to={user.email} user={user.id} err={e}")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "EMAIL_RESEND_FAILED",
                "message": "Não foi possível reenviar o e-mail de verificação. Tente novamente em instantes.",
            },
        ) from None

    print(
        f"[EMAIL-VERIFY][RESEND] user={user.id} email={user.email} expires_at={issued.expires_at.isoformat()}"
    )

    return MessageOut(
        message="Enviamos um novo link de verificação para o seu e-mail. Confira também a caixa de spam."
    )


@router.post("/forgot-password", response_model=MessageOut)
def forgot_password(data: ForgotPasswordRequestIn, request: Request, db: DBSession):
    input_email = str(data.email).strip().lower()

    generic_message = "Se existir uma conta compatível com este e-mail, enviaremos um link para redefinição de senha."

    user = db.scalar(select(User).where(User.email == input_email))
    if not user:
        return MessageOut(message=generic_message)

    if not user.is_active or user.email_verified_at is None:
        return MessageOut(message=generic_message)

    if not user.password_hash:
        google_identity = _get_google_identity(db, user.id)
        if google_identity is not None:
            return MessageOut(
                message=(
                    "Esta conta foi criada com Google e ainda não possui senha. "
                    "Entre com Google para concluir o cadastro e definir sua senha."
                )
            )

        if _is_student_like_role(user.role):
            return MessageOut(
                message=(
                    "Sua conta foi aprovada, mas você ainda não definiu sua senha. "
                    "Use o fluxo de primeiro acesso para criar sua senha."
                )
            )

        return MessageOut(
            message=(
                "Esta conta ainda não possui uma senha cadastrada. "
                "Use o método original de acesso ou conclua o cadastro antes de redefinir a senha."
            )
        )

    svc = PasswordResetService(ttl_minutes=getattr(settings, "password_reset_ttl_minutes", 30))
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    issued = svc.issue_for_user(db, user.id, ip=ip, user_agent=ua)

    reset_link = _build_password_reset_link(issued.token)

    sender = _get_email_sender()
    try:
        sender.send_password_reset_email(user.email, reset_link)
    except EmailSendError as e:
        print(f"[EMAIL][ERROR][RESET] to={user.email} user={user.id} err={e}")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "PASSWORD_RESET_EMAIL_FAILED",
                "message": "Não foi possível enviar o e-mail de redefinição de senha. Tente novamente em instantes.",
            },
        ) from None

    print(
        f"[PASSWORD-RESET] user={user.id} email={user.email} expires_at={issued.expires_at.isoformat()}"
    )

    return MessageOut(message=generic_message)


@router.post("/reset-password", response_model=MessageOut)
def reset_password(data: ResetPasswordIn, db: DBSession):
    svc = PasswordResetService(ttl_minutes=getattr(settings, "password_reset_ttl_minutes", 30))
    new_password_hash = get_password_hash(data.password)

    try:
        svc.consume_token(db, data.token, password_hash=new_password_hash)
    except PasswordResetExpired:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "PASSWORD_RESET_TOKEN_EXPIRED",
                "message": "O link de redefinição expirou. Solicite um novo link.",
            },
        ) from None
    except PasswordResetInvalid:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "PASSWORD_RESET_TOKEN_INVALID",
                "message": "O link de redefinição é inválido ou já foi utilizado.",
            },
        ) from None

    return MessageOut(message="Sua senha foi redefinida com sucesso. Faça login para continuar.")


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, db: DBSession):
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token ausente")

    try:
        claims = decode_refresh_token(token)
        if claims.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token inválido")
        user_id = UUID(safe_get_subject(claims))
    except Exception:
        raise HTTPException(status_code=401, detail="Refresh token inválido") from None

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuário inválido")

    new_access = create_access_token(subject=str(user.id))
    new_refresh = create_refresh_token(subject=str(user.id))
    _set_refresh_cookie(response, new_refresh)

    return TokenOut(access_token=new_access, expires_in=settings.access_token_expire_minutes * 60)


@router.post("/logout", response_model=MessageOut)
def logout(response: Response):
    _clear_refresh_cookie(response)
    return MessageOut(message="ok")


@router.get("/me", response_model=MeOut)
def me(user_id: str = Depends(get_current_user_id), db: DBSession = None):
    user = db.get(User, UUID(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado",
        )

    has_password = bool(user.password_hash)
    google_identity = _get_google_identity(db, user.id)
    auth_provider = "password"

    if not has_password and google_identity is not None:
        auth_provider = "google"

    return MeOut(
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        email_verified=user.email_verified_at is not None,
        auth_provider=auth_provider,
        avatar_url=(
            getattr(google_identity, "provider_avatar_url", None)
            if google_identity is not None
            else None
        ),
        has_password=has_password,
        whatsapp=user.whatsapp,
        instagram=user.instagram,
        birth_date=user.birth_date,
        zip_code=user.zip_code,
        guardian_full_name=user.guardian_full_name,
        guardian_whatsapp=user.guardian_whatsapp,
        guardian_relationship=user.guardian_relationship,
        profile_completed=_is_profile_completed(user),
    )


@router.get("/verify-email")
def verify_email(token: str, db: DBSession):
    svc = EmailVerificationService(ttl_minutes=settings.email_verify_ttl_minutes)

    ok_url = f"{settings.frontend_url}{settings.frontend_verify_redirect_path}?verified=1"
    invalid_url = (
        f"{settings.frontend_url}{settings.frontend_verify_redirect_path}?verified=0&reason=invalid"
    )
    expired_url = (
        f"{settings.frontend_url}{settings.frontend_verify_redirect_path}?verified=0&reason=expired"
    )

    try:
        user_id = svc.verify_token(db, token)
    except EmailVerificationExpired:
        return RedirectResponse(url=expired_url, status_code=status.HTTP_302_FOUND)
    except EmailVerificationInvalid:
        return RedirectResponse(url=invalid_url, status_code=status.HTTP_302_FOUND)

    resp = RedirectResponse(url=ok_url, status_code=status.HTTP_302_FOUND)
    refresh = create_refresh_token(subject=str(user_id))
    _set_refresh_cookie(resp, refresh)
    return resp

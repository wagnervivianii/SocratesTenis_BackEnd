from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Geral
    env: str = "dev"
    app_name: str = "SocratesTenis API"
    version: str = "0.1.0"

    # CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Banco
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/socratestennis"

    # Auth / JWT
    jwt_algorithm: str = "HS256"
    jwt_access_secret_key: str = "dev-change-me-access"
    jwt_refresh_secret_key: str = "dev-change-me-refresh"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14

    # Cookie refresh
    refresh_cookie_name: str = "st_refresh"
    refresh_cookie_path: str = "/api/v1/auth/refresh"
    refresh_cookie_samesite: str = "lax"
    refresh_cookie_secure: bool = False
    refresh_cookie_domain: str | None = None

    # URLs públicas
    public_api_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    frontend_verify_redirect_path: str = "/login"

    # Email verification
    email_verify_ttl_minutes: int = 30

    # ✅ Email sender
    # "console" (dev) ou "smtp" (real)
    email_sender_backend: str = "console"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_authorize_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_userinfo_url: str = "https://openidconnect.googleapis.com/v1/userinfo"
    google_scopes: str = "openid email profile"
    google_oauth_state_ttl_minutes: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()

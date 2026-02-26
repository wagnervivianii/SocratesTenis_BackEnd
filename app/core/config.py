from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Geral
    env: str = "dev"
    app_name: str = "SocratesTenis API"
    version: str = "0.1.0"

    # CORS (quando conectar React/Apps)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Banco
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/socratestennis"

    # Auth / JWT
    jwt_algorithm: str = "HS256"

    # 🔐 Para dev pode ficar assim, mas em produção você VAI definir via .env
    jwt_access_secret_key: str = "dev-change-me-access"
    jwt_refresh_secret_key: str = "dev-change-me-refresh"

    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14

    # Cookie do refresh token (httpOnly)
    refresh_cookie_name: str = "st_refresh"
    refresh_cookie_path: str = "/api/v1/auth/refresh"
    refresh_cookie_samesite: str = "lax"  # "lax" é um ótimo default
    refresh_cookie_secure: bool = False  # em prod vamos trocar para True (HTTPS)
    refresh_cookie_domain: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()

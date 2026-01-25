from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Geral
    env: str = "dev"
    app_name: str = "SocratesTenis API"
    version: str = "0.1.0"

    # CORS (quando conectar React/Apps)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()

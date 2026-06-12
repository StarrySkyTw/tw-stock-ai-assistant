from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./tw_stock_assistant.db"
    cors_origins: str = "http://localhost:3000"

    finmind_token: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4-mini"
    enable_live_data: bool = True

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    alert_email_to: str | None = None

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    line_channel_access_token: str | None = None
    line_to_id: str | None = None

    reports_dir: Path = Path("storage/reports")
    after_close_hour: int = 18
    after_close_minute: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    return settings

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_FILES = (
    API_ROOT / ".env",
    API_ROOT / ".env.local",
    PROJECT_ROOT / ".env.local",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./tw_stock_assistant.db"
    cors_origins: str = "http://localhost:3000"

    finmind_token: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4-mini"
    enable_live_data: bool = True
    market_risk_cache_ttl_seconds: int = 8
    market_data_cache_ttl_seconds: int = 20
    analysis_data_timeout_seconds: float = 0.65
    analysis_cache_ttl_seconds: int = 12
    analysis_background_timeout_seconds: float = 8.0
    analysis_response_timeout_seconds: float = 0.85
    analysis_wait_timeout_seconds: float = 9.5
    market_scan_max_symbols: int = 120
    market_scan_concurrency: int = 6

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
    static_web_dir: Path | None = None
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

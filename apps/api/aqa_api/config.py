"""Application settings loaded from environment."""

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    api_port: int = 3001
    node_env: str = "development"
    log_level: str = "info"
    api_version: str = "0.1.0"
    encryption_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or f"{self.redis_url.rstrip('/')}/0"

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.broker_url

    @property
    def is_development(self) -> bool:
        return self.node_env == "development"


settings = Settings()

"""Application API request/response schemas (SPEC §16.2)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


def _hostname(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("must be a valid HTTP or HTTPS URL with a hostname")
    return parsed.hostname.lower()


class AuthConfigInput(BaseModel):
    type: str = "form"
    login_url: str | None = None
    email_selector: str | None = None
    password_selector: str | None = None
    submit_selector: str | None = None
    credentials_secret_ref: str | None = None
    cookies: list[dict[str, Any]] | None = None


class CrawlConfigInput(BaseModel):
    max_depth: int = Field(default=5, ge=1, le=10)
    max_pages: int = Field(default=100, ge=1, le=500)
    allowed_domains: list[str] | None = None
    excluded_urls: list[str] = Field(default_factory=list)
    respect_robots_txt: bool = True
    page_timeout_ms: int | None = Field(default=30000, ge=1000, le=120000)


class CreateApplicationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    base_url: str
    seed_urls: list[str] = Field(default_factory=list)
    auth_config: AuthConfigInput | None = None
    crawl_config: CrawlConfigInput | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        _hostname(value)
        return value

    @model_validator(mode="after")
    def validate_seed_urls(self) -> CreateApplicationRequest:
        base_host = _hostname(self.base_url)
        allowed = (
            self.crawl_config.allowed_domains
            if self.crawl_config and self.crawl_config.allowed_domains
            else [base_host]
        )
        allowed_lower = {d.lower() for d in allowed}
        for seed in self.seed_urls:
            seed_host = _hostname(seed)
            if seed_host not in allowed_lower:
                raise ValueError(
                    f"seed_urls hostname {seed_host!r} must be in allowed_domains "
                    f"{sorted(allowed_lower)}"
                )
        return self


class PublicAuthConfig(BaseModel):
    configured: bool
    type: str | None = None


class ApplicationResponse(BaseModel):
    app_id: UUID
    name: str
    base_url: str
    seed_urls: list[str]
    auth_config: PublicAuthConfig
    crawl_config: dict[str, Any]
    last_crawl_at: datetime | None = None
    last_run_at: datetime | None = None
    overall_health_score: Decimal | None = None
    config_version: int
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApplicationListResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int

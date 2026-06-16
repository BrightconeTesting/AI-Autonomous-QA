"""Application CRUD service (Day 11–12)."""

from __future__ import annotations

from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aqa_api.config import settings
from aqa_api.schemas.apps import ApplicationResponse, CreateApplicationRequest, PublicAuthConfig
from aqa_shared.crypto.auth_config import (
    is_encrypted_auth_config,
    prepare_auth_config_for_storage,
)
from aqa_shared.db.models import Application
from aqa_shared.security.url_validator import UrlSecurityError, validate_url_safe, validate_urls_safe


def _base_hostname(base_url: str) -> str:
    return urlparse(base_url).hostname or ""


def _build_crawl_config(body: CreateApplicationRequest) -> dict:
    crawl = body.crawl_config.model_dump() if body.crawl_config else {}
    if not crawl.get("allowed_domains"):
        crawl["allowed_domains"] = [_base_hostname(body.base_url)]
    return crawl


def validate_application_urls(body: CreateApplicationRequest) -> None:
    validate_url_safe(body.base_url)
    validate_urls_safe(body.seed_urls)


def public_auth_config(raw: dict | None) -> PublicAuthConfig:
    if not raw:
        return PublicAuthConfig(configured=False)
    if is_encrypted_auth_config(raw):
        return PublicAuthConfig(configured=True, type=str(raw.get("type", "form")))
    auth_type = raw.get("type")
    if not auth_type and not raw.get("credentials_secret_ref") and not raw.get("cookies"):
        return PublicAuthConfig(configured=False)
    return PublicAuthConfig(configured=True, type=str(auth_type or "form"))


def to_application_response(app: Application) -> ApplicationResponse:
    raw_auth = app.auth_config if isinstance(app.auth_config, dict) else {}
    return ApplicationResponse(
        app_id=app.app_id,
        name=app.name,
        base_url=app.base_url,
        seed_urls=list(app.seed_urls or []),
        auth_config=public_auth_config(raw_auth),
        crawl_config=dict(app.crawl_config or {}),
        last_crawl_at=app.last_crawl_at,
        last_run_at=app.last_run_at,
        overall_health_score=app.overall_health_score,
        config_version=app.config_version,
        created_at=app.created_at,
        updated_at=app.updated_at,
    )


def create_application(db: Session, body: CreateApplicationRequest) -> Application:
    validate_application_urls(body)

    plain_auth = body.auth_config.model_dump(exclude_none=True) if body.auth_config else {}
    stored_auth = prepare_auth_config_for_storage(
        plain_auth,
        allow_plaintext=settings.is_development,
    )

    app = Application(
        name=body.name,
        base_url=body.base_url,
        seed_urls=body.seed_urls,
        auth_config=stored_auth,
        crawl_config=_build_crawl_config(body),
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def list_applications(db: Session) -> list[Application]:
    return list(db.scalars(select(Application).order_by(Application.created_at.desc())).all())


def get_application(db: Session, app_id: UUID) -> Application | None:
    return db.get(Application, app_id)

"""Application CRUD service (Day 11–12)."""

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from aqa_api.config import settings
from aqa_api.schemas.apps import ApplicationResponse, CreateApplicationRequest, PublicAuthConfig
from aqa_api.services.artifacts import artifact_storage_root
from aqa_api.services.pipeline_runs import find_active_pipeline_run, reconcile_stale_active_pipeline
from aqa_shared.crypto.auth_config import (
    is_encrypted_auth_config,
    prepare_auth_config_for_storage,
)
from aqa_shared.db.models import Application, Artifact, PipelineRun, TestRun
from aqa_shared.security.url_validator import UrlSecurityError, validate_url_safe, validate_urls_safe


def _base_hostname(base_url: str) -> str:
    return urlparse(base_url).hostname or ""


def _build_crawl_config(body: CreateApplicationRequest) -> dict:
    crawl = body.crawl_config.model_dump() if body.crawl_config else {}
    if not crawl.get("allowed_domains"):
        crawl["allowed_domains"] = [_base_hostname(body.base_url)]
    crawl.setdefault("enable_cic", True)
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
    has_material = bool(
        raw.get("credentials")
        or raw.get("credentials_secret_ref")
        or raw.get("cookies")
    )
    if not auth_type and not has_material:
        return PublicAuthConfig(configured=False)
    if not has_material:
        return PublicAuthConfig(configured=False, type=str(auth_type) if auth_type else None)
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


def _normalize_plain_auth(body: CreateApplicationRequest) -> dict:
    if not body.auth_config:
        return {}

    plain_auth = body.auth_config.model_dump(exclude_none=True)
    creds = body.auth_config.credentials
    if creds and not creds.is_empty():
        plain_auth["credentials"] = {
            "email": creds.resolved_email(),
            "password": creds.password,
        }
    else:
        plain_auth.pop("credentials", None)

    has_material = bool(
        plain_auth.get("credentials")
        or plain_auth.get("credentials_secret_ref")
        or plain_auth.get("cookies")
    )
    if not has_material:
        return {}

    return plain_auth


def create_application(db: Session, body: CreateApplicationRequest) -> Application:
    validate_application_urls(body)

    plain_auth = _normalize_plain_auth(body)
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


def _purge_app_artifact_files(db: Session, app_id: UUID) -> None:
    run_ids = list(db.scalars(select(TestRun.run_id).where(TestRun.app_id == app_id)))
    pipeline_ids = list(
        db.scalars(select(PipelineRun.id).where(PipelineRun.application_id == app_id))
    )
    conditions = []
    if run_ids:
        conditions.append(Artifact.run_id.in_(run_ids))
    if pipeline_ids:
        conditions.append(Artifact.pipeline_run_id.in_(pipeline_ids))
    if conditions:
        artifacts = db.scalars(select(Artifact).where(or_(*conditions))).all()
        for artifact in artifacts:
            path = Path(artifact.path)
            if path.is_file():
                path.unlink(missing_ok=True)
            db.delete(artifact)

    screenshot_dir = artifact_storage_root() / "screenshots" / str(app_id)
    if screenshot_dir.is_dir():
        shutil.rmtree(screenshot_dir, ignore_errors=True)


def delete_application(db: Session, app_id: UUID) -> bool:
    """Delete application and related data. Returns False if not found."""
    app = get_application(db, app_id)
    if app is None:
        return False

    reconcile_stale_active_pipeline(db, app_id)
    active = find_active_pipeline_run(db, app_id)
    if active is not None:
        from aqa_api.services.pipeline_runs import ActivePipelineConflictError

        raise ActivePipelineConflictError(active.id)

    _purge_app_artifact_files(db, app_id)
    db.flush()
    # Core DELETE — avoid ORM db.delete(app) which nulls child FKs (flows.app_id) and fails.
    db.execute(delete(Application).where(Application.app_id == app_id))
    db.commit()
    return True

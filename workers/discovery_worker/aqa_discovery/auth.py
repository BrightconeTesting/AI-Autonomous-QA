"""Application authentication for discovery crawl (SPEC §15.7, §23.1, Day 18)."""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse

from sqlalchemy.orm import Session

from aqa_shared.crypto.auth_config import decrypt_auth_config, is_encrypted_auth_config
from aqa_shared.db.models import CredentialAccessAudit, CredentialAuditAction

logger = logging.getLogger(__name__)

ACCESSOR = "discovery_worker"
_SENSITIVE_KEYS = frozenset({"password", "token", "secret", "api_key", "authorization"})


class AuthError(Exception):
    """Raised when authentication configuration or login fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


AuditFn = Callable[[CredentialAuditAction], None]


def redact_secrets(value: Any) -> Any:
    """Return a log-safe copy with sensitive fields masked."""
    if isinstance(value, dict):
        return {
            key: ("***" if key.lower() in _SENSITIVE_KEYS else redact_secrets(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def resolve_credentials_secret_ref(ref: str) -> dict[str, str]:
    """Load email/password JSON from an environment variable name."""
    raw = os.getenv(ref, "").strip()
    if not raw:
        raise AuthError(f"Credential secret {ref!r} is not set in the environment")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AuthError(f"Credential secret {ref!r} must be valid JSON") from exc

    if not isinstance(data, dict):
        raise AuthError(f"Credential secret {ref!r} must decode to a JSON object")

    email = data.get("email") or data.get("username")
    password = data.get("password")
    if not email or not password:
        raise AuthError(f"Credential secret {ref!r} must include email and password")

    return {"email": str(email), "password": str(password)}


def write_credential_audit(
    db: Session,
    *,
    app_id: uuid.UUID,
    pipeline_run_id: uuid.UUID | None,
    action: CredentialAuditAction,
    accessor: str = ACCESSOR,
) -> None:
    """Persist credential access audit row (SPEC §23.1)."""
    db.add(
        CredentialAccessAudit(
            app_id=app_id,
            pipeline_run_id=pipeline_run_id,
            accessor=accessor,
            action=action,
        )
    )
    db.commit()


def load_auth_config(
    stored: dict[str, Any] | None,
    *,
    audit: AuditFn | None = None,
) -> dict[str, Any]:
    """Decrypt auth_config for worker use and record decrypt audit when encrypted."""
    if not stored:
        return {}
    if is_encrypted_auth_config(stored):
        if audit is not None:
            audit(CredentialAuditAction.decrypt)
        return decrypt_auth_config(stored)
    return dict(stored)


def _resolve_login_url(base_url: str, auth_config: dict[str, Any]) -> str:
    login_url = auth_config.get("login_url") or base_url
    if login_url.startswith(("http://", "https://", "about:", "data:")):
        return login_url
    return urljoin(base_url.rstrip("/") + "/", login_url.lstrip("/"))


def _normalize_cookies(cookies: list[dict[str, Any]], base_url: str) -> list[dict[str, Any]]:
    parsed = urlparse(base_url)
    hostname = parsed.hostname
    if not hostname:
        raise AuthError(f"Cannot inject cookies without a hostname in base_url: {base_url!r}")

    normalized: list[dict[str, Any]] = []
    for raw in cookies:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        value = raw.get("value")
        if not name or value is None:
            continue
        cookie: dict[str, Any] = {
            "name": str(name),
            "value": str(value),
            "domain": str(raw.get("domain") or hostname),
            "path": str(raw.get("path") or "/"),
        }
        if "expires" in raw and raw["expires"] is not None:
            cookie["expires"] = raw["expires"]
        if raw.get("httpOnly") is not None:
            cookie["httpOnly"] = bool(raw["httpOnly"])
        if raw.get("secure") is not None:
            cookie["secure"] = bool(raw["secure"])
        if raw.get("sameSite") is not None:
            cookie["sameSite"] = raw["sameSite"]
        normalized.append(cookie)
    if not normalized:
        raise AuthError("auth_config.cookies must include at least one cookie with name and value")
    return normalized


def inject_cookies(
    browser_context,
    cookies: list[dict[str, Any]],
    *,
    base_url: str,
    audit: AuditFn | None = None,
) -> None:
    """Inject session cookies into the Playwright browser context."""
    normalized = _normalize_cookies(cookies, base_url)
    browser_context.add_cookies(normalized)
    if audit is not None:
        audit(CredentialAuditAction.inject)
    logger.info(
        "DiscoveryWorker cookies injected",
        extra={"cookieCount": len(normalized), "domain": normalized[0]["domain"]},
    )


def perform_form_login(
    page,
    *,
    auth_config: dict[str, Any],
    base_url: str,
    page_timeout_ms: int,
    audit: AuditFn | None = None,
    detect_blockers: Callable[[Any], None] | None = None,
    navigate: bool = True,
) -> None:
    """Fill and submit a login form using selectors from auth_config."""
    ref = auth_config.get("credentials_secret_ref")
    if not ref:
        raise AuthError("Form login requires credentials_secret_ref")

    if audit is not None:
        audit(CredentialAuditAction.read)

    credentials = resolve_credentials_secret_ref(str(ref))
    email_selector = auth_config.get("email_selector")
    password_selector = auth_config.get("password_selector")
    submit_selector = auth_config.get("submit_selector")
    if not email_selector or not password_selector or not submit_selector:
        raise AuthError("Form login requires email_selector, password_selector, and submit_selector")

    if navigate:
        login_url = _resolve_login_url(base_url, auth_config)
        page.goto(login_url, timeout=page_timeout_ms, wait_until="domcontentloaded")
        if detect_blockers is not None:
            detect_blockers(page)

    page.locator(str(email_selector)).fill(credentials["email"])
    page.locator(str(password_selector)).fill(credentials["password"])
    page.locator(str(submit_selector)).click()

    page.wait_for_load_state("networkidle", timeout=page_timeout_ms)
    if detect_blockers is not None:
        detect_blockers(page)

    logger.info(
        "DiscoveryWorker form login completed",
        extra={
            "loginUrl": _resolve_login_url(base_url, auth_config) if navigate else page.url,
            "finalUrl": page.url,
            "credentialsRef": ref,
        },
    )


def authenticate_browser(
    browser_context,
    *,
    auth_config: dict[str, Any],
    base_url: str,
    page_timeout_ms: int,
    audit: AuditFn | None = None,
    detect_blockers: Callable[[Any], None] | None = None,
) -> bool:
    """Authenticate the browser context before crawl. Returns True when auth ran."""
    if not auth_config:
        return False

    auth_type = str(auth_config.get("type") or "form")

    cookies = auth_config.get("cookies")
    if cookies:
        inject_cookies(browser_context, list(cookies), base_url=base_url, audit=audit)
        return True

    if auth_type != "form":
        logger.info(
            "DiscoveryWorker auth skipped — unsupported auth type",
            extra={"authType": auth_type},
        )
        return False

    if not auth_config.get("credentials_secret_ref"):
        logger.info("DiscoveryWorker auth skipped — no credentials_secret_ref or cookies")
        return False

    page = browser_context.new_page()
    try:
        perform_form_login(
            page,
            auth_config=auth_config,
            base_url=base_url,
            page_timeout_ms=page_timeout_ms,
            audit=audit,
            detect_blockers=detect_blockers,
        )
    finally:
        page.close()
    return True

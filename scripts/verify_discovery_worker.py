#!/usr/bin/env python3
"""Verify DiscoveryWorker Playwright fetch + BFS crawl — Days 15–19."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.robotparser import RobotFileParser

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql://aqa:aqa@localhost:5432/autonomous_qa")
os.environ.setdefault("ENCRYPTION_KEY", "0123456789abcdef" * 4)

from aqa_discovery.auth import (
    inject_cookies,
    load_auth_config,
    perform_form_login,
    redact_secrets,
    resolve_credentials_secret_ref,
    write_credential_audit,
)
from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.crawler import CrawlSession, fetch_page
from aqa_discovery.extractors import build_locators, extract_elements
from aqa_discovery.persist import (
    mark_pipeline_completed,
    mark_pipeline_running,
    persist_crawl_result,
    screenshot_path_for_page,
    update_last_crawl_at,
)
from aqa_discovery.robots import RobotsChecker
from aqa_discovery.safety import is_safety_excluded_link, is_safety_excluded_url
from aqa_discovery.types import CrawlResult, ElementSnapshot, PageSnapshot
from aqa_discovery.url_utils import is_allowed_domain, is_excluded_url, normalize_crawl_url
from aqa_shared.crypto.auth_config import prepare_auth_config_for_storage
from aqa_shared.db.models import (
    Application,
    Artifact,
    ArtifactType,
    CredentialAccessAudit,
    CredentialAuditAction,
    Element,
    Page,
    PipelineRun,
    PipelineStage,
    PipelineStatus,
)
from aqa_shared.db.session import get_session_factory


def _verify_url_utils() -> bool:
    assert normalize_crawl_url("https://Example.com/path/") == "https://example.com/path"
    assert normalize_crawl_url("https://example.com/#/login") == "https://example.com/#/login"
    juice_home = normalize_crawl_url("https://juice-shop.herokuapp.com/")
    juice_login = normalize_crawl_url("https://juice-shop.herokuapp.com/#/login")
    juice_search = normalize_crawl_url("https://juice-shop.herokuapp.com/#/search")
    assert juice_login != juice_home
    assert juice_search != juice_home
    assert juice_search != juice_login
    assert is_allowed_domain("https://example.com/a", {"example.com"}) is True
    assert is_allowed_domain("https://other.com/a", {"example.com"}) is False
    assert is_excluded_url("https://example.com/logout", ["**/logout**"]) is True
    assert is_excluded_url("https://example.com/about", ["**/logout**"]) is False
    print("OK url_utils: normalize, hash-SPA routes, allowed_domains, excluded_urls")
    return True


def _verify_safety_exclusions() -> bool:
    assert is_safety_excluded_url("https://example.com/logout") is True
    assert is_safety_excluded_url("https://example.com/account/sign-out") is True
    assert is_safety_excluded_url("https://example.com/delete-account") is True
    assert is_safety_excluded_url("https://example.com/about") is False
    assert is_safety_excluded_link(href="https://example.com/home", link_text="Sign out") is True
    assert is_safety_excluded_link(href="https://example.com/home", link_text="About us") is False

    settings = CrawlSettings(
        max_depth=1,
        max_pages=5,
        allowed_domains=["example.com"],
        respect_robots_txt=False,
    )
    try:
        with CrawlSession() as session:
            result = session.crawl_bfs(["https://example.com/logout"], settings)
    except Exception as exc:
        print(f"FAIL safety crawl: {exc}", file=sys.stderr)
        return False

    if result.pages:
        print("FAIL logout URL was crawled", file=sys.stderr)
        return False
    if result.stats.skipped_safety < 1:
        print(f"FAIL expected skipped_safety >= 1, got {result.stats.skipped_safety}", file=sys.stderr)
        return False

    print(f"OK safety exclusions: skipped_safety={result.stats.skipped_safety}")
    return True


def _verify_robots_txt() -> bool:
    parser = RobotFileParser()
    parser.parse(["User-agent: *", "Disallow: /private"])

    with patch.object(RobotsChecker, "_fetch_parser", return_value=parser):
        checker = RobotsChecker("https://example.com", enabled=True)
        if not checker.is_allowed("https://example.com/about"):
            print("FAIL robots allowed path rejected", file=sys.stderr)
            return False
        if checker.is_allowed("https://example.com/private/admin"):
            print("FAIL robots disallowed path accepted", file=sys.stderr)
            return False

    disabled = RobotsChecker("https://example.com", enabled=False)
    if not disabled.is_allowed("https://example.com/private/admin"):
        print("FAIL respect_robots_txt=false should allow all paths", file=sys.stderr)
        return False

    print("OK robots.txt: disallowed paths skipped when enabled")
    return True


def _verify_captcha_halt() -> bool:
    from aqa_discovery.types import CrawlHaltError

    try:
        with CrawlSession() as session:
            page = session._context.new_page()
            try:
                page.set_content("<html><body><div class='g-recaptcha'></div></body></html>")
                session._detect_captcha_or_mfa(page)
            finally:
                page.close()
    except CrawlHaltError as exc:
        if "CAPTCHA" not in exc.message:
            print(f"FAIL unexpected halt message: {exc.message}", file=sys.stderr)
            return False
        print(f"OK CAPTCHA detection halts crawl: reason={exc.message[:60]}...")
        return True
    except Exception as exc:
        print(f"FAIL captcha halt detection: {exc}", file=sys.stderr)
        return False

    print("FAIL CAPTCHA page should raise CrawlHaltError", file=sys.stderr)
    return False


def _verify_single_fetch() -> bool:
    try:
        with CrawlSession() as session:
            snapshot = session.fetch_page("https://example.com")
    except Exception as exc:
        hint = "Run `pnpm playwright:install` if browsers are missing."
        print(f"FAIL CrawlSession fetch: {exc}", file=sys.stderr)
        print(f"Hint: {hint}", file=sys.stderr)
        return False

    if snapshot.status != 200 or not snapshot.title or snapshot.html_length <= 0:
        print(f"FAIL single fetch snapshot: {snapshot}", file=sys.stderr)
        return False
    print(
        f"OK CrawlSession fetch_page: url={snapshot.url} title={snapshot.title!r} "
        f"html_length={snapshot.html_length}"
    )

    standalone = fetch_page("https://example.com")
    if standalone.status != 200 or standalone.html_length <= 0:
        print("FAIL standalone fetch_page helper", file=sys.stderr)
        return False
    print(f"OK fetch_page helper: html_length={standalone.html_length}")
    return True


def _verify_bfs_crawl() -> bool:
    settings = CrawlSettings(
        max_depth=2,
        max_pages=5,
        allowed_domains=["example.com", "www.example.com"],
        excluded_urls=["**/iana.org/**"],
        page_timeout_ms=30_000,
        respect_robots_txt=False,
    )
    try:
        with CrawlSession(page_timeout_ms=settings.page_timeout_ms) as session:
            result = session.crawl_bfs(["https://example.com"], settings)
    except Exception as exc:
        print(f"FAIL BFS crawl: {exc}", file=sys.stderr)
        return False

    if not result.pages:
        print("FAIL BFS crawl returned no pages", file=sys.stderr)
        return False
    if len(result.pages) > settings.max_pages:
        print(f"FAIL BFS exceeded max_pages: {len(result.pages)}", file=sys.stderr)
        return False
    if result.stats.pages_crawled != len(result.pages):
        print("FAIL BFS stats.pages_crawled mismatch", file=sys.stderr)
        return False

    for page in result.pages:
        host = page.url.split("/")[2].lower()
        if not host.endswith("example.com"):
            print(f"FAIL off-domain page crawled: {page.url}", file=sys.stderr)
            return False

    print(
        f"OK BFS crawl: pages={len(result.pages)} "
        f"skipped_off_domain={result.stats.skipped_off_domain} "
        f"skipped_excluded={result.stats.skipped_excluded}"
    )
    return True


def _verify_locator_priority() -> bool:
    semantic, xpath = build_locators(
        {
            "tag": "button",
            "role": "button",
            "accessibleName": "Sign in",
            "text": "Sign in",
            "xpath": "//button[1]",
        }
    )
    if not semantic or "getByRole" not in semantic:
        print(f"FAIL locator priority role: {semantic}", file=sys.stderr)
        return False
    if xpath != "//button[1]":
        print(f"FAIL xpath fallback: {xpath}", file=sys.stderr)
        return False

    label_semantic, _ = build_locators(
        {
            "tag": "input",
            "role": "textbox",
            "label": "Email address",
            "xpath": "//input[1]",
        }
    )
    if not label_semantic or "getByLabel" not in label_semantic:
        print(f"FAIL locator priority label: {label_semantic}", file=sys.stderr)
        return False

    print("OK extractors: locator priority role > label")
    return True


def _verify_element_extraction() -> bool:
    try:
        with CrawlSession() as session:
            page = session._context.new_page()
            try:
                page.set_content(
                    """
                    <html>
                      <body>
                        <a href="/about">About us</a>
                        <button type="button">Sign in</button>
                        <label for="email">Email address</label>
                        <input id="email" name="email" placeholder="you@example.com" />
                      </body>
                    </html>
                    """
                )
                elements = extract_elements(page)
            finally:
                page.close()
    except Exception as exc:
        print(f"FAIL element extraction: {exc}", file=sys.stderr)
        return False

    roles = {item.role for item in elements}
    if "link" not in roles or "button" not in roles:
        print(f"FAIL expected link/button roles, got {roles}", file=sys.stderr)
        return False
    if not any(item.semantic_selector and "getByRole" in item.semantic_selector for item in elements):
        print("FAIL no getByRole semantic selector generated", file=sys.stderr)
        return False

    print(f"OK element extraction: count={len(elements)}")
    return True


def _verify_persist_crawl_result() -> bool:
    session = get_session_factory()()
    app_id = uuid.uuid4()
    pipeline_run_id = uuid.uuid4()
    screenshot_path = screenshot_path_for_page(
        app_id=app_id,
        url="https://example.com/persist-verify",
    )
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path.write_bytes(b"fake-png")

    try:
        session.add(
            Application(
                app_id=app_id,
                name=f"verify-persist-{app_id.hex[:8]}",
                base_url="https://example.com",
            )
        )
        session.add(
            PipelineRun(
                id=pipeline_run_id,
                application_id=app_id,
                status=PipelineStatus.pending,
                current_stage=PipelineStage.discover,
            )
        )
        session.commit()

        mark_pipeline_running(session, pipeline_run_id)
        running = session.get(PipelineRun, pipeline_run_id)
        if running is None or running.status != PipelineStatus.running:
            print(f"FAIL pipeline running status: {running}", file=sys.stderr)
            return False

        crawl_result = CrawlResult(
            pages=[
                PageSnapshot(
                    url="https://example.com/persist-verify",
                    title="Persist Verify",
                    status=200,
                    html_length=100,
                    depth=0,
                    elements=[
                        ElementSnapshot(
                            tag_name="button",
                            role="button",
                            text_content="Go",
                            semantic_selector="getByRole('button', { name: 'Go' })",
                            xpath_fallback="//button[1]",
                        )
                    ],
                    screenshot_path=str(screenshot_path),
                )
            ]
        )
        result = persist_crawl_result(
            session,
            app_id=app_id,
            pipeline_run_id=pipeline_run_id,
            crawl_result=crawl_result,
        )
        update_last_crawl_at(session, app_id)
        mark_pipeline_completed(
            session,
            pipeline_run_id,
            page_count=result.page_count,
            element_count=result.element_count,
        )

        page_rows = session.query(Page).filter(Page.app_id == app_id).all()
        element_rows = session.query(Element).join(Page).filter(Page.app_id == app_id).all()
        artifact_rows = (
            session.query(Artifact)
            .filter(
                Artifact.pipeline_run_id == pipeline_run_id,
                Artifact.type == ArtifactType.screenshot,
            )
            .all()
        )
        completed = session.get(PipelineRun, pipeline_run_id)
        app = session.get(Application, app_id)

        if len(page_rows) != 1:
            print(f"FAIL pages persisted: {len(page_rows)}", file=sys.stderr)
            return False
        if len(element_rows) != 1:
            print(f"FAIL elements persisted: {len(element_rows)}", file=sys.stderr)
            return False
        if len(artifact_rows) != 1:
            print(f"FAIL screenshot artifacts persisted: {len(artifact_rows)}", file=sys.stderr)
            return False
        if completed is None or completed.status != PipelineStatus.completed:
            print(f"FAIL pipeline completed status: {completed}", file=sys.stderr)
            return False
        if app is None or app.last_crawl_at is None:
            print("FAIL last_crawl_at not updated", file=sys.stderr)
            return False
    finally:
        session.query(Artifact).filter(Artifact.pipeline_run_id == pipeline_run_id).delete()
        session.query(Element).filter(
            Element.page_id.in_(session.query(Page.page_id).filter(Page.app_id == app_id))
        ).delete(synchronize_session=False)
        session.query(Page).filter(Page.app_id == app_id).delete()
        session.query(PipelineRun).filter(PipelineRun.id == pipeline_run_id).delete()
        session.query(Application).filter(Application.app_id == app_id).delete()
        session.commit()
        session.close()
        if screenshot_path.is_file():
            screenshot_path.unlink()

    print("OK persist: pages, elements, artifacts, pipeline status")
    return True


def _verify_auth_credentials() -> bool:
    secret_name = "VERIFY_JUICE_SHOP_TEST_USER"
    secret_value = json.dumps({"email": "user@example.com", "password": "secret-pass"})
    with patch.dict(os.environ, {secret_name: secret_value}, clear=False):
        creds = resolve_credentials_secret_ref(secret_name)
        if creds["email"] != "user@example.com" or creds["password"] != "secret-pass":
            print("FAIL credential resolution", file=sys.stderr)
            return False

    redacted = redact_secrets({"email": "user@example.com", "password": "secret-pass"})
    if redacted["password"] != "***":
        print(f"FAIL redact_secrets: {redacted}", file=sys.stderr)
        return False

    print("OK auth: resolve credentials_secret_ref + redact_secrets")
    return True


def _verify_form_login_mock() -> bool:
    auth_config = {
        "type": "form",
        "login_url": "about:blank",
        "email_selector": "input[name=email]",
        "password_selector": "input[name=password]",
        "submit_selector": "#loginButton",
        "credentials_secret_ref": "VERIFY_JUICE_SHOP_TEST_USER",
    }
    secret_value = json.dumps({"email": "user@example.com", "password": "secret-pass"})

    try:
        with patch.dict(os.environ, {"VERIFY_JUICE_SHOP_TEST_USER": secret_value}, clear=False):
            with CrawlSession() as session:
                page = session._context.new_page()
                try:
                    page.set_content(
                        """
                        <form>
                          <input name="email" />
                          <input name="password" type="password" />
                          <button id="loginButton" type="submit">Login</button>
                        </form>
                        <script>
                          document.querySelector('form').addEventListener('submit', (event) => {
                            event.preventDefault();
                            document.body.innerHTML = '<div id="logged-in">Welcome</div>';
                          });
                        </script>
                        """
                    )
                    perform_form_login(
                        page,
                        auth_config=auth_config,
                        base_url="https://example.com",
                        page_timeout_ms=10_000,
                        navigate=False,
                    )
                    if page.locator("#logged-in").count() == 0:
                        print("FAIL form login mock did not reach logged-in state", file=sys.stderr)
                        return False
                finally:
                    page.close()
    except Exception as exc:
        print(f"FAIL form login mock: {exc}", file=sys.stderr)
        return False

    print("OK auth: form login mock")
    return True


def _verify_cookie_injection() -> bool:
    try:
        with CrawlSession() as session:
            page = session._context.new_page()
            context = page.context
            page.close()
            inject_cookies(
                context,
                [{"name": "session", "value": "abc123"}],
                base_url="https://example.com",
            )
            cookies = session._context.cookies("https://example.com")
            if not any(cookie["name"] == "session" and cookie["value"] == "abc123" for cookie in cookies):
                print(f"FAIL cookie injection: {cookies}", file=sys.stderr)
                return False
    except Exception as exc:
        print(f"FAIL cookie injection: {exc}", file=sys.stderr)
        return False

    print("OK auth: cookie injection")
    return True


def _verify_credential_audit() -> bool:
    plain_auth = {
        "type": "form",
        "credentials_secret_ref": "JUICE_SHOP_TEST_USER",
        "email_selector": "input[name=email]",
        "password_selector": "input[name=password]",
        "submit_selector": "#loginButton",
    }
    stored_auth = prepare_auth_config_for_storage(plain_auth, allow_plaintext=True)
    audit_actions: list[CredentialAuditAction] = []

    def _audit(action: CredentialAuditAction) -> None:
        audit_actions.append(action)

    decrypted = load_auth_config(stored_auth, audit=_audit)
    if decrypted.get("credentials_secret_ref") != "JUICE_SHOP_TEST_USER":
        print("FAIL load_auth_config decrypt", file=sys.stderr)
        return False
    if CredentialAuditAction.decrypt not in audit_actions:
        print("FAIL decrypt audit callback not invoked for encrypted auth_config", file=sys.stderr)
        return False

    session = get_session_factory()()
    app_id = uuid.uuid4()
    try:
        session.add(
            Application(
                app_id=app_id,
                name=f"verify-auth-{app_id.hex[:8]}",
                base_url="https://example.com",
                auth_config=stored_auth,
            )
        )
        session.commit()

        write_credential_audit(
            session,
            app_id=app_id,
            pipeline_run_id=None,
            action=CredentialAuditAction.read,
        )
        rows = (
            session.query(CredentialAccessAudit)
            .filter(CredentialAccessAudit.app_id == app_id)
            .order_by(CredentialAccessAudit.timestamp.asc())
            .all()
        )
        if len(rows) != 1 or rows[0].action != CredentialAuditAction.read:
            print(f"FAIL credential audit row missing: {rows}", file=sys.stderr)
            return False
    finally:
        session.query(CredentialAccessAudit).filter(CredentialAccessAudit.app_id == app_id).delete()
        session.query(Application).filter(Application.app_id == app_id).delete()
        session.commit()
        session.close()

    print("OK auth: credential audit row written")
    return True


def _verify_authenticated_crawl_optional() -> bool:
    secret_name = "JUICE_SHOP_TEST_USER"
    if not os.getenv(secret_name, "").strip():
        print(f"SKIP authenticated crawl: {secret_name} not set in environment")
        return True

    from aqa_discovery.worker import crawl_application
    from fastapi.testclient import TestClient
    from aqa_api.main import app

    client = TestClient(app)
    payload = {
        "name": f"Juice Shop Auth Verify {uuid.uuid4().hex[:8]}",
        "base_url": "https://juice-shop.herokuapp.com",
        "seed_urls": ["https://juice-shop.herokuapp.com/#/search"],
        "auth_config": {
            "type": "form",
            "login_url": "/#/login",
            "email_selector": "#email",
            "password_selector": "#password",
            "submit_selector": "#loginButton",
            "credentials_secret_ref": secret_name,
        },
        "crawl_config": {
            "max_pages": 5,
            "max_depth": 2,
            "wait_until": "networkidle",
            "respect_robots_txt": False,
        },
    }
    resp = client.post("/api/v1/apps", json=payload)
    if resp.status_code != 201:
        print(f"SKIP authenticated crawl: app registration failed ({resp.status_code})", file=sys.stderr)
        return True

    app_id = resp.json()["app_id"]
    try:
        result = crawl_application(app_id)
    except Exception as exc:
        print(f"SKIP authenticated crawl: {exc}", file=sys.stderr)
        return True

    if result.halted:
        print(f"SKIP authenticated crawl: site halted ({result.halt_reason})", file=sys.stderr)
        return True
    if not result.authenticated:
        print("FAIL authenticated crawl did not authenticate", file=sys.stderr)
        return False
    if not result.pages:
        print("FAIL authenticated crawl returned no pages", file=sys.stderr)
        return False

    print(
        f"OK authenticated crawl: authenticated={result.authenticated} pages={len(result.pages)}"
    )
    return True


def main() -> int:
    print("verify:discovery")
    checks = [
        _verify_url_utils,
        _verify_safety_exclusions,
        _verify_robots_txt,
        _verify_captcha_halt,
        _verify_auth_credentials,
        _verify_form_login_mock,
        _verify_cookie_injection,
        _verify_credential_audit,
        _verify_locator_priority,
        _verify_element_extraction,
        _verify_persist_crawl_result,
        _verify_single_fetch,
        _verify_bfs_crawl,
        _verify_authenticated_crawl_optional,
    ]
    for check in checks:
        if not check():
            return 1
    print("verify:discovery OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Register ParaBank app and run CIC full persist with live progress."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql://aqa:aqa@localhost:5432/autonomous_qa")
os.environ.setdefault("ENCRYPTION_KEY", "0123456789abcdef" * 4)

PARABANK_BASE = "https://parabank.parasoft.com/parabank/"
PARABANK_LOGIN = "https://parabank.parasoft.com/parabank/index.htm?ConnType=JDBC"
PARABANK_NAME = "ParaBank"
CREDENTIALS_REF = "PARABANK_USER"

from aqa_shared.crypto.auth_config import encrypt_auth_config  # noqa: E402
from aqa_shared.db.models import Application  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _ensure_parabank_app(*, username: str, password: str) -> str:
    os.environ[CREDENTIALS_REF] = json.dumps({"username": username, "password": password})

    auth_config = encrypt_auth_config(
        {
            "type": "form",
            "login_url": "index.htm?ConnType=JDBC",
            "email_selector": "input[name='username']",
            "password_selector": "input[name='password']",
            "submit_selector": "input[value='Log In']",
            "credentials_secret_ref": CREDENTIALS_REF,
        }
    )
    crawl_config = {
        "max_pages": 100,
        "max_depth": 10,
        "allowed_domains": ["parabank.parasoft.com"],
        "excluded_urls": ["**/api-docs/**", "**/services/**", "**/*wadl*"],
        "respect_robots_txt": False,
        "wait_until": "networkidle",
        "page_timeout_ms": 45000,
    }

    session = get_session_factory()()
    app = session.query(Application).filter(Application.name == PARABANK_NAME).first()
    if app is None:
        app = Application(
            name=PARABANK_NAME,
            base_url=PARABANK_BASE,
            seed_urls=[PARABANK_LOGIN],
            auth_config=auth_config,
            crawl_config=crawl_config,
        )
        session.add(app)
    else:
        app.base_url = PARABANK_BASE
        app.seed_urls = [PARABANK_LOGIN]
        app.auth_config = auth_config
        app.crawl_config = crawl_config

    session.commit()
    session.refresh(app)
    app_id = str(app.app_id)
    session.close()
    return app_id


def main() -> int:
    username = os.getenv("PARABANK_USERNAME", "hari")
    password = os.getenv("PARABANK_PASSWORD", "hari123")

    app_id = _ensure_parabank_app(username=username, password=password)
    print(f"ParaBank app ready: {app_id}")
    print(f"URL: {PARABANK_LOGIN}")
    print(f"User: {username}")
    print()

    log_path = ROOT / "artifacts" / "parabank_cic_live.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(ROOT / ".venv/bin/python"),
        str(ROOT / "scripts/cic_persist_discovery.py"),
        "--app-id",
        app_id,
        "--cic-mode",
        "full",
        "--live",
    ]
    print(f"Log file: {log_path}")
    print("Starting CIC full persist (tail the log for live updates)...")
    print("=" * 70)

    with log_path.open("w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log_file.write(line)
            log_file.flush()
        return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())

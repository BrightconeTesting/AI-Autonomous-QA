#!/usr/bin/env python3
"""Register Nykaa app and run CIC full persist with live progress (guest, no login)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql://aqa:aqa@localhost:5432/autonomous_qa")
os.environ.setdefault("ENCRYPTION_KEY", "0123456789abcdef" * 4)

NYKAA_BASE = "https://www.nykaa.com/"
NYKAA_NAME = "Nykaa"
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

from aqa_shared.db.models import Application  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _ensure_nykaa_app() -> str:
    crawl_config = {
        "max_pages": 100,
        "max_depth": 10,
        "allowed_domains": ["www.nykaa.com", "nykaa.com"],
        "excluded_urls": [
            "**/cart/**",
            "**/checkout/**",
            "**/gcheckout/**",
            "**/auth/**",
            "**/login/**",
        ],
        "respect_robots_txt": False,
        "wait_until": "domcontentloaded",
        "page_timeout_ms": 60000,
        "max_scroll_iterations": 15,
        "browser_channel": "chrome",
        "user_agent": CHROME_USER_AGENT,
        "locale": "en-IN",
        "viewport_width": 1440,
        "viewport_height": 900,
    }

    session = get_session_factory()()
    app = session.query(Application).filter(Application.name == NYKAA_NAME).first()
    if app is None:
        app = Application(
            name=NYKAA_NAME,
            base_url=NYKAA_BASE,
            seed_urls=[NYKAA_BASE],
            auth_config=None,
            crawl_config=crawl_config,
        )
        session.add(app)
    else:
        app.base_url = NYKAA_BASE
        app.seed_urls = [NYKAA_BASE]
        app.auth_config = None
        app.crawl_config = crawl_config

    session.commit()
    session.refresh(app)
    app_id = str(app.app_id)
    session.close()
    return app_id


def main() -> int:
    app_id = _ensure_nykaa_app()
    print(f"Nykaa app ready: {app_id}")
    print(f"URL: {NYKAA_BASE}")
    print("Auth: none (guest crawl)")
    print("Limits: max_pages=100, max_depth=10, cic_mode=full")
    print()

    log_path = ROOT / "artifacts" / "nykaa_cic_live.log"
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
    print("Starting CIC full persist — tail the log for live updates:")
    print(f"  tail -f {log_path}")
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

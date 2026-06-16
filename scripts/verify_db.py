#!/usr/bin/env python3
"""Verify database connectivity, indexes, and basic CRUD."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from aqa_shared.db.models import Application
from aqa_shared.db.session import get_engine, get_session_factory

CRITICAL_INDEXES = [
    "idx_pipeline_runs_active",
    "idx_pages_app_url",
    "idx_test_scripts_version",
    "idx_test_runs_app_id",
]


def main() -> int:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public' AND indexname LIKE 'idx_%'
                ORDER BY indexname
                """
            )
        ).fetchall()
    index_names = [row[0] for row in rows]
    print("Index count:", len(index_names))
    print("Indexes:", ", ".join(index_names))

    exit_code = 0
    for name in CRITICAL_INDEXES:
        found = name in index_names
        print(f"{'✓' if found else '✗ MISSING'} {name}")
        if not found:
            exit_code = 1

    session = get_session_factory()()
    try:
        app = Application(name="Verify DB App", base_url="https://example.com")
        session.add(app)
        session.commit()
        session.refresh(app)
        print("Dummy Application created:", app.app_id)
        session.delete(app)
        session.commit()
        print("Dummy Application cleaned up")
    finally:
        session.close()

    return exit_code


if __name__ == "__main__":
    os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))
    sys.exit(main())

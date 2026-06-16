"""Load bundled JSON Schema files."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


@lru_cache
def load_schema(filename: str) -> dict:
    path = SCHEMA_DIR / filename
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)

"""FastAPI dependencies."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from aqa_shared.db.session import get_db as _get_db


def get_db() -> Generator[Session, None, None]:
    yield from _get_db()

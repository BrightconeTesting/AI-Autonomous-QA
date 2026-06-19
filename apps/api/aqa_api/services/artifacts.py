"""Artifact storage and streaming."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aqa_api.schemas.runs import ArtifactMetaResponse
from aqa_shared.db.models import Artifact


def artifact_storage_root() -> Path:
    return Path(os.getenv("ARTIFACT_STORAGE_PATH", "./artifacts")).resolve()


def get_artifact(db: Session, artifact_id: uuid.UUID) -> Artifact | None:
    return db.get(Artifact, artifact_id)


def artifact_meta(db: Session, artifact: Artifact) -> ArtifactMetaResponse:
    return ArtifactMetaResponse(
        id=artifact.id,
        type=artifact.type.value if hasattr(artifact.type, "value") else str(artifact.type),
        size_bytes=int(artifact.size_bytes or 0),
        testcase_id=None,
        run_id=artifact.run_id,
        created_at=artifact.created_at,
    )


def delete_artifact(db: Session, artifact: Artifact) -> None:
    path = Path(artifact.path)
    if path.is_file():
        path.unlink(missing_ok=True)
    db.delete(artifact)
    db.commit()


def storage_bytes_for_app(db: Session, app_id: uuid.UUID) -> int:
    from aqa_shared.db.models import TestRun

    total = db.scalar(
        select(func.coalesce(func.sum(Artifact.size_bytes), 0))
        .join(TestRun, TestRun.run_id == Artifact.run_id)
        .where(TestRun.app_id == app_id)
    )
    return int(total or 0)

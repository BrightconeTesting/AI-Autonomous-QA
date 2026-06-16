"""Initial schema — ported from Prisma migration 20260615114336_init."""

from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "20260615114336"
down_revision = None
branch_labels = None
depends_on = None

_INIT_SQL = Path(__file__).resolve().parents[1] / "sql" / "20260615114336_init.sql"


def upgrade() -> None:
    sql = _INIT_SQL.read_text(encoding="utf-8")
    conn = op.get_bind()
    conn.execute(sa.text(sql))


def downgrade() -> None:
    tables = [
        "credential_access_audit",
        "artifacts",
        "results",
        "test_scripts",
        "test_cases",
        "test_runs",
        "pipeline_runs",
        "elements",
        "pages",
        "flows",
        "applications",
    ]
    for table in tables:
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))

    enums = [
        "CredentialAuditAction",
        "ArtifactType",
        "PipelineStage",
        "PipelineStatus",
        "ResultOutcome",
        "TestRunStatus",
        "TestCaseStatus",
        "TestPriority",
        "FlowSource",
    ]
    for enum_name in enums:
        op.execute(sa.text(f'DROP TYPE IF EXISTS "{enum_name}" CASCADE'))

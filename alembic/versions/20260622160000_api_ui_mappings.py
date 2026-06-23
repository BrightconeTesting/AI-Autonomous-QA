"""Phase B2: api_ui_mappings table for API↔UI correlation."""

from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "20260622160000"
down_revision = "20260622140000"
branch_labels = None
depends_on = None

_MAPPING_SQL = Path(__file__).resolve().parents[1] / "sql" / "20260622160000_api_ui_mappings.sql"


def upgrade() -> None:
    sql = _MAPPING_SQL.read_text(encoding="utf-8")
    conn = op.get_bind()
    conn.execute(sa.text(sql))


def downgrade() -> None:
    op.execute(sa.text('DROP TABLE IF EXISTS "api_ui_mappings" CASCADE'))

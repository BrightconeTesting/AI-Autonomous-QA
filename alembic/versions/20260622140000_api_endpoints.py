"""Phase B: api_endpoints table for network/OpenAPI discovery."""

from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "20260622140000"
down_revision = "20260622120000"
branch_labels = None
depends_on = None

_API_SQL = Path(__file__).resolve().parents[1] / "sql" / "20260622140000_api_endpoints.sql"


def upgrade() -> None:
    sql = _API_SQL.read_text(encoding="utf-8")
    conn = op.get_bind()
    conn.execute(sa.text(sql))


def downgrade() -> None:
    op.execute(sa.text('DROP TABLE IF EXISTS "api_endpoints" CASCADE'))

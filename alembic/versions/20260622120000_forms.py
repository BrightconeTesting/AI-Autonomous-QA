"""Phase A: forms table for crawl-time form detection."""

from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "20260622120000"
down_revision = "20260618120000"
branch_labels = None
depends_on = None

_FORMS_SQL = Path(__file__).resolve().parents[1] / "sql" / "20260622120000_forms.sql"


def upgrade() -> None:
    sql = _FORMS_SQL.read_text(encoding="utf-8")
    conn = op.get_bind()
    conn.execute(sa.text(sql))


def downgrade() -> None:
    op.execute(sa.text('DROP TABLE IF EXISTS "forms" CASCADE'))

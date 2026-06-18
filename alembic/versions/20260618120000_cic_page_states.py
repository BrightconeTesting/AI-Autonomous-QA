"""CIC Phase 1: page_states, state_transitions, page_discoveries."""

from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "20260618120000"
down_revision = "20260615114336"
branch_labels = None
depends_on = None

_CIC_SQL = Path(__file__).resolve().parents[1] / "sql" / "20260618120000_cic_page_states.sql"


def upgrade() -> None:
    sql = _CIC_SQL.read_text(encoding="utf-8")
    conn = op.get_bind()
    conn.execute(sa.text(sql))


def downgrade() -> None:
    op.execute(sa.text('ALTER TABLE "elements" DROP CONSTRAINT IF EXISTS "elements_state_id_fkey"'))
    op.execute(sa.text('ALTER TABLE "elements" DROP COLUMN IF EXISTS "state_id"'))
    op.execute(sa.text('DROP TABLE IF EXISTS "page_discoveries" CASCADE'))
    op.execute(sa.text('DROP TABLE IF EXISTS "state_transitions" CASCADE'))
    op.execute(sa.text('DROP TABLE IF EXISTS "page_states" CASCADE'))

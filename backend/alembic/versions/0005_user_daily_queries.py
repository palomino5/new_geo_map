"""user: afegir comptador de consultes diàries

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-08
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE core."user"
            ADD COLUMN daily_queries_used       INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN daily_queries_reset_date DATE;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE core."user"
            DROP COLUMN daily_queries_used,
            DROP COLUMN daily_queries_reset_date;
    """)

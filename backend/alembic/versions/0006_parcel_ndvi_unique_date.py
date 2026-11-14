"""parcel_ndvi: UNIQUE (parcel_id, date) + registre d'importacions NDVI

- Elimina duplicats i afegeix UNIQUE (parcel_id, date), necessari per a l'upsert
  de import_ndvi_results.py (ON CONFLICT).
- Crea analytics.ndvi_import: quina versió (processed_at) de cada data publicada
  per GitHub Actions s'ha importat, per detectar dates noves o reprocessades.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-14
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Conserva el registre més recent (id més alt) de cada (parcel_id, date)
    op.execute("""
        DELETE FROM analytics.parcel_ndvi a
        USING analytics.parcel_ndvi b
        WHERE a.parcel_id = b.parcel_id
          AND a.date = b.date
          AND a.id < b.id;
    """)
    op.execute("""
        ALTER TABLE analytics.parcel_ndvi
            ADD CONSTRAINT uq_parcel_ndvi_parcel_date UNIQUE (parcel_id, date);
    """)
    op.execute("""
        CREATE TABLE analytics.ndvi_import (
            date          DATE PRIMARY KEY,
            processed_at  TEXT NOT NULL,
            rows_imported INTEGER NOT NULL,
            imported_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE analytics.ndvi_import;")
    op.execute("""
        ALTER TABLE analytics.parcel_ndvi
            DROP CONSTRAINT uq_parcel_ndvi_parcel_date;
    """)

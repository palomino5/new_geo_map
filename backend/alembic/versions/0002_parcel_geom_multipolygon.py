"""parcel geom: Polygon → MultiPolygon

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23
"""
from alembic import op
import geoalchemy2

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE core.parcel
        ALTER COLUMN geom TYPE geometry(MultiPolygon, 4326)
        USING ST_Multi(geom)
    """)
    op.execute("DROP INDEX IF EXISTS idx_core_parcel_geom")
    op.execute("CREATE INDEX idx_core_parcel_geom ON core.parcel USING GIST (geom)")


def downgrade() -> None:
    op.execute("""
        ALTER TABLE core.parcel
        ALTER COLUMN geom TYPE geometry(Polygon, 4326)
        USING ST_GeometryN(geom, 1)
    """)

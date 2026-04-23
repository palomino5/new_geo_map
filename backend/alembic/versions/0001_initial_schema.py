"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions i schemas
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis_topology")
    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    op.execute("CREATE SCHEMA IF NOT EXISTS raw")
    op.execute("CREATE SCHEMA IF NOT EXISTS analytics")

    # core.municipality
    op.create_table(
        "municipality",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code_ine", sa.String(10), nullable=False, unique=True),
        sa.Column("province", sa.String(100)),
        sa.Column("area_km2", sa.Float()),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry("MULTIPOLYGON", srid=4326, spatial_index=True),
            nullable=False,
        ),
        schema="core",
    )
    op.create_index("ix_core_municipality_code_ine", "municipality", ["code_ine"], schema="core")

    # core.parcel
    op.create_table(
        "parcel",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ref_catastral", sa.String(20), nullable=False, unique=True),
        sa.Column(
            "municipality_id",
            sa.Integer(),
            sa.ForeignKey("core.municipality.id"),
            nullable=False,
        ),
        sa.Column("superficie_ha", sa.Float()),
        sa.Column("uso_sigpac", sa.String(10)),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry("POLYGON", srid=4326, spatial_index=True),
            nullable=False,
        ),
        schema="core",
    )
    op.create_index("ix_core_parcel_ref_catastral", "parcel", ["ref_catastral"], schema="core")
    op.create_index("ix_core_parcel_municipality_id", "parcel", ["municipality_id"], schema="core")

    # analytics.parcel_ndvi
    op.create_table(
        "parcel_ndvi",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parcel_id", sa.Integer(), sa.ForeignKey("core.parcel.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("ndvi_mean", sa.Float()),
        sa.Column("ndvi_min", sa.Float()),
        sa.Column("ndvi_max", sa.Float()),
        sa.Column("ndvi_std", sa.Float()),
        sa.Column("cloud_cover_pct", sa.Float(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema="analytics",
    )
    op.create_index("ix_analytics_parcel_ndvi_parcel_id", "parcel_ndvi", ["parcel_id"], schema="analytics")
    op.create_index("ix_analytics_parcel_ndvi_date", "parcel_ndvi", ["date"], schema="analytics")

    # analytics.parcel_status
    # sa.Enum amb create_type=True (default) gestiona el CREATE TYPE automàticament
    op.create_table(
        "parcel_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parcel_id", sa.Integer(), sa.ForeignKey("core.parcel.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("activa", "abandonada", "desconeguda", name="parcel_status_enum", schema="analytics"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), server_default="0"),
        sa.Column("algoritmo_version", sa.String(20), server_default="'v1.0'"),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema="analytics",
    )
    op.create_index("ix_analytics_parcel_status_parcel_id", "parcel_status", ["parcel_id"], schema="analytics")
    op.create_index("ix_analytics_parcel_status_calculated_at", "parcel_status", ["calculated_at"], schema="analytics")

    # Vista: parcel_status_latest
    op.execute("""
        CREATE VIEW analytics.parcel_status_latest AS
        SELECT DISTINCT ON (parcel_id)
            id, parcel_id, status, confidence, algoritmo_version, calculated_at
        FROM analytics.parcel_status
        ORDER BY parcel_id, calculated_at DESC
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS analytics.parcel_status_latest")
    op.drop_table("parcel_status", schema="analytics")
    op.execute("DROP TYPE IF EXISTS analytics.parcel_status_enum")
    op.drop_table("parcel_ndvi", schema="analytics")
    op.drop_table("parcel", schema="core")
    op.drop_table("municipality", schema="core")
    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE")
    op.execute("DROP SCHEMA IF EXISTS raw CASCADE")
    op.execute("DROP SCHEMA IF EXISTS core CASCADE")

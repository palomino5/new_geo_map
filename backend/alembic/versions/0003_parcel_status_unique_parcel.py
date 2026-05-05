"""parcel_status: afegir UNIQUE constraint a parcel_id

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-28
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM analytics.parcel_status")
    op.create_unique_constraint(
        "uq_parcel_status_parcel_id",
        "parcel_status",
        ["parcel_id"],
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_parcel_status_parcel_id",
        "parcel_status",
        schema="analytics",
    )

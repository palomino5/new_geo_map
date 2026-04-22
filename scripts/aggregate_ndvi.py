"""
Agrega i neteja els registres NDVI: elimina duplicats i afegeix estadístiques de cobertura de núvols.
Ús: python scripts/aggregate_ndvi.py
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.app.core.config import settings  # noqa: E402


def aggregate() -> None:
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        # Elimina duplicats (conserva el primer inserit)
        result = session.execute(text("""
            DELETE FROM analytics.parcel_ndvi
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM analytics.parcel_ndvi
                GROUP BY parcel_id, date
            )
        """))
        deleted = result.rowcount
        session.commit()
        print(f"Duplicats eliminats: {deleted}")

        # Estadístiques resum
        stats = session.execute(text("""
            SELECT
                COUNT(*) as total_records,
                COUNT(DISTINCT parcel_id) as parcels_with_ndvi,
                MIN(date) as earliest_date,
                MAX(date) as latest_date,
                AVG(ndvi_mean) as avg_ndvi
            FROM analytics.parcel_ndvi
        """)).fetchone()

        if stats:
            print(f"Total registres: {stats[0]}")
            print(f"Parcel·les amb NDVI: {stats[1]}")
            print(f"Rang de dates: {stats[2]} – {stats[3]}")
            print(f"NDVI mig global: {stats[4]:.4f}" if stats[4] else "Sense dades NDVI")


if __name__ == "__main__":
    aggregate()

"""
Calcula l'índex NDVI per parcel·la a partir de les bandes B04 i B08 de Sentinel-2.
Ús: python scripts/calculate_ndvi.py --date 2024-03-15
     python scripts/calculate_ndvi.py  # processa totes les dates pendents
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.mask import mask as rio_mask
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.app.core.config import settings  # noqa: E402

DATA_DIR = Path("data/sentinel2")
NODATA = -9999.0


def compute_ndvi(b04_path: Path, b08_path: Path, geom_geojson: dict) -> dict | None:
    with rasterio.open(b04_path) as b04_src, rasterio.open(b08_path) as b08_src:
        try:
            red, _ = rio_mask(b04_src, [geom_geojson], crop=True, nodata=NODATA)
            nir, _ = rio_mask(b08_src, [geom_geojson], crop=True, nodata=NODATA)
        except Exception:
            return None

        red = red.astype(float)
        nir = nir.astype(float)
        red[red == NODATA] = np.nan
        nir[nir == NODATA] = np.nan

        denom = nir + red
        with np.errstate(invalid="ignore", divide="ignore"):
            ndvi = np.where(denom != 0, (nir - red) / denom, np.nan)

        valid = ndvi[~np.isnan(ndvi)]
        if valid.size == 0:
            return None

        return {
            "ndvi_mean": float(np.mean(valid)),
            "ndvi_min": float(np.min(valid)),
            "ndvi_max": float(np.max(valid)),
            "ndvi_std": float(np.std(valid)),
        }


def process_date(date_str: str, session: Session) -> None:
    date_dir = DATA_DIR / date_str
    b04_files = list(date_dir.glob("*B04*.tif"))
    b08_files = list(date_dir.glob("*B08*.tif"))

    if not b04_files or not b08_files:
        print(f"  No s'han trobat bandes per {date_str}")
        return

    b04_path = b04_files[0]
    b08_path = b08_files[0]
    print(f"  Processant {date_str}: {b04_path.name}")

    parcels = session.execute(
        text("SELECT id, ST_AsGeoJSON(geom) as geojson FROM core.parcel")
    ).fetchall()

    inserted = 0
    for parcel_id, geojson_str in parcels:
        import json
        geom = json.loads(geojson_str)
        result = compute_ndvi(b04_path, b08_path, geom)
        if result is None:
            continue

        session.execute(
            text("""
                INSERT INTO analytics.parcel_ndvi (parcel_id, date, ndvi_mean, ndvi_min, ndvi_max, ndvi_std)
                VALUES (:parcel_id, :date, :ndvi_mean, :ndvi_min, :ndvi_max, :ndvi_std)
                ON CONFLICT DO NOTHING
            """),
            {"parcel_id": parcel_id, "date": date_str, **result},
        )
        inserted += 1

    session.commit()
    print(f"  {inserted} parcel·les actualitzades per {date_str}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calcula NDVI per parcel·la")
    parser.add_argument("--date", help="Data YYYY-MM-DD (ometre per processar totes)")
    args = parser.parse_args()

    engine = create_engine(settings.database_url)

    if args.date:
        dates = [args.date]
    else:
        dates = sorted(d.name for d in DATA_DIR.iterdir() if d.is_dir())

    with Session(engine) as session:
        for date_str in dates:
            print(f"Processant {date_str}...")
            process_date(date_str, session)

    print("Càlcul NDVI completat.")

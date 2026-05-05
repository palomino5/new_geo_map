"""
Calcula l'índex NDVI per parcel·la a partir de les bandes B04 i B08 de Sentinel-2.
Usa rasterstats.zonal_stats() per processar totes les parcel·les en una sola passada.
Ús: python scripts/calculate_ndvi.py --date 2024-03-15
     python scripts/calculate_ndvi.py  # processa totes les dates pendents
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterstats import zonal_stats
from shapely.geometry import mapping, shape
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings  # noqa: E402

DATA_DIR = Path("data/sentinel2")
BATCH_SIZE = 5000


def reproject_geojson(geom_dict: dict, transformer: Transformer) -> dict:
    """Reprojecta una geometria GeoJSON usant un Transformer de pyproj."""
    geom = shape(geom_dict)
    reprojected = type(geom)(
        [
            [
                [transformer.transform(y, x) for x, y in ring.coords]
                for ring in polygon.exterior.coords and [polygon.exterior] + list(polygon.interiors)
            ]
            for polygon in (geom.geoms if hasattr(geom, 'geoms') else [geom])
        ]
    )
    return mapping(reprojected)


def reproject_geometry(geom_dict: dict, transformer: Transformer) -> dict:
    """Reprojecta qualsevol geometria GeoJSON (Polygon o MultiPolygon)."""
    from shapely.ops import transform as shapely_transform
    geom = shape(geom_dict)
    reprojected = shapely_transform(
        lambda x, y: transformer.transform(x, y),  # lon,lat → x_utm,y_utm
        geom
    )
    return mapping(reprojected)


def process_date(date_str: str, session: Session) -> None:
    date_dir = DATA_DIR / date_str
    b04_files = list(date_dir.glob("*B04*.tif"))
    b08_files = list(date_dir.glob("*B08*.tif"))

    if not b04_files or not b08_files:
        print(f"  No s'han trobat bandes per {date_str}")
        return

    # Agrupa fitxers per tile: {tile_id: (b04_path, b08_path)}
    # Suporta tant el format nou ({data}_{tile}_B04.tif) com l'antic ({data}_B04.tif)
    tiles = {}
    for b04 in b04_files:
        name = b04.stem  # ex: "2024-03-02_T31TBH_B04"
        parts = name.split("_")
        tile_id = parts[1] if len(parts) >= 3 else "UNKNOWN"
        b08_candidates = [f for f in b08_files if tile_id in f.name or (tile_id == "UNKNOWN")]
        if b08_candidates:
            tiles[tile_id] = (b04, b08_candidates[0])

    if not tiles:
        print(f"  No s'han pogut aparellar bandes B04/B08 per {date_str}")
        return

    print(f"  Tiles disponibles: {list(tiles.keys())}")

    # Carrega bounding box dels tiles per filtrar parcel·les
    tile_bounds_4326 = []
    for tile_id, (b04, b08) in tiles.items():
        with rasterio.open(str(b04)) as src:
            raster_crs_epsg = src.crs.to_epsg()
            b = src.bounds
        t_inv = Transformer.from_crs(f"EPSG:{raster_crs_epsg}", "EPSG:4326", always_xy=True)
        lon_min, lat_min = t_inv.transform(b.left, b.bottom)
        lon_max, lat_max = t_inv.transform(b.right, b.top)
        tile_bounds_4326.append((tile_id, lon_min, lat_min, lon_max, lat_max))
        print(f"  Tile {tile_id}: lat {lat_min:.2f}–{lat_max:.2f}, lon {lon_min:.2f}–{lon_max:.2f}")

    total_inserted = 0

    for tile_id, (b04_file, b08_file) in tiles.items():
        b04_path = str(b04_file)
        b08_path = str(b08_file)

        with rasterio.open(b04_path) as src:
            raster_crs_epsg = src.crs.to_epsg()
            rb = src.bounds

        transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{raster_crs_epsg}", always_xy=True)

        # Converteix bounds del raster a 4326 per filtrar parcel·les
        t_inv = Transformer.from_crs(f"EPSG:{raster_crs_epsg}", "EPSG:4326", always_xy=True)
        lon_min, lat_min = t_inv.transform(rb.left, rb.bottom)
        lon_max, lat_max = t_inv.transform(rb.right, rb.top)

        # Compta parcel·les dins del tile
        count_in_tile = session.execute(
            text("""
                SELECT COUNT(*) FROM core.parcel
                WHERE ST_Intersects(geom, ST_MakeEnvelope(:lon_min, :lat_min, :lon_max, :lat_max, 4326))
            """),
            {"lon_min": lon_min, "lat_min": lat_min, "lon_max": lon_max, "lat_max": lat_max},
        ).scalar()

        print(f"  Tile {tile_id}: {count_in_tile} parcel·les dins del tile")
        if count_in_tile == 0:
            continue

        # Comprova si aquest tile ja s'ha processat completament
        existing = session.execute(
            text("""
                SELECT COUNT(*) FROM analytics.parcel_ndvi pn
                JOIN core.parcel p ON p.id = pn.parcel_id
                WHERE pn.date = :date
                AND ST_Intersects(p.geom, ST_MakeEnvelope(:lon_min, :lat_min, :lon_max, :lat_max, 4326))
            """),
            {"date": date_str, "lon_min": lon_min, "lat_min": lat_min,
             "lon_max": lon_max, "lat_max": lat_max},
        ).scalar()
        if existing and existing >= count_in_tile * 0.95:
            print(f"  Tile {tile_id} ja processat ({existing}/{count_in_tile} parcel·les). Saltant.")
            total_inserted += existing
            continue
        if existing and existing > 0:
            print(f"  Tile {tile_id} processat parcialment ({existing}/{count_in_tile}). Reprocessant.")

        inserted = 0
        offset = 0

        while offset < count_in_tile:
            rows = session.execute(
                text("""
                    SELECT id, ST_AsGeoJSON(geom) as geojson
                    FROM core.parcel
                    WHERE ST_Intersects(geom, ST_MakeEnvelope(:lon_min, :lat_min, :lon_max, :lat_max, 4326))
                    ORDER BY id
                    LIMIT :limit OFFSET :offset
                """),
                {"lon_min": lon_min, "lat_min": lat_min, "lon_max": lon_max, "lat_max": lat_max,
                 "limit": BATCH_SIZE, "offset": offset},
            ).fetchall()

            if not rows:
                break

            geojsons = []
            for r in rows:
                geom = json.loads(r.geojson)
                geom = reproject_geometry(geom, transformer)
                geojsons.append({"type": "Feature", "geometry": geom, "properties": {}})
            parcel_ids = [r.id for r in rows]

            stats_b04 = zonal_stats(geojsons, b04_path, stats=["mean"], nodata=-9999)
            stats_b08 = zonal_stats(geojsons, b08_path, stats=["mean", "min", "max", "std"], nodata=-9999)

            batch_data = []
            for pid, s04, s08 in zip(parcel_ids, stats_b04, stats_b08):
                red = s04.get("mean")
                nir_mean = s08.get("mean")
                nir_min = s08.get("min")
                nir_max = s08.get("max")

                if red is None or nir_mean is None or (red + nir_mean) == 0:
                    continue

                ndvi_mean = (nir_mean - red) / (nir_mean + red)
                ndvi_min = (nir_min - red) / (nir_min + red) if nir_min is not None else ndvi_mean
                ndvi_max = (nir_max - red) / (nir_max + red) if nir_max is not None else ndvi_mean
                ndvi_std = float(s08.get("std") or 0) / max(abs(nir_mean), 1)

                batch_data.append({
                    "parcel_id": pid, "date": date_str,
                    "ndvi_mean": round(float(ndvi_mean), 4),
                    "ndvi_min": round(float(ndvi_min), 4),
                    "ndvi_max": round(float(ndvi_max), 4),
                    "ndvi_std": round(float(ndvi_std), 4),
                })

            if batch_data:
                session.execute(
                    text("""
                        INSERT INTO analytics.parcel_ndvi
                            (parcel_id, date, ndvi_mean, ndvi_min, ndvi_max, ndvi_std)
                        VALUES (:parcel_id, :date, :ndvi_mean, :ndvi_min, :ndvi_max, :ndvi_std)
                        ON CONFLICT DO NOTHING
                    """),
                    batch_data,
                )
                session.commit()
                inserted += len(batch_data)

            offset += BATCH_SIZE
            print(f"    {min(offset, count_in_tile)}/{count_in_tile} processades, {inserted} amb NDVI...")

        total_inserted += inserted
        print(f"  Tile {tile_id} completat: {inserted} parcel·les amb NDVI")

    print(f"  Completat {date_str}: {total_inserted} parcel·les amb NDVI en total")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calcula NDVI per parcel·la")
    parser.add_argument("--date", help="Data YYYY-MM-DD (ometre per processar totes)")
    args = parser.parse_args()

    engine = create_engine(settings.database_url)

    if args.date:
        dates = [args.date]
    else:
        dates = sorted(d.name for d in DATA_DIR.iterdir() if d.is_dir())

    print(f"Dates a processar: {dates}")

    with Session(engine) as session:
        for date_str in dates:
            print(f"\nProcessant {date_str}...")
            process_date(date_str, session)

    print("\nCàlcul NDVI completat.")

"""
Importa dades SIGPAC (usos agrícoles) i actualitza uso_sigpac a core.parcel.
Ús: python scripts/import_sigpac.py --input data/imports/sigpac_cat.shp
"""

import argparse
import sys
import os

import geopandas as gpd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.app.core.config import settings  # noqa: E402

USO_COLS = ["USO_SIGPAC", "uso_sigpac", "USO", "uso", "CODIUSO"]
REF_COLS = ["REFCAT", "refcat", "REF_CATASTRAL"]
BATCH_SIZE = 1000


def resolve_col(gdf: gpd.GeoDataFrame, aliases: list[str]) -> str | None:
    for alias in aliases:
        if alias in gdf.columns:
            return alias
    return None


def import_sigpac(input_path: str) -> None:
    print(f"Llegint {input_path}...")
    gdf = gpd.read_file(input_path)
    gdf = gdf.to_crs(epsg=4326)

    uso_col = resolve_col(gdf, USO_COLS)
    ref_col = resolve_col(gdf, REF_COLS)

    if not uso_col:
        print(f"ERROR: No s'ha trobat la columna d'ús SIGPAC. Columnes: {list(gdf.columns)}")
        sys.exit(1)

    engine = create_engine(settings.database_url)
    updated = 0

    with Session(engine) as session:
        for i, (_, row) in enumerate(gdf.iterrows()):
            uso = str(row[uso_col]).strip()[:10] if row[uso_col] else None
            if not uso:
                continue

            if ref_col and row[ref_col]:
                # Actualització per referència catastral directa
                ref_cat = str(row[ref_col]).strip()[:20]
                session.execute(
                    text("UPDATE core.parcel SET uso_sigpac = :uso WHERE ref_catastral = :ref"),
                    {"uso": uso, "ref": ref_cat},
                )
            else:
                # Actualització per intersecció espacial
                geom_wkt = row.geometry.wkt
                session.execute(
                    text("""
                        UPDATE core.parcel
                        SET uso_sigpac = :uso
                        WHERE ST_Intersects(geom, ST_GeomFromText(:geom, 4326))
                          AND uso_sigpac IS NULL
                    """),
                    {"uso": uso, "geom": geom_wkt},
                )

            updated += 1
            if updated % BATCH_SIZE == 0:
                session.commit()
                print(f"  {updated} registres processats...")

        session.commit()

    print(f"Import SIGPAC completat: {updated} registres processats.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importa usos SIGPAC")
    parser.add_argument("--input", required=True, help="Ruta al fitxer SHP")
    args = parser.parse_args()
    import_sigpac(args.input)

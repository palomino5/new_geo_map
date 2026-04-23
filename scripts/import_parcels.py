"""
Importa parcel·les catastrals rústiques a core.parcel.
Accepta fitxers SHP o GML del Catastro amb la referència catastral de 20 caràcters.
Ús: python scripts/import_parcels.py --input data/imports/parceles.shp --municipality-code 080193
"""

import argparse
import sys
import os

import geopandas as gpd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings  # noqa: E402

REF_CATASTRAL_COLS = ["REFCAT", "refcat", "REF_CATASTRAL", "ref_catastral", "LOCALID"]
SUPERFICIE_COLS = ["SUPERFICIE", "sup_m2", "AREA", "area"]
BATCH_SIZE = 500


def resolve_col(gdf: gpd.GeoDataFrame, aliases: list[str]) -> str | None:
    for alias in aliases:
        if alias in gdf.columns:
            return alias
    return None


def import_parcels(input_path: str, municipality_code: str | None) -> None:
    print(f"Llegint {input_path}...")
    gdf = gpd.read_file(input_path)
    gdf = gdf.to_crs(epsg=4326)
    gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid]

    ref_col = resolve_col(gdf, REF_CATASTRAL_COLS)
    sup_col = resolve_col(gdf, SUPERFICIE_COLS)

    if not ref_col:
        print(f"ERROR: No s'ha trobat la columna de referència catastral. Columnes: {list(gdf.columns)}")
        sys.exit(1)

    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        # Obtenir municipality_id
        muni_id: int | None = None
        if municipality_code:
            row = session.execute(
                text("SELECT id FROM core.municipality WHERE code_ine = :code"),
                {"code": municipality_code.zfill(6)},
            ).fetchone()
            if not row:
                print(f"ERROR: Municipi amb codi {municipality_code} no trobat.")
                sys.exit(1)
            muni_id = row[0]

        inserted = 0
        updated = 0
        batch = []

        for _, row in gdf.iterrows():
            ref_cat = str(row[ref_col]).strip()[:20]
            if not ref_cat:
                continue

            sup_m2 = float(row[sup_col]) if sup_col and row[sup_col] else None
            sup_ha = sup_m2 / 10_000 if sup_m2 else None
            geom_wkt = row.geometry.wkt

            batch.append({
                "ref_catastral": ref_cat,
                "municipality_id": muni_id,
                "superficie_ha": sup_ha,
                "geom": geom_wkt,
            })

            if len(batch) >= BATCH_SIZE:
                i, u = _flush_batch(session, batch)
                inserted += i
                updated += u
                batch = []

        if batch:
            i, u = _flush_batch(session, batch)
            inserted += i
            updated += u

        session.commit()

    print(f"Import completat: {inserted} noves, {updated} actualitzades.")


def _flush_batch(session: Session, batch: list[dict]) -> tuple[int, int]:
    inserted = updated = 0
    for item in batch:
        result = session.execute(
            text("""
                INSERT INTO core.parcel (ref_catastral, municipality_id, superficie_ha, geom)
                VALUES (:ref_catastral, :municipality_id, :superficie_ha, ST_GeomFromText(:geom, 4326))
                ON CONFLICT (ref_catastral) DO UPDATE SET
                    municipality_id = COALESCE(EXCLUDED.municipality_id, core.parcel.municipality_id),
                    superficie_ha = EXCLUDED.superficie_ha,
                    geom = EXCLUDED.geom
                RETURNING (xmax = 0) AS inserted
            """),
            item,
        )
        row = result.fetchone()
        if row and row[0]:
            inserted += 1
        else:
            updated += 1
    return inserted, updated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importa parcel·les catastrals rústiques")
    parser.add_argument("--input", required=True, help="Ruta al fitxer SHP o GML")
    parser.add_argument("--municipality-code", help="Codi INE del municipi (opcional)")
    args = parser.parse_args()
    import_parcels(args.input, args.municipality_code)

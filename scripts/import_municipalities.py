"""
Importa els límits administratius dels municipis de Catalunya a core.municipality.
Accepta fitxers SHP o GeoJSON amb les columnes: CODIMUNI (o CODIGOINE), NOMMUNI (o NOM).
Ús: python scripts/import_municipalities.py --input data/imports/municipis.shp
"""

import argparse
import sys
import os

import geopandas as gpd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings  # noqa: E402


COLUMN_ALIASES = {
    "code_ine": ["CODIMUNI", "CODIGOINE", "INE", "cod_ine", "codi_mun"],
    "name": ["NOMMUNI", "NOM", "nombre", "nom_muni", "NOMBRE"],
    "province": ["NOMPROV", "provincia", "PROVINCIA", "NOMPROVINCIA"],
}


def resolve_col(gdf: gpd.GeoDataFrame, aliases: list[str]) -> str | None:
    for alias in aliases:
        if alias in gdf.columns:
            return alias
    return None


def import_municipalities(input_path: str) -> None:
    print(f"Llegint {input_path}...")
    gdf = gpd.read_file(input_path)
    gdf = gdf.to_crs(epsg=4326)

    code_col = resolve_col(gdf, COLUMN_ALIASES["code_ine"])
    name_col = resolve_col(gdf, COLUMN_ALIASES["name"])
    province_col = resolve_col(gdf, COLUMN_ALIASES["province"])

    if not code_col or not name_col:
        print(f"ERROR: No s'han trobat les columnes necessàries. Columnes disponibles: {list(gdf.columns)}")
        sys.exit(1)

    engine = create_engine(settings.database_url)
    inserted = 0
    updated = 0

    with Session(engine) as session:
        for _, row in gdf.iterrows():
            geom_wkt = row.geometry.wkt
            code_ine = str(row[code_col]).zfill(6)
            name = str(row[name_col])
            province = str(row[province_col]) if province_col and row[province_col] else None
            area_km2 = float(row.geometry.area * (111_320 ** 2) / 1_000_000)  # approx

            result = session.execute(
                text("""
                    INSERT INTO core.municipality (name, code_ine, province, area_km2, geom)
                    VALUES (:name, :code_ine, :province, :area_km2, ST_GeomFromText(:geom, 4326))
                    ON CONFLICT (code_ine) DO UPDATE SET
                        name = EXCLUDED.name,
                        province = EXCLUDED.province,
                        area_km2 = EXCLUDED.area_km2,
                        geom = EXCLUDED.geom
                    RETURNING (xmax = 0) AS inserted
                """),
                {"name": name, "code_ine": code_ine, "province": province, "area_km2": area_km2, "geom": geom_wkt},
            )
            row_result = result.fetchone()
            if row_result and row_result[0]:
                inserted += 1
            else:
                updated += 1

        session.commit()

    print(f"Import completat: {inserted} nous, {updated} actualitzats.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importa municipis a core.municipality")
    parser.add_argument("--input", required=True, help="Ruta al fitxer SHP o GeoJSON")
    args = parser.parse_args()
    import_municipalities(args.input)

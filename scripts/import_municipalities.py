"""
Importa els límits administratius dels municipis a core.municipality.

Suporta dos formats:
  - CNIG/IGN INSPIRE (recintos_municipales_inspire_*.shp):
      columnes NAMEUNIT, NATCODE, CODNUT2, CODNUT3
  - ICGC / genèric:
      columnes CODIMUNI/CODIGOINE, NOMMUNI/NOM, NOMPROV

Ús:
  # Només Catalunya (recomanat amb fitxer CNIG):
  python scripts/import_municipalities.py --input data/imports/lineas_limite/SHP_ETRS89/recintos_municipales_inspire_peninbal_etrs89/recintos_municipales_inspire_peninbal_etrs89.shp --nuts2 ES51

  # Tot Espanya o format genèric:
  python scripts/import_municipalities.py --input data/imports/municipis.shp
"""

import argparse
import sys
import os

import geopandas as gpd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings  # noqa: E402

NUTS2_PROVINCE_NAMES = {
    "ES511": "Barcelona",
    "ES512": "Girona",
    "ES513": "Lleida",
    "ES514": "Tarragona",
}


def is_cnig_format(gdf: gpd.GeoDataFrame) -> bool:
    return "NATCODE" in gdf.columns and "NAMEUNIT" in gdf.columns


def extract_code_ine_cnig(natcode: str) -> str:
    # NATCODE format: 34090808001 → últims 5 dígits = codi INE (p.ex. 08001)
    return str(natcode).strip()[-5:]


def import_municipalities(input_path: str, nuts2_filter: str | None) -> None:
    print(f"Llegint {input_path}...")
    gdf = gpd.read_file(input_path)
    gdf = gdf.to_crs(epsg=4326)
    gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid]

    if is_cnig_format(gdf):
        print("Format detectat: CNIG/IGN INSPIRE")
        if nuts2_filter:
            gdf = gdf[gdf["CODNUT2"] == nuts2_filter]
            print(f"Filtrant per CODNUT2={nuts2_filter}: {len(gdf)} municipis")
        _import_cnig(gdf)
    else:
        print("Format detectat: genèric (ICGC/altre)")
        _import_generic(gdf)


def _import_cnig(gdf: gpd.GeoDataFrame) -> None:
    engine = create_engine(settings.database_url)
    inserted = updated = 0

    with Session(engine) as session:
        for _, row in gdf.iterrows():
            code_ine = extract_code_ine_cnig(row["NATCODE"])
            name = str(row["NAMEUNIT"])
            province = NUTS2_PROVINCE_NAMES.get(str(row.get("CODNUT3", "")))
            geom_wkt = row.geometry.wkt
            area_km2 = _approx_area_km2(row.geometry)

            row_result = session.execute(
                text("""
                    INSERT INTO core.municipality (name, code_ine, province, area_km2, geom)
                    VALUES (:name, :code_ine, :province, :area_km2,
                            ST_Multi(ST_GeomFromText(:geom, 4326)))
                    ON CONFLICT (code_ine) DO UPDATE SET
                        name = EXCLUDED.name,
                        province = EXCLUDED.province,
                        area_km2 = EXCLUDED.area_km2,
                        geom = EXCLUDED.geom
                    RETURNING (xmax = 0) AS inserted
                """),
                {"name": name, "code_ine": code_ine, "province": province,
                 "area_km2": area_km2, "geom": geom_wkt},
            ).fetchone()

            if row_result and row_result[0]:
                inserted += 1
            else:
                updated += 1

            if (inserted + updated) % 100 == 0:
                print(f"  {inserted + updated} processats...")

        session.commit()

    print(f"Import completat: {inserted} nous, {updated} actualitzats.")


def _import_generic(gdf: gpd.GeoDataFrame) -> None:
    aliases = {
        "code_ine": ["CODIMUNI", "CODIGOINE", "INE", "cod_ine", "codi_mun"],
        "name":     ["NOMMUNI", "NOM", "nombre", "nom_muni", "NOMBRE"],
        "province": ["NOMPROV", "provincia", "PROVINCIA", "NOMPROVINCIA"],
    }

    def resolve(cols: list[str]) -> str | None:
        return next((c for c in cols if c in gdf.columns), None)

    code_col = resolve(aliases["code_ine"])
    name_col = resolve(aliases["name"])
    province_col = resolve(aliases["province"])

    if not code_col or not name_col:
        print(f"ERROR: columnes no trobades. Disponibles: {list(gdf.columns)}")
        sys.exit(1)

    engine = create_engine(settings.database_url)
    inserted = updated = 0

    with Session(engine) as session:
        for _, row in gdf.iterrows():
            code_ine = str(row[code_col]).zfill(6)
            name = str(row[name_col])
            province = str(row[province_col]) if province_col and row[province_col] else None
            geom_wkt = row.geometry.wkt
            area_km2 = _approx_area_km2(row.geometry)

            row_result = session.execute(
                text("""
                    INSERT INTO core.municipality (name, code_ine, province, area_km2, geom)
                    VALUES (:name, :code_ine, :province, :area_km2,
                            ST_Multi(ST_GeomFromText(:geom, 4326)))
                    ON CONFLICT (code_ine) DO UPDATE SET
                        name = EXCLUDED.name,
                        province = EXCLUDED.province,
                        area_km2 = EXCLUDED.area_km2,
                        geom = EXCLUDED.geom
                    RETURNING (xmax = 0) AS inserted
                """),
                {"name": name, "code_ine": code_ine, "province": province,
                 "area_km2": area_km2, "geom": geom_wkt},
            ).fetchone()

            if row_result and row_result[0]:
                inserted += 1
            else:
                updated += 1

        session.commit()

    print(f"Import completat: {inserted} nous, {updated} actualitzats.")


def _approx_area_km2(geom) -> float:
    # Aproximació en graus → km² (vàlid per Catalunya)
    return float(geom.area * (111_320 ** 2) / 1_000_000)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importa municipis a core.municipality")
    parser.add_argument("--input", required=True, help="Ruta al fitxer SHP o GeoJSON")
    parser.add_argument("--nuts2", default=None,
                        help="Filtra per codi NUTS2 (ex: ES51 per Catalunya). Només format CNIG.")
    args = parser.parse_args()
    import_municipalities(args.input, args.nuts2)

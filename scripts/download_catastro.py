"""
Descarrega i importa parcel·les rústiques del Catastro INSPIRE WFS per municipi.
Usa el bounding box del municipi (de la BD) per evitar problemes amb codis interns del Catastro.

Ús:
  # Per nom de municipi:
  python scripts/download_catastro.py --name "Abrera"
  python scripts/download_catastro.py --name "Vic" "Manresa" "Igualada"

  # Per codi INE:
  python scripts/download_catastro.py --code 08001

  # Només descarrega sense importar:
  python scripts/download_catastro.py --name "Abrera" --no-import
"""

import argparse
import sys
import os
import time
from pathlib import Path

import httpx
import geopandas as gpd
from shapely import wkt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings  # noqa: E402

WFS_URL = "https://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"
DOWNLOADS_DIR = Path("/data/imports/catastro")
BATCH_SIZE = 200


def get_municipality_info(session: Session, name: str | None = None, code: str | None = None) -> list[dict]:
    """Retorna llista de {id, name, code_ine, bbox} de la BD."""
    if name:
        rows = session.execute(
            text("""
                SELECT id, name, code_ine,
                       ST_XMin(ST_Extent(geom)) as minx, ST_YMin(ST_Extent(geom)) as miny,
                       ST_XMax(ST_Extent(geom)) as maxx, ST_YMax(ST_Extent(geom)) as maxy
                FROM core.municipality
                WHERE name ILIKE :name
                GROUP BY id, name, code_ine
                ORDER BY name
            """),
            {"name": f"%{name}%"},
        ).fetchall()
    else:
        rows = session.execute(
            text("""
                SELECT id, name, code_ine,
                       ST_XMin(ST_Extent(geom)) as minx, ST_YMin(ST_Extent(geom)) as miny,
                       ST_XMax(ST_Extent(geom)) as maxx, ST_YMax(ST_Extent(geom)) as maxy
                FROM core.municipality
                WHERE code_ine = :code OR code_ine = :code5
                GROUP BY id, name, code_ine
            """),
            {"code": code, "code5": str(code).zfill(5) if code else ""},
        ).fetchall()

    return [
        {"id": r.id, "name": r.name, "code_ine": r.code_ine,
         "bbox": (r.minx, r.miny, r.maxx, r.maxy)}
        for r in rows
    ]


PAGE_SIZE = 1000


def download_by_bbox(muni: dict) -> Path | None:
    """Descarrega parcel·les per bounding box del municipi amb paginació."""
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    code = muni["code_ine"]
    output = DOWNLOADS_DIR / f"parcels_{code}_{muni['name'].replace(' ','_')}.gml"

    if output.exists():
        print(f"  Ja descarregat: {output.name} — usant fitxer existent")
        return output

    minx, miny, maxx, maxy = muni["bbox"]
    margin = 0.001
    # WFS 2.0 amb EPSG:4326 usa ordre Y,X (lat,lon): miny,minx,maxy,maxx
    # NO afegir CRS suffix al BBOX (causa 500 al servidor del Catastro)
    bbox_str = f"{miny - margin},{minx - margin},{maxy + margin},{maxx + margin}"

    print(f"  Descarregant parcel·les de {muni['name']}...")

    base_params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": "CP:CadastralParcel",
        "SRSNAME": "urn:ogc:def:crs:EPSG::4326",
        "BBOX": bbox_str,
        "COUNT": str(PAGE_SIZE),
    }

    all_pages: list[bytes] = []
    start_index = 0

    try:
        while True:
            params = {**base_params, "STARTINDEX": str(start_index)}
            with httpx.stream("GET", WFS_URL, params=params, timeout=300, follow_redirects=True) as r:
                r.raise_for_status()
                page_data = b"".join(r.iter_bytes(chunk_size=8192))

            all_pages.append(page_data)
            page_kb = len(page_data) // 1024
            print(f"  Pàgina {start_index // PAGE_SIZE + 1}: {page_kb} KB")

            # Si la resposta és molt petita, probablement és l'última pàgina
            if len(page_data) < 5000:
                break

            # Comprova si hi ha menys features que PAGE_SIZE (última pàgina)
            feature_count = page_data.count(b"<CP:CadastralParcel ")
            if feature_count < PAGE_SIZE:
                break

            start_index += PAGE_SIZE
            time.sleep(0.3)

        # Si només hi ha una pàgina, escriu directament
        if len(all_pages) == 1:
            with open(output, "wb") as f:
                f.write(all_pages[0])
        else:
            # Combina pàgines: agafa el header de la primera i el footer de l'última
            # Elimina el wrapper XML de les pàgines intermèdies i finals
            with open(output, "wb") as f:
                first = all_pages[0]
                # Busca el tancament del wrapper per poder concatenar
                close_tag = b"</wfs:FeatureCollection>"
                header_end = first.rfind(close_tag)
                if header_end != -1 and len(all_pages) > 1:
                    f.write(first[:header_end])
                    for page in all_pages[1:-1]:
                        # Extreu només els features (entre el primer <CP: i el tancament)
                        start = page.find(b"<CP:CadastralParcel ")
                        end = page.rfind(close_tag)
                        if start != -1 and end != -1:
                            f.write(page[start:end])
                    # Última pàgina amb tancament
                    last = all_pages[-1]
                    start = last.find(b"<CP:CadastralParcel ")
                    if start != -1:
                        f.write(last[start:])
                    else:
                        f.write(close_tag)
                else:
                    # Fallback: escriu tot
                    for page in all_pages:
                        f.write(page)

        size_kb = output.stat().st_size // 1024
        print(f"  Descarregat: {output.name} ({size_kb} KB)")
        return output

    except Exception as e:
        print(f"  ERROR: {e}")
        if output.exists():
            output.unlink()
        return None


def import_gml(gml_path: Path, muni: dict) -> tuple[int, int]:
    """Importa un GML del Catastro filtrant per geometria del municipi."""
    print(f"  Llegint {gml_path.name}...")

    try:
        gdf = gpd.read_file(gml_path)
    except Exception as e:
        print(f"  ERROR llegint GML: {e}")
        return 0, 0

    gdf = gdf.to_crs(epsg=4326)
    # Filtra geometries vàlides i que no siguin punts de referència
    gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid]
    gdf = gdf[~gdf.geometry.geom_type.isin(["Point", "MultiPoint"])]
    # Normalitza tot a MultiPolygon (la columna DB és MultiPolygon)
    from shapely.geometry import MultiPolygon
    gdf = gdf.copy()
    gdf["geometry"] = gdf["geometry"].apply(
        lambda g: g if g.geom_type == "MultiPolygon" else MultiPolygon([g])
    )

    if len(gdf) == 0:
        print(f"  Cap parcel·la vàlida")
        return 0, 0

    print(f"  {len(gdf)} parcel·les llegides")
    print(f"  Columnes: {gdf.columns.tolist()}")

    # Referència catastral
    ref_col = next(
        (c for c in ["nationalCadastralReference", "localId", "gml_id", "REFCAT"] if c in gdf.columns),
        None,
    )

    # Àrea
    area_col = next((c for c in ["areaValue", "area"] if c in gdf.columns), None)

    engine = create_engine(settings.database_url)
    inserted = updated = 0

    with Session(engine) as session:
        # Geometria del municipi per filtrar parcel·les exteriors
        muni_geom_row = session.execute(
            text("SELECT ST_AsText(geom) FROM core.municipality WHERE id = :id"),
            {"id": muni["id"]},
        ).fetchone()
        muni_geom = wkt.loads(muni_geom_row[0]) if muni_geom_row else None

        batch = []
        skipped = 0
        for _, row in gdf.iterrows():
            # Extreu referència catastral
            if ref_col:
                raw = str(row[ref_col])
                # Neteja format INSPIRE "ES.SDGC.CP.XXXXX" → agafa la part final
                ref_cat = raw.split(".")[-1][:20]
            else:
                ref_cat = str(row.name)[:20]

            if not ref_cat or ref_cat in ("nan", "None"):
                skipped += 1
                continue

            # Filtra parcel·les fora del municipi (el bbox pot incloure municipis veïns)
            if muni_geom and not row.geometry.intersects(muni_geom):
                skipped += 1
                continue

            sup_m2 = float(row[area_col]) if area_col and row[area_col] else None
            sup_ha = sup_m2 / 10_000 if sup_m2 else None

            batch.append({
                "ref_catastral": ref_cat,
                "municipality_id": muni["id"],
                "superficie_ha": sup_ha,
                "geom": row.geometry.wkt,
            })

            if len(batch) >= BATCH_SIZE:
                i, u = _flush_batch(session, batch)
                inserted += i
                updated += u
                batch = []
                print(f"  {inserted + updated} processades...")

        if batch:
            i, u = _flush_batch(session, batch)
            inserted += i
            updated += u

        session.commit()

    print(f"  Saltades (fora de municipi o sense ref): {skipped}")
    print(f"  Import: {inserted} noves, {updated} actualitzades")
    return inserted, updated


def _flush_batch(session: Session, batch: list[dict]) -> tuple[int, int]:
    inserted = updated = 0
    for item in batch:
        try:
            result = session.execute(
                text("""
                    INSERT INTO core.parcel (ref_catastral, municipality_id, superficie_ha, geom)
                    VALUES (:ref_catastral, :municipality_id, :superficie_ha,
                            ST_GeomFromText(:geom, 4326))
                    ON CONFLICT (ref_catastral) DO UPDATE SET
                        municipality_id = COALESCE(EXCLUDED.municipality_id, core.parcel.municipality_id),
                        superficie_ha   = COALESCE(EXCLUDED.superficie_ha, core.parcel.superficie_ha),
                        geom            = EXCLUDED.geom
                    RETURNING (xmax = 0) AS ins
                """),
                item,
            )
            row = result.fetchone()
            if row and row[0]:
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            print(f"    Error inserint {item.get('ref_catastral')}: {e}")
            session.rollback()
    return inserted, updated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descarrega i importa parcel·les del Catastro INSPIRE")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--name", nargs="+", metavar="NOM", help="Nom(s) del municipi")
    group.add_argument("--code", nargs="+", metavar="INE", help="Codi(s) INE del municipi")
    group.add_argument("--all", action="store_true", help="Tots els municipis de la BD")
    parser.add_argument("--no-import", action="store_true", help="Només descarrega, no importa a la BD")
    args = parser.parse_args()

    engine = create_engine(settings.database_url)
    munis = []

    with Session(engine) as session:
        if args.all:
            rows = session.execute(
                text("""
                    SELECT id, name, code_ine,
                           ST_XMin(ST_Extent(geom)) as minx, ST_YMin(ST_Extent(geom)) as miny,
                           ST_XMax(ST_Extent(geom)) as maxx, ST_YMax(ST_Extent(geom)) as maxy
                    FROM core.municipality
                    GROUP BY id, name, code_ine
                    ORDER BY code_ine
                """)
            ).fetchall()
            munis = [
                {"id": r.id, "name": r.name, "code_ine": r.code_ine,
                 "bbox": (r.minx, r.miny, r.maxx, r.maxy)}
                for r in rows
            ]
            print(f"Total municipis: {len(munis)}")
        elif args.name:
            for name in args.name:
                found = get_municipality_info(session, name=name)
                if not found:
                    print(f"Municipi '{name}' no trobat a la BD")
                elif len(found) > 1:
                    print(f"Diversos municipis per '{name}':")
                    for m in found:
                        print(f"  {m['code_ine']}  {m['name']}")
                    munis.append(found[0])
                else:
                    munis.append(found[0])
        else:
            for code in args.code:
                found = get_municipality_info(session, code=code)
                if not found:
                    print(f"Codi '{code}' no trobat a la BD")
                else:
                    munis.append(found[0])

    if not munis:
        sys.exit(1)

    total_ins = total_upd = 0
    for muni in munis:
        print(f"\nProcessant: {muni['name']} ({muni['code_ine']})")
        gml = download_by_bbox(muni)
        if gml and not args.no_import:
            i, u = import_gml(gml, muni)
            total_ins += i
            total_upd += u
        time.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"Total: {total_ins} parcel·les noves, {total_upd} actualitzades.")

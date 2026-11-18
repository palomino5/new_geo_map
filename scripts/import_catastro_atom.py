"""
Importa TOTES les parcel·les rústiques de Catalunya des del servei ATOM INSPIRE del Catastro.

A diferència de download_catastro.py (WFS per bbox, amb límits de mida que deixaven
municipis incomplets), aquí es descarrega el ZIP complet de cada municipi:
  https://www.catastro.hacienda.gob.es/INSPIRE/CadastralParcels/{prov}/ES.SDGC.CP.atom_{prov}.xml

Passos:
  1. download  Descarrega els ZIP de les 4 províncies (reprèn si s'interromp)
  2. import    Llegeix cada GML, es queda amb les parcel·les RÚSTIQUES
               (referència de 14 caràcters amb lletra a la 6a posició: PPMMM A PPP PPPPP),
               i fa upsert a core.parcel per ref_catastral. El municipi s'assigna per
               intersecció espacial (punt interior de la parcel·la dins core.municipality).

  purge        Esborra les parcel·les NO rústiques (urbanes o referències invàlides)
               amb el seu NDVI i classificació.

Els ids existents es conserven (upsert per ref_catastral), així l'historial NDVI es manté.

Ús (dins el contenidor api):
  python scripts/import_catastro_atom.py download
  python scripts/import_catastro_atom.py purge
  python scripts/import_catastro_atom.py import
  python scripts/import_catastro_atom.py all
  python scripts/import_catastro_atom.py import --only 08001,25120
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import geopandas as gpd
import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")

DATABASE_URL = os.getenv("DATABASE_URL") or (
    "postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}".format(
        user=os.getenv("POSTGRES_USER", "geomap"),
        pw=os.getenv("POSTGRES_PASSWORD", "changeme"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        db=os.getenv("POSTGRES_DB", "geomap"),
    )
)

PROVINCES = ["08", "17", "25", "43"]  # Barcelona, Girona, Lleida, Tarragona
ATOM_URL = "https://www.catastro.hacienda.gob.es/INSPIRE/CadastralParcels/{p}/ES.SDGC.CP.atom_{p}.xml"
DOWNLOAD_DIR = Path(os.getenv("CATASTRO_DIR", "/data/imports/catastro_atom"))
RUSTIC_REF = re.compile(r"^\d{5}[A-Z]\d{8}$")

ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


# ── 1. Descàrrega ─────────────────────────────────────────────────────────────

def list_municipalities(client: httpx.Client) -> list[tuple[str, str, str]]:
    """Retorna [(provincia, codi_catastro, url_zip)] de les 4 províncies."""
    out = []
    for p in PROVINCES:
        r = client.get(ATOM_URL.format(p=p))
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for entry in root.findall("a:entry", ATOM_NS):
            for link in entry.findall("a:link", ATOM_NS):
                href = link.get("href", "")
                if href.endswith(".zip"):
                    code = href.rsplit(".", 2)[-2]  # ...A.ES.SDGC.CP.08001.zip → 08001
                    out.append((p, code, href.replace(" ", "%20")))
    return out


def download_all() -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=300, follow_redirects=True, headers={"User-Agent": "new_geo_map"}) as client:
        munis = list_municipalities(client)
        log(f"{len(munis)} municipis a les províncies {PROVINCES}")
        failed = []
        for i, (p, code, url) in enumerate(munis, 1):
            dest = DOWNLOAD_DIR / f"{code}.zip"
            if dest.exists() and dest.stat().st_size > 0:
                continue
            for attempt in range(3):
                try:
                    r = client.get(url)
                    r.raise_for_status()
                    tmp = dest.with_suffix(".part")
                    tmp.write_bytes(r.content)
                    tmp.rename(dest)
                    break
                except Exception as e:
                    if attempt == 2:
                        log(f"  {code}: ERROR {e}")
                        failed.append(code)
                    time.sleep(5 * (attempt + 1))
            if i % 25 == 0:
                log(f"  {i}/{len(munis)} descarregats")
            time.sleep(0.3)
    log(f"Descàrrega acabada. Errors: {failed or 'cap'}")


# ── 2. Importació ─────────────────────────────────────────────────────────────

STAGE_SQL = """
CREATE TEMP TABLE stage_parcel (
    ref_catastral varchar(20) PRIMARY KEY,
    superficie_ha double precision,
    geom geometry(MultiPolygon, 4326)
) ON COMMIT DROP
"""

UPSERT_SQL = """
INSERT INTO core.parcel (ref_catastral, municipality_id, superficie_ha, geom)
SELECT s.ref_catastral, m.id, s.superficie_ha, s.geom
FROM stage_parcel s
JOIN LATERAL (
    SELECT id FROM core.municipality mu
    WHERE ST_Intersects(mu.geom, ST_PointOnSurface(s.geom))
    LIMIT 1
) m ON true
ON CONFLICT (ref_catastral) DO UPDATE SET
    municipality_id = EXCLUDED.municipality_id,
    superficie_ha = EXCLUDED.superficie_ha,
    geom = EXCLUDED.geom
"""


def read_rustic(zip_path: Path) -> gpd.GeoDataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        name = next(n for n in zf.namelist() if n.endswith("cadastralparcel.gml"))
        data = zf.read(name)
    gdf = gpd.read_file(io.BytesIO(data))
    ref = gdf["nationalCadastralReference"].astype(str)
    gdf = gdf[ref.str.match(RUSTIC_REF)]
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if gdf.empty:
        return gdf
    gdf = gdf.to_crs(4326)
    gdf["geometry"] = gdf.geometry.make_valid()
    # make_valid pot retornar GeometryCollection: ens quedem amb la part poligonal
    gdf["geometry"] = gdf.geometry.apply(_polygonal)
    gdf = gdf[gdf.geometry.notna()]
    gdf = gdf.drop_duplicates("nationalCadastralReference")
    return gdf


def _polygonal(g):
    from shapely.geometry import MultiPolygon, Polygon
    if g is None:
        return None
    if isinstance(g, MultiPolygon):
        return g
    if isinstance(g, Polygon):
        return MultiPolygon([g])
    polys = []
    for part in getattr(g, "geoms", []):
        if isinstance(part, Polygon):
            polys.append(part)
        elif isinstance(part, MultiPolygon):
            polys.extend(part.geoms)
    return MultiPolygon(polys) if polys else None


def import_zip(engine, zip_path: Path) -> tuple[int, int]:
    gdf = read_rustic(zip_path)
    if gdf.empty:
        return 0, 0
    buf = io.StringIO()
    for ref, area, geom in zip(gdf["nationalCadastralReference"], gdf["areaValue"], gdf.geometry):
        ha = float(area) / 10_000 if area not in (None, "") else ""
        buf.write(f"{ref}\t{ha}\tSRID=4326;{geom.wkt}\n")
    buf.seek(0)

    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(STAGE_SQL)
        cur.copy_expert("COPY stage_parcel (ref_catastral, superficie_ha, geom) FROM STDIN WITH (FORMAT text, NULL '')", buf)
        cur.execute(UPSERT_SQL)
        n = cur.rowcount
        raw.commit()
        return len(gdf), n
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def import_all(only: set[str] | None) -> None:
    engine = create_engine(DATABASE_URL)
    zips = sorted(DOWNLOAD_DIR.glob("*.zip"))
    if only:
        zips = [z for z in zips if z.stem in only]
    log(f"Important {len(zips)} municipis de {DOWNLOAD_DIR}")
    total_read = total_up = 0
    errors = []
    for i, z in enumerate(zips, 1):
        try:
            read, up = import_zip(engine, z)
            total_read += read
            total_up += up
            if read != up:
                log(f"  {z.stem}: {read} rústiques llegides, {up} importades ({read - up} sense municipi)")
        except Exception as e:
            log(f"  {z.stem}: ERROR {e}")
            errors.append(z.stem)
        if i % 25 == 0 or i == len(zips):
            log(f"  {i}/{len(zips)} municipis · {total_up:,} parcel·les importades")
    log(f"Importació acabada: {total_read:,} llegides, {total_up:,} importades. Errors: {errors or 'cap'}")


PURGE_SQL = [
    # Parcel·les no rústiques (urbanes o referències invàlides) i tot el que en depèn
    """CREATE TEMP TABLE purge_ids ON COMMIT DROP AS
       SELECT id FROM core.parcel WHERE ref_catastral !~ '^[0-9]{5}[A-Z][0-9]{8}$'""",
    "DELETE FROM analytics.parcel_ndvi WHERE parcel_id IN (SELECT id FROM purge_ids)",
    "DELETE FROM analytics.parcel_status WHERE parcel_id IN (SELECT id FROM purge_ids)",
    "DELETE FROM core.parcel WHERE id IN (SELECT id FROM purge_ids)",
]


def purge_non_rustic() -> None:
    engine = create_engine(DATABASE_URL)
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        for sql in PURGE_SQL:
            cur.execute(sql)
            if sql.startswith("DELETE"):
                log(f"  {sql.split()[2]}: {cur.rowcount:,} files esborrades")
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["download", "purge", "import", "all"])
    ap.add_argument("--only", help="Codis de municipi Catastro separats per comes (ex: 08001,25120)")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None
    if args.step in ("download", "all"):
        download_all()
    if args.step in ("purge", "all"):
        purge_non_rustic()
    if args.step in ("import", "all"):
        import_all(only)
    return 0


if __name__ == "__main__":
    sys.exit(main())

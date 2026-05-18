"""
Importa usos del sòl no agrícoles des d'OpenStreetMap (Overpass API)
i actualitza uso_sigpac a core.parcel per a parcel·les dins de zones forestals
o urbanes, evitant falsos positius a la classificació.

Mapes OSM → SIGPAC:
  natural=wood / landuse=forest      → FO (forestal)
  landuse=residential/commercial/... → ZU (zona urbana)
  natural=water/waterway             → AG (aigues)
  landuse=meadow/grassland           → PA (pasto)

Ús:
  python scripts/import_landuse_osm.py --municipality Begues
  python scripts/import_landuse_osm.py --all
"""

import argparse
import os
import sys
import time
import urllib.parse
from pathlib import Path

import httpx
from shapely.geometry import shape, mapping
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_env = True
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    load_dotenv(Path(__file__).parent.parent / "backend" / ".env")
except ImportError:
    load_env = False

DATABASE_URL = os.getenv("DATABASE_URL") or (
    "postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}".format(
        user=os.getenv("POSTGRES_USER", "geomap"),
        pw=os.getenv("POSTGRES_PASSWORD", "changeme"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        db=os.getenv("POSTGRES_DB", "geomap"),
    )
)

OVERPASS_URL = "https://z.overpass-api.de/api/interpreter"
OVERPASS_DELAY = 2.0  # segons entre peticions (respectar rate limit)

# Tags OSM → codi SIGPAC equivalent
# Conservador: NOMÉS bosc i urbà. Excloem water (massa falsos positius amb
# llacunes, aiguamolls i mars que cobreixen camps agrícoles).
NON_AGRI_QUERY_TAGS = [
    '["natural"="wood"]',
    '["landuse"="forest"]',
    '["natural"="scrub"]',        # matollar mediterrani (garriga, brolla)
    '["natural"="heath"]',
    '["landuse"="residential"]',
    '["landuse"="commercial"]',
    '["landuse"="industrial"]',
    '["landuse"="retail"]',
]

OSM_TO_SIGPAC = {
    "wood": "FO", "forest": "FO", "scrub": "FO", "heath": "FO",
    "residential": "ZU", "commercial": "ZU", "industrial": "ZU", "retail": "ZU",
}


def build_overpass_query(bbox: tuple[float, float, float, float]) -> str:
    minx, miny, maxx, maxy = bbox
    # Overpass bbox: south,west,north,east
    bb = f"({miny},{minx},{maxy},{maxx})"
    # Només ways (no relations) → respostes molt més petites i ràpides.
    # Relations de bosc cobreixen àrees enormes i no aporten precisió extra.
    tag_parts = "\n".join(
        f"  way{tag}{bb};"
        for tag in NON_AGRI_QUERY_TAGS
    )
    return f"""[out:json][timeout:45][maxsize:10485760];
(
{tag_parts}
);
out geom qt;"""


def overpass_request(query: str) -> dict | None:
    encoded = urllib.parse.quote(query)
    try:
        r = httpx.get(f"{OVERPASS_URL}?data={encoded}",
                      headers={"User-Agent": "geomap-landuse-import/1.0"},
                      timeout=90)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ERROR Overpass: {e}")
        return None


def parse_features(osm_data: dict) -> list[dict]:
    """Extreu geometries i codi SIGPAC dels elements OSM."""
    features = []
    for elem in osm_data.get("elements", []):
        tags = elem.get("tags", {})
        uso = None
        for key, val in tags.items():
            if key in ("natural", "landuse", "waterway") and val in OSM_TO_SIGPAC:
                uso = OSM_TO_SIGPAC[val]
                break
        if not uso:
            continue

        geom = None
        if elem["type"] == "way" and "geometry" in elem:
            coords = [(n["lon"], n["lat"]) for n in elem["geometry"]]
            if len(coords) >= 4:
                try:
                    from shapely.geometry import Polygon
                    geom = Polygon(coords)
                    if not geom.is_valid:
                        geom = geom.buffer(0)
                except Exception:
                    continue
        elif elem["type"] == "relation" and "members" in elem:
            # Relacions complexes → bounding box aproximat
            lons = [n["lon"] for m in elem.get("members", []) for n in m.get("geometry", []) if "lon" in n]
            lats = [n["lat"] for m in elem.get("members", []) for n in m.get("geometry", []) if "lat" in n]
            if lons and lats:
                try:
                    from shapely.geometry import box
                    geom = box(min(lons), min(lats), max(lons), max(lats))
                except Exception:
                    continue

        if geom and not geom.is_empty:
            features.append({"uso_sigpac": uso, "geom_wkt": geom.wkt})

    return features


def update_parcels(session: Session, features: list[dict]) -> int:
    if not features:
        return 0

    for attempt in range(3):
        try:
            session.rollback()
            session.execute(text("""
                CREATE TEMP TABLE IF NOT EXISTS osm_landuse_tmp (
                    uso_sigpac TEXT,
                    geom GEOMETRY(GEOMETRY, 4326)
                ) ON COMMIT DROP
            """))
            session.execute(
                text("INSERT INTO osm_landuse_tmp (uso_sigpac, geom) VALUES (:uso, ST_GeomFromText(:geom, 4326))"),
                [{"uso": f["uso_sigpac"], "geom": f["geom_wkt"]} for f in features],
            )
            session.execute(text("CREATE INDEX ON osm_landuse_tmp USING GIST (geom)"))
            result = session.execute(text("""
                UPDATE core.parcel p
                SET uso_sigpac = t.uso_sigpac
                FROM osm_landuse_tmp t
                WHERE ST_Within(ST_Centroid(p.geom), t.geom)
                  AND (p.uso_sigpac IS NULL OR p.uso_sigpac = '')
            """))
            session.execute(text("DROP TABLE IF EXISTS osm_landuse_tmp"))
            session.commit()
            return result.rowcount
        except Exception as e:
            session.rollback()
            if attempt < 2:
                time.sleep(3 + attempt * 2)
            else:
                print(f"  ERROR després de 3 intents: {e}")
                return 0
    return 0


def get_municipalities(session: Session, name: str | None = None) -> list[dict]:
    if name:
        rows = session.execute(
            text("""
                SELECT id, name, code_ine,
                       ST_XMin(ST_Extent(geom)) as minx, ST_YMin(ST_Extent(geom)) as miny,
                       ST_XMax(ST_Extent(geom)) as maxx, ST_YMax(ST_Extent(geom)) as maxy
                FROM core.municipality
                WHERE name ILIKE :n
                GROUP BY id, name, code_ine ORDER BY name
            """),
            {"n": f"%{name}%"},
        ).fetchall()
    else:
        rows = session.execute(
            text("""
                SELECT id, name, code_ine,
                       ST_XMin(ST_Extent(geom)) as minx, ST_YMin(ST_Extent(geom)) as miny,
                       ST_XMax(ST_Extent(geom)) as maxx, ST_YMax(ST_Extent(geom)) as maxy
                FROM core.municipality
                GROUP BY id, name, code_ine ORDER BY code_ine
            """)
        ).fetchall()
    return [
        {"id": r.id, "name": r.name, "code_ine": r.code_ine,
         "bbox": (r.minx, r.miny, r.maxx, r.maxy)}
        for r in rows
    ]


def run(args: argparse.Namespace) -> None:
    engine = create_engine(DATABASE_URL)

    with Session(engine) as session:
        if args.all:
            munis = get_municipalities(session)
        else:
            munis = get_municipalities(session, name=args.municipality)

        if not munis:
            print("Cap municipi trobat.")
            return

        print(f"Processant {len(munis)} municipis via Overpass API...")
        total_updated = 0
        for i, muni in enumerate(munis, 1):
            print(f"[{i}/{len(munis)}] {muni['name']}...", end=" ", flush=True)
            query = build_overpass_query(muni["bbox"])
            data = overpass_request(query)
            if data is None:
                print("ERROR, salt")
                time.sleep(OVERPASS_DELAY * 2)
                continue

            features = parse_features(data)
            if not features:
                print("0 geometries no agrícoles")
                time.sleep(OVERPASS_DELAY)
                continue

            n = update_parcels(session, features)
            total_updated += n
            print(f"{len(features)} geometries OSM → {n} parcel·les actualitzades")
            time.sleep(OVERPASS_DELAY)

        print(f"\nTotal parcel·les uso_sigpac actualitzades: {total_updated}")

        # Resum
        result = session.execute(
            text("""
                SELECT uso_sigpac, COUNT(*) as cnt
                FROM core.parcel
                WHERE uso_sigpac IS NOT NULL
                GROUP BY uso_sigpac ORDER BY cnt DESC
            """)
        ).fetchall()
        print("\nDistribució uso_sigpac actualitzada:")
        for uso, cnt in result:
            print(f"  {uso:>6}  {cnt:>8}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importa usos del sòl des d'OSM")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Tots els municipis")
    group.add_argument("--municipality", help="Nom del municipi")
    args = parser.parse_args()
    run(args)

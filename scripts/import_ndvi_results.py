"""
Importa a la base de dades local els resultats NDVI publicats per GitHub Actions.

Llegeix el manifest.json de la release `ndvi-data` del repositori i el compara amb
analytics.ndvi_import per detectar dates noves o reprocessades (processed_at diferent).
Descarrega els CSV corresponents i els insereix (upsert per parcel_id + date).
Si entra alguna data, reclassifica.

Ús (dins el contenidor api):
  python scripts/import_ndvi_results.py                 # importa dates noves
  python scripts/import_ndvi_results.py --date 2026-10-21 --date 2026-10-28  # força dates
  python scripts/import_ndvi_results.py --no-classify

Variables d'entorn:
  GITHUB_REPO   default: palomino5/new_geo_map
  NDVI_RELEASE  default: ndvi-data
  GITHUB_TOKEN  opcional (necessari si el repo passa a ser privat)
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

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
GITHUB_REPO = os.getenv("GITHUB_REPO", "palomino5/new_geo_map")
NDVI_RELEASE = os.getenv("NDVI_RELEASE", "ndvi-data")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

CSV_COLUMNS = "parcel_id, ndvi_mean, ndvi_min, ndvi_max, ndvi_std, cloud_cover_pct, pixels"


def github_client() -> httpx.Client:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "new_geo_map-importer"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return httpx.Client(headers=headers, timeout=120, follow_redirects=True)


def download(client: httpx.Client, name: str, assets: dict[str, dict] | None) -> bytes | None:
    """Descarrega un fitxer de la release. Retorna None si no existeix.

    Sense token es fa servir la URL pública de descàrrega directa, que no consumeix
    el límit de 60 peticions/h de l'API de GitHub. Amb token (repo privat) es fa
    servir l'endpoint de l'API, per al qual cal haver llistat els assets abans.
    """
    if assets is None:
        r = client.get(f"https://github.com/{GITHUB_REPO}/releases/download/{NDVI_RELEASE}/{name}")
    else:
        if name not in assets:
            return None
        r = client.get(assets[name]["url"], headers={"Accept": "application/octet-stream"})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.content


def list_assets(client: httpx.Client) -> dict[str, dict] | None:
    """Només amb token: llista els assets via API. Sense token retorna None (URLs directes)."""
    if not GITHUB_TOKEN:
        return None
    r = client.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{NDVI_RELEASE}")
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    return {a["name"]: a for a in r.json().get("assets", [])}


def import_date(engine, d: str, processed_at: str, csv_gz: bytes) -> int:
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(f"""
            CREATE TEMP TABLE tmp_ndvi (
                parcel_id integer, ndvi_mean double precision, ndvi_min double precision,
                ndvi_max double precision, ndvi_std double precision,
                cloud_cover_pct double precision, pixels integer
            ) ON COMMIT DROP
        """)
        with gzip.open(io.BytesIO(csv_gz), "rt") as f:
            cur.copy_expert(f"COPY tmp_ndvi ({CSV_COLUMNS}) FROM STDIN WITH (FORMAT csv, HEADER true)", f)
        # JOIN amb core.parcel: ignora ids que ja no existeixin a la BD local
        cur.execute("""
            INSERT INTO analytics.parcel_ndvi
                (parcel_id, date, ndvi_mean, ndvi_min, ndvi_max, ndvi_std, cloud_cover_pct)
            SELECT t.parcel_id, %s::date, t.ndvi_mean, t.ndvi_min, t.ndvi_max, t.ndvi_std, t.cloud_cover_pct
            FROM tmp_ndvi t
            JOIN core.parcel p ON p.id = t.parcel_id
            ON CONFLICT (parcel_id, date) DO UPDATE SET
                ndvi_mean = EXCLUDED.ndvi_mean,
                ndvi_min = EXCLUDED.ndvi_min,
                ndvi_max = EXCLUDED.ndvi_max,
                ndvi_std = EXCLUDED.ndvi_std,
                cloud_cover_pct = EXCLUDED.cloud_cover_pct
        """, (d,))
        n = cur.rowcount
        cur.execute("""
            INSERT INTO analytics.ndvi_import (date, processed_at, rows_imported)
            VALUES (%s, %s, %s)
            ON CONFLICT (date) DO UPDATE SET
                processed_at = EXCLUDED.processed_at,
                rows_imported = EXCLUDED.rows_imported,
                imported_at = NOW()
        """, (d, processed_at, n))
        raw.commit()
        return n
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Importa resultats NDVI de GitHub Releases")
    ap.add_argument("--date", action="append", help="Força la importació d'aquesta data")
    ap.add_argument("--no-classify", action="store_true", help="No reclassificar després d'importar")
    args = ap.parse_args()

    engine = create_engine(DATABASE_URL)

    with github_client() as client:
        assets = list_assets(client)
        raw_manifest = download(client, "manifest.json", assets)
        if raw_manifest is None:
            print(f"No hi ha manifest.json a la release '{NDVI_RELEASE}' de {GITHUB_REPO}. Res a importar.")
            return 0
        manifest = json.loads(raw_manifest)
        published = {d: info for d, info in manifest.get("dates", {}).items() if info.get("rows", 0) > 0}

        with engine.connect() as conn:
            have = {
                r[0].isoformat(): r[1]
                for r in conn.execute(text("SELECT date, processed_at FROM analytics.ndvi_import"))
            }

        if args.date:
            todo = sorted(d for d in args.date if d in published)
        else:
            todo = sorted(d for d, info in published.items() if have.get(d) != info.get("processed_at"))
        print(f"Dates publicades: {len(published)} · ja importades: {len(published) - len(todo)} · a importar: {len(todo)}")

        imported = 0
        for d in todo:
            name = f"ndvi_{d}.csv.gz"
            data = download(client, name, assets)
            if data is None:
                print(f"  {d}: no hi ha {name} a la release, saltant")
                continue
            n = import_date(engine, d, published[d].get("processed_at", ""), data)
            print(f"  {d}: {n:,} parcel·les importades")
            imported += 1

    if imported and not args.no_classify:
        print("Reclassificant parcel·les...")
        from scripts.classify_parcels import run_classification
        run_classification()
    elif not imported:
        print("Res de nou.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

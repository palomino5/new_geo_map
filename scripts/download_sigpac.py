"""
Descarrega usos SIGPAC per a totes les parcel·les de Catalunya via WFS nacional.

Estratègia:
  1. Baixa les geometries SIGPAC (recintos) per municipi via WFS
  2. Guarda cada municipi com a Parquet a data/imports/sigpac/ (resumible)
  3. Importa a PostGIS (taula temporal) i actualitza uso_sigpac a core.parcel

Ús:
  # Un sol municipi (prova):
  python scripts/download_sigpac.py --name Abrera
  python scripts/download_sigpac.py --code 08001

  # Tots els municipis de Catalunya:
  python scripts/download_sigpac.py --all

  # Només importar fitxers ja descarregats (sense baixar de nou):
  python scripts/download_sigpac.py --import-only

  # Amb paràmetres explícits:
  python scripts/download_sigpac.py --all --batch-size 100 --delay 1.0
"""

import argparse
import sys
import os
import time
import json
from pathlib import Path

import httpx
import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from shapely.geometry import shape

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings  # noqa: E402

WFS_URL = "https://sigpac.mapa.gob.es/fega/servicioswfs/wfs"
LAYER_NAME = "sigpac:recinto"
DOWNLOADS_DIR = Path("/data/imports/sigpac")
PAGE_SIZE = 5000
DEFAULT_DELAY = 0.5  # segons entre peticions WFS

# Codis SIGPAC no agrícoles → classificar com a "desconeguda"
NON_AGRICULTURAL = {"FO", "PA", "PR", "ZU", "ED", "AG", "IM", "ZV", "OV_FO"}


def get_all_municipalities(session: Session) -> list[dict]:
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
    return [
        {"id": r.id, "name": r.name, "code_ine": r.code_ine,
         "bbox": (r.minx, r.miny, r.maxx, r.maxy)}
        for r in rows
    ]


def get_municipality(session: Session, name: str | None = None, code: str | None = None) -> list[dict]:
    if name:
        rows = session.execute(
            text("""
                SELECT id, name, code_ine,
                       ST_XMin(ST_Extent(geom)) as minx, ST_YMin(ST_Extent(geom)) as miny,
                       ST_XMax(ST_Extent(geom)) as maxx, ST_YMax(ST_Extent(geom)) as maxy
                FROM core.municipality
                WHERE name ILIKE :name
                GROUP BY id, name, code_ine ORDER BY name
            """),
            {"name": f"%{name}%"},
        ).fetchall()
    else:
        code5 = str(code).zfill(5) if code else ""
        rows = session.execute(
            text("""
                SELECT id, name, code_ine,
                       ST_XMin(ST_Extent(geom)) as minx, ST_YMin(ST_Extent(geom)) as miny,
                       ST_XMax(ST_Extent(geom)) as maxx, ST_YMax(ST_Extent(geom)) as maxy
                FROM core.municipality
                WHERE code_ine = :code OR code_ine = :code5
                GROUP BY id, name, code_ine
            """),
            {"code": code, "code5": code5},
        ).fetchall()
    return [
        {"id": r.id, "name": r.name, "code_ine": r.code_ine,
         "bbox": (r.minx, r.miny, r.maxx, r.maxy)}
        for r in rows
    ]


def download_sigpac_wfs(muni: dict, delay: float = DEFAULT_DELAY) -> gpd.GeoDataFrame | None:
    """Baixa recintos SIGPAC per al bbox del municipi via WFS amb paginació."""
    minx, miny, maxx, maxy = muni["bbox"]
    bbox_str = f"{miny},{minx},{maxy},{maxx}"  # WFS 2.0 usa lat,lon (EPSG:4326)

    all_features = []
    start_index = 0

    with httpx.Client(timeout=60) as client:
        while True:
            params = {
                "SERVICE": "WFS",
                "VERSION": "2.0.0",
                "REQUEST": "GetFeature",
                "TYPENAMES": LAYER_NAME,
                "BBOX": f"{bbox_str},EPSG:4326",
                "COUNT": str(PAGE_SIZE),
                "STARTINDEX": str(start_index),
                "OUTPUTFORMAT": "application/json",
                "SRSNAME": "EPSG:4326",
            }
            try:
                r = client.get(WFS_URL, params=params)
                r.raise_for_status()
            except httpx.HTTPError as e:
                print(f"  ERROR WFS {muni['name']}: {e}")
                return None

            try:
                data = r.json()
            except Exception:
                print(f"  ERROR: resposta no JSON per {muni['name']}")
                print(f"  URL: {r.url}")
                print(f"  Resposta (primers 300 chars): {r.text[:300]}")
                return None

            features = data.get("features", [])
            all_features.extend(features)

            if len(features) < PAGE_SIZE:
                break
            start_index += PAGE_SIZE
            time.sleep(delay)

    if not all_features:
        return gpd.GeoDataFrame()

    rows = []
    for f in all_features:
        props = f.get("properties", {})
        geom = f.get("geometry")
        if not geom:
            continue
        uso = (
            props.get("USO_SIGPAC") or
            props.get("uso_sigpac") or
            props.get("USO") or
            props.get("uso") or
            ""
        ).strip().upper()
        rows.append({"uso_sigpac": uso, "geometry": shape(geom)})

    if not rows:
        return gpd.GeoDataFrame()

    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


def save_parquet(gdf: gpd.GeoDataFrame, muni: dict) -> Path:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = muni["name"].replace(" ", "_").replace("/", "-")
    path = DOWNLOADS_DIR / f"sigpac_{muni['code_ine']}_{safe_name}.parquet"
    gdf.to_parquet(path)
    return path


def parquet_exists(muni: dict) -> bool:
    safe_name = muni["name"].replace(" ", "_").replace("/", "-")
    return (DOWNLOADS_DIR / f"sigpac_{muni['code_ine']}_{safe_name}.parquet").exists()


def update_uso_sigpac_batch(session: Session, gdf: gpd.GeoDataFrame) -> int:
    """Carrega gdf a taula temp i actualitza core.parcel via intersecció espacial."""
    if gdf.empty:
        return 0

    # Inserir a taula temporal
    session.execute(text("""
        CREATE TEMP TABLE IF NOT EXISTS sigpac_tmp (
            uso_sigpac TEXT,
            geom GEOMETRY(GEOMETRY, 4326)
        ) ON COMMIT DROP
    """))

    rows = [
        {"uso": row.uso_sigpac, "geom": row.geometry.wkt}
        for _, row in gdf.iterrows()
        if row.uso_sigpac and row.geometry is not None
    ]
    if not rows:
        return 0

    session.execute(
        text("INSERT INTO sigpac_tmp (uso_sigpac, geom) VALUES (:uso, ST_GeomFromText(:geom, 4326))"),
        rows,
    )

    result = session.execute(text("""
        UPDATE core.parcel p
        SET uso_sigpac = t.uso_sigpac
        FROM sigpac_tmp t
        WHERE ST_Intersects(p.geom, t.geom)
          AND (p.uso_sigpac IS NULL OR p.uso_sigpac = '')
    """))
    session.execute(text("DROP TABLE IF EXISTS sigpac_tmp"))
    session.commit()
    return result.rowcount


def run(args: argparse.Namespace) -> None:
    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        # Determina quins municipis processar
        if args.import_only:
            munis = []
        elif getattr(args, "all", False):
            munis = get_all_municipalities(session)
            print(f"{len(munis)} municipis a processar")
        elif args.name:
            munis = get_municipality(session, name=args.name)
        elif args.code:
            munis = get_municipality(session, code=args.code)
        else:
            print("ERROR: cal especificar --all, --name, --code o --import-only")
            sys.exit(1)

        # Descàrrega
        if not args.import_only:
            total = len(munis)
            for i, muni in enumerate(munis, 1):
                prefix = f"[{i}/{total}] {muni['name']} ({muni['code_ine']})"
                if parquet_exists(muni):
                    print(f"{prefix} → ja descarregat, salt")
                    continue
                print(f"{prefix} → baixant SIGPAC...", end=" ", flush=True)
                gdf = download_sigpac_wfs(muni, delay=args.delay)
                if gdf is None:
                    print("ERROR, salt")
                    continue
                if gdf.empty:
                    print("0 recintos")
                    save_parquet(gdf, muni)
                    continue
                path = save_parquet(gdf, muni)
                print(f"{len(gdf)} recintos → {path.name}")
                time.sleep(args.delay)

        # Importació de tots els parquets a la BD
        parquet_files = sorted(DOWNLOADS_DIR.glob("sigpac_*.parquet"))
        if not parquet_files:
            print("No hi ha fitxers Parquet a importar.")
            return

        print(f"\nImportant {len(parquet_files)} fitxers a core.parcel.uso_sigpac...")
        total_updated = 0
        for pf in parquet_files:
            gdf = gpd.read_parquet(pf)
            if gdf.empty:
                continue
            n = update_uso_sigpac_batch(session, gdf)
            total_updated += n
            print(f"  {pf.name}: {n} parcel·les actualitzades")

        print(f"\nTotal parcel·les actualitzades: {total_updated}")

        # Resum d'usos importats
        result = session.execute(
            text("SELECT uso_sigpac, COUNT(*) FROM core.parcel GROUP BY uso_sigpac ORDER BY COUNT(*) DESC LIMIT 20")
        ).fetchall()
        print("\nDistribució uso_sigpac a core.parcel:")
        for uso, cnt in result:
            flag = " ← no agrícola" if uso and uso.upper() in NON_AGRICULTURAL else ""
            print(f"  {uso or 'NULL':>10}  {cnt:>8}{flag}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descarrega i importa usos SIGPAC")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="Tots els municipis de la BD")
    group.add_argument("--name", help="Nom del municipi (cerca parcial)")
    group.add_argument("--code", help="Codi INE del municipi (ex: 08001)")
    group.add_argument("--import-only", action="store_true",
                       help="Només importa parquets ja descarregats (sense baixar)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        help=f"Espera entre peticions WFS (s, default {DEFAULT_DELAY})")
    args = parser.parse_args()
    run(args)

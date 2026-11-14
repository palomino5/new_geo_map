"""
Pipeline NDVI per a GitHub Actions (substitueix l'orquestrador de la Raspberry Pi).

Llegeix les bandes B04/B08/SCL de Sentinel-2 L2A directament dels COG públics
d'Earth Search (AWS, sense credencials), calcula l'NDVI píxel a píxel amb màscara
de núvols (SCL) i agrega estadístiques per parcel·la.

Entrada:
  --parcels   FlatGeobuf amb les parcel·les (columnes: id, geometry en EPSG:4326),
              generat al PC amb `.\\setup.ps1 publish-parcels`
  --manifest  manifest.json existent (dates ja processades); pot no existir

Sortida (a --out-dir):
  ndvi_YYYY-MM-DD.csv.gz   parcel_id,ndvi_mean,ndvi_min,ndvi_max,ndvi_std,cloud_cover_pct,pixels
  manifest.json            {"dates": {"YYYY-MM-DD": {"rows": N, "tiles": [...], ...}}}

Si s'indica --release, cada data es puja a la release de GitHub (via `gh`) just
en acabar-la, de manera que un timeout no fa perdre la feina ja feta.

Ús:
  python scripts/gha_ndvi_pipeline.py --parcels parcels.fgb --manifest out/manifest.json \\
      --out-dir out --release ndvi-data
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import geopandas as gpd
import httpx
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.windows import Window, from_bounds
from shapely.geometry import box, shape

STAC_URL = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = os.getenv("STAC_COLLECTION", "sentinel-2-c1-l2a")
CATALUNYA_BBOX = [0.15, 40.52, 3.33, 42.86]

# Classes SCL considerades observació vàlida de superfície:
# 4 vegetació, 5 sòl nu, 6 aigua, 7 no classificat (baixa probabilitat de núvol)
SCL_CLEAR = np.array([4, 5, 6, 7], dtype=np.uint8)

# Fracció mínima de píxels clars dins la parcel·la per acceptar l'observació
MIN_CLEAR_FRACTION = 0.5

# Dies mínims d'antiguitat d'una data abans de processar-la (el catàleg
# a vegades publica els tiles d'una mateixa passada amb unes hores/dies de diferència)
MIN_AGE_DAYS = 2

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")


def log(msg: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


# ── Catàleg STAC ──────────────────────────────────────────────────────────────

def search_items(start: date, end: date, max_cloud: float) -> list[dict]:
    body: dict | None = {
        "collections": [COLLECTION],
        "bbox": CATALUNYA_BBOX,
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
        "limit": 100,
    }
    url = STAC_URL
    items: list[dict] = []
    with httpx.Client(timeout=60) as client:
        while body is not None:
            r = client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
            items.extend(data.get("features", []))
            nxt = next((l for l in data.get("links", []) if l.get("rel") == "next"), None)
            if nxt is None:
                break
            url = nxt["href"]
            body = nxt.get("body")
    return items


def group_by_date(items: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        grouped[it["properties"]["datetime"][:10]].append(it)
    return grouped


# ── Càlcul per tile ───────────────────────────────────────────────────────────

@dataclass
class ParcelObs:
    ndvi_mean: float
    ndvi_min: float
    ndvi_max: float
    ndvi_std: float
    cloud_cover_pct: float
    pixels: int  # píxels clars usats


def band_scale_offset(asset: dict) -> tuple[float, float]:
    bands = asset.get("raster:bands") or asset.get("bands") or [{}]
    b = bands[0]
    return float(b.get("scale", 0.0001)), float(b.get("offset", 0.0))


def process_item(item: dict, parcels: gpd.GeoDataFrame) -> dict[int, ParcelObs]:
    """Calcula estadístiques NDVI per a les parcel·les dins el footprint d'un tile."""
    footprint = shape(item["geometry"])
    cand_idx = parcels.sindex.query(footprint, predicate="intersects")
    if len(cand_idx) == 0:
        return {}

    props = item["properties"]
    epsg = props.get("proj:epsg") or int(str(props.get("proj:code", "")).split(":")[-1])
    subset = parcels.iloc[cand_idx].to_crs(epsg=epsg)

    red_a, nir_a, scl_a = item["assets"]["red"], item["assets"]["nir"], item["assets"]["scl"]
    red_scale, red_off = band_scale_offset(red_a)
    nir_scale, nir_off = band_scale_offset(nir_a)

    with rasterio.open(red_a["href"]) as red_src, \
         rasterio.open(nir_a["href"]) as nir_src, \
         rasterio.open(scl_a["href"]) as scl_src:

        rb = red_src.bounds
        minx, miny, maxx, maxy = subset.total_bounds
        minx, miny = max(minx, rb.left), max(miny, rb.bottom)
        maxx, maxy = min(maxx, rb.right), min(maxy, rb.top)
        if minx >= maxx or miny >= maxy:
            return {}

        win = from_bounds(minx, miny, maxx, maxy, red_src.transform)
        win = win.round_offsets().round_lengths()
        win = win.intersection(Window(0, 0, red_src.width, red_src.height))
        h, w = int(win.height), int(win.width)
        transform = red_src.window_transform(win)

        red = red_src.read(1, window=win)
        nir = nir_src.read(1, window=win)
        # SCL és a 20 m: llegim la mateixa extensió remostrejada a la graella de 10 m
        scl_win = from_bounds(*rasterio.windows.bounds(win, red_src.transform), scl_src.transform)
        scl = scl_src.read(1, window=scl_win, out_shape=(h, w), resampling=Resampling.nearest)

    # Etiqueta cada píxel amb la posició (1..n) de la parcel·la que el conté
    labels = rasterize(
        ((geom, i + 1) for i, geom in enumerate(subset.geometry.values)),
        out_shape=(h, w), transform=transform, fill=0, dtype="int32",
    )
    n = len(subset)

    has_data = (labels > 0) & (red > 0) & (nir > 0)
    clear = has_data & np.isin(scl, SCL_CLEAR)

    total_cnt = np.bincount(labels[has_data], minlength=n + 1)
    lab_c = labels[clear]
    r = red[clear].astype(np.float32) * red_scale + red_off
    nr = nir[clear].astype(np.float32) * nir_scale + nir_off
    denom = nr + r
    ok = denom > 0
    lab_c, ndvi = lab_c[ok], (nr[ok] - r[ok]) / denom[ok]
    ndvi = np.clip(ndvi, -1.0, 1.0)

    clear_cnt = np.bincount(lab_c, minlength=n + 1)
    s1 = np.bincount(lab_c, weights=ndvi, minlength=n + 1)
    s2 = np.bincount(lab_c, weights=ndvi.astype(np.float64) ** 2, minlength=n + 1)

    # min / max per etiqueta: ordenem i reduïm per segments
    order = np.argsort(lab_c, kind="stable")
    lab_sorted, ndvi_sorted = lab_c[order], ndvi[order]
    uniq, starts = np.unique(lab_sorted, return_index=True)
    mins = np.minimum.reduceat(ndvi_sorted, starts) if len(starts) else np.array([])
    maxs = np.maximum.reduceat(ndvi_sorted, starts) if len(starts) else np.array([])
    min_by_lab = dict(zip(uniq.tolist(), mins.tolist()))
    max_by_lab = dict(zip(uniq.tolist(), maxs.tolist()))

    ids = subset["id"].to_numpy()
    out: dict[int, ParcelObs] = {}
    for lab in uniq.tolist():
        c, t = int(clear_cnt[lab]), int(total_cnt[lab])
        if c == 0 or t == 0 or c / t < MIN_CLEAR_FRACTION:
            continue
        mean = s1[lab] / c
        var = max(s2[lab] / c - mean * mean, 0.0)
        out[int(ids[lab - 1])] = ParcelObs(
            ndvi_mean=round(float(mean), 4),
            ndvi_min=round(float(min_by_lab[lab]), 4),
            ndvi_max=round(float(max_by_lab[lab]), 4),
            ndvi_std=round(float(np.sqrt(var)), 4),
            cloud_cover_pct=round(100.0 * (1 - c / t), 1),
            pixels=c,
        )
    return out


def process_date(items: list[dict], parcels: gpd.GeoDataFrame) -> tuple[dict[int, ParcelObs], list[str]]:
    best: dict[int, ParcelObs] = {}
    tiles: list[str] = []
    for it in sorted(items, key=lambda i: i["id"]):
        tile = it["properties"].get("grid:code") or it["id"]
        t0 = time.time()
        try:
            res = process_item(it, parcels)
        except Exception as e:  # un tile corrupte no ha d'aturar tota la data
            log(f"    {it['id']}: ERROR {e}")
            continue
        # Parcel·les a la zona de solapament entre tiles: ens quedem amb més píxels clars
        for pid, obs in res.items():
            prev = best.get(pid)
            if prev is None or obs.pixels > prev.pixels:
                best[pid] = obs
        tiles.append(tile)
        log(f"    {it['id']}: {len(res):,} parcel·les ({time.time() - t0:.0f}s)")
    return best, tiles


# ── Sortida ───────────────────────────────────────────────────────────────────

def write_csv(path: Path, results: dict[int, ParcelObs]) -> None:
    with gzip.open(path, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["parcel_id", "ndvi_mean", "ndvi_min", "ndvi_max", "ndvi_std", "cloud_cover_pct", "pixels"])
        for pid in sorted(results):
            o = results[pid]
            w.writerow([pid, o.ndvi_mean, o.ndvi_min, o.ndvi_max, o.ndvi_std, o.cloud_cover_pct, o.pixels])


def gh_upload(release: str, *files: Path) -> None:
    subprocess.run(["gh", "release", "upload", release, *map(str, files), "--clobber"], check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parcels", required=True, type=Path)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=Path("out"))
    ap.add_argument("--lookback-days", type=int, default=int(os.getenv("LOOKBACK_DAYS", "365")))
    ap.add_argument("--max-cloud", type=float, default=float(os.getenv("MAX_CLOUD", "30")))
    ap.add_argument("--max-dates", type=int, default=int(os.getenv("MAX_DATES", "6")))
    ap.add_argument("--date", action="append", help="Força processar aquesta data (es pot repetir)")
    ap.add_argument("--release", default=None, help="Tag de la release on pujar els resultats")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_dir / "manifest.json"
    manifest: dict = {"dates": {}}
    if args.manifest and args.manifest.exists():
        manifest = json.loads(args.manifest.read_text())
        manifest.setdefault("dates", {})

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=args.lookback_days)
    end = today - timedelta(days=MIN_AGE_DAYS)

    log(f"Cercant imatges {COLLECTION} {start} → {end} (núvols < {args.max_cloud}%)")
    by_date = group_by_date(search_items(start, end, args.max_cloud))
    log(f"  {sum(map(len, by_date.values()))} tiles en {len(by_date)} dates")

    if args.date:
        pending = [d for d in args.date if d in by_date]
    else:
        # Primer les més recents: són les que més pesen a la classificació
        pending = sorted((d for d in by_date if d not in manifest["dates"]), reverse=True)
    log(f"  {len(pending)} dates pendents; en processem fins a {args.max_dates}: {pending[:args.max_dates]}")
    pending = pending[:args.max_dates]
    if not pending:
        manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
        return

    log(f"Carregant parcel·les de {args.parcels}...")
    parcels = gpd.read_file(args.parcels)
    if parcels.crs is None or parcels.crs.to_epsg() != 4326:
        parcels = parcels.set_crs(4326, allow_override=True) if parcels.crs is None else parcels.to_crs(4326)
    parcels = parcels[["id", "geometry"]].reset_index(drop=True)
    _ = parcels.sindex
    log(f"  {len(parcels):,} parcel·les")

    for d in pending:
        log(f"Data {d}: {len(by_date[d])} tiles")
        results, tiles = process_date(by_date[d], parcels)
        csv_path = args.out_dir / f"ndvi_{d}.csv.gz"
        write_csv(csv_path, results)
        manifest["dates"][d] = {
            "rows": len(results),
            "tiles": tiles,
            "collection": COLLECTION,
            "processed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
        log(f"  {d}: {len(results):,} parcel·les amb NDVI")
        if args.release:
            gh_upload(args.release, csv_path, manifest_path)

    log("Fet.")


if __name__ == "__main__":
    sys.exit(main())

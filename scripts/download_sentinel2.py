"""
Descarrega imatges Sentinel-2 (bandes B04 i B08) per a l'àrea de Catalunya.
Utilitza l'API de Copernicus Data Space (CDSE).
Ús: python scripts/download_sentinel2.py --start 2024-01-01 --end 2024-03-31 --max-cloud 20
"""

import argparse
import io
import os
import sys
import zipfile
from pathlib import Path

import httpx
import rasterio
from rasterio.io import MemoryFile

CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
DOWNLOAD_BASE = "https://download.dataspace.copernicus.eu/odata/v1/Products"
CATALOGUE_BBOX = "0.15,40.52,3.33,42.86"  # Catalunya
OUTPUT_BASE = Path("data/sentinel2")


def search_products(start: str, end: str, max_cloud: float) -> list[dict]:
    params = {
        "$filter": (
            f"Collection/Name eq 'SENTINEL-2' "
            f"and OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(("
            f"0.15 40.52,3.33 40.52,3.33 42.86,0.15 42.86,0.15 40.52))')"
            f" and ContentDate/Start gt {start}T00:00:00.000Z"
            f" and ContentDate/Start lt {end}T23:59:59.000Z"
            f" and Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' "
            f"and att/OData.CSC.DoubleAttribute/Value le {max_cloud})"
            f" and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' "
            f"and att/OData.CSC.StringAttribute/Value eq 'S2MSI2A')"
        ),
        "$orderby": "ContentDate/Start asc",
        "$top": "50",
    }

    print("Cercant imatges Sentinel-2...")
    with httpx.Client(timeout=30) as client:
        r = client.get(CATALOGUE_URL, params=params)
        r.raise_for_status()
        data = r.json()

    products = data.get("value", [])
    print(f"Trobades {len(products)} imatges.")
    return products


def get_tile_id(product_name: str) -> str:
    """Extreu l'ID del tile Sentinel-2 del nom del producte (ex: T31TBH)."""
    parts = product_name.split("_")
    for part in parts:
        if len(part) == 6 and part.startswith("T") and part[1:3].isdigit():
            return part
    return "UNKNOWN"


def download_bands(product: dict, username: str, password: str) -> None:
    product_id = product["Id"]
    product_name = product.get("Name", product_id)
    date_str = product["ContentDate"]["Start"][:10]
    tile_id = get_tile_id(product_name)

    # Salta productes no disponibles en línia (estan en Long Term Archive)
    if not product.get("Online", True):
        print(f"  Salta {date_str} {tile_id}: producte en arxiu (no Online)")
        return

    output_dir = OUTPUT_BASE / date_str
    output_dir.mkdir(parents=True, exist_ok=True)

    # Inclou tile_id al nom per evitar sobreescriure tiles del mateix dia
    b04_out = output_dir / f"{date_str}_{tile_id}_B04.tif"
    b08_out = output_dir / f"{date_str}_{tile_id}_B08.tif"

    if b04_out.exists() and b08_out.exists():
        print(f"  Ja existeix: {date_str} {tile_id} B04+B08")
        return

    print(f"  Descarregant {product_name[:60]} ({date_str})...")
    url = f"{DOWNLOAD_BASE}({product_id})/$value"

    # Descarrega a fitxer temporal per evitar OOM en dispositius amb poca RAM (ex: Pi 3B)
    tmp_zip = output_dir / f"_tmp_{tile_id}.zip"
    downloaded_ok = False
    for attempt in range(1, 4):
        try:
            token = get_token(username, password)
            headers = {"Authorization": f"Bearer {token}"}
            with httpx.stream("GET", url, headers=headers, timeout=900, follow_redirects=True) as r:
                r.raise_for_status()
                size = 0
                with open(tmp_zip, "wb") as fout:
                    for chunk in r.iter_bytes(chunk_size=65536):
                        fout.write(chunk)
                        size += len(chunk)
            downloaded_ok = True
            break
        except Exception as e:
            print(f"  Intent {attempt}/3 fallit: {type(e).__name__}: {str(e)[:80]}")
            tmp_zip.unlink(missing_ok=True)
            if attempt < 3:
                import time as _time
                _time.sleep(10 * attempt)
            else:
                print(f"  ERROR: no s'ha pogut descarregar {product_name[:50]} després de 3 intents")
                return

    if not downloaded_ok:
        return

    size_mb = tmp_zip.stat().st_size // 1024 // 1024
    print(f"  Descarregat {size_mb} MB, extraient bandes B04/B08...")

    try:
        with zipfile.ZipFile(tmp_zip) as zf:
            names = zf.namelist()
            for band_key, out_path in (("B04_10m", b04_out), ("B08_10m", b08_out)):
                if out_path.exists():
                    continue
                matches = [n for n in names if band_key in n and n.endswith(".jp2")]
                if not matches:
                    print(f"  AVÍS: no s'ha trobat {band_key} al producte")
                    continue
                jp2_name = matches[0]
                print(f"  Extraient {jp2_name.split('/')[-1]} → {out_path.name}")
                with zf.open(jp2_name) as jp2_f:
                    jp2_data = jp2_f.read()
                with MemoryFile(jp2_data) as memfile:
                    with memfile.open() as src:
                        profile = src.profile.copy()
                        profile.update(driver="GTiff", compress="lzw")
                        with rasterio.open(out_path, "w", **profile) as dst:
                            dst.write(src.read())
    finally:
        tmp_zip.unlink(missing_ok=True)

    print(f"  Guardat: {b04_out.name}, {b08_out.name}")


TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
_token_cache = {"token": None, "expires_at": 0}


def get_token(username: str, password: str) -> str:
    import time
    now = time.time()
    # Renova si falten menys de 60 s per caducar (token dura ~600 s)
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    r = httpx.post(
        TOKEN_URL,
        data={"client_id": "cdse-public", "grant_type": "password",
              "username": username, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 600)
    return _token_cache["token"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descarrega imatges Sentinel-2 per Catalunya")
    parser.add_argument("--start", required=True, help="Data inici YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Data fi YYYY-MM-DD")
    parser.add_argument("--max-cloud", type=float, default=20.0, help="Cobertura màxima de núvols %%")
    parser.add_argument("--username", default=os.getenv("COPERNICUS_USER"), help="Usuari Copernicus")
    parser.add_argument("--password", default=os.getenv("COPERNICUS_PASS"), help="Contrasenya Copernicus")
    args = parser.parse_args()

    if not args.username or not args.password:
        print("ERROR: Cal definir COPERNICUS_USER i COPERNICUS_PASS (o usar --username/--password)")
        sys.exit(1)

    get_token(args.username, args.password)  # verifica credencials abans de començar
    products = search_products(args.start, args.end, args.max_cloud)

    for product in products:
        download_bands(product, args.username, args.password)

    print("Descàrrega completada.")

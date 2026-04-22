"""
Descarrega imatges Sentinel-2 (bandes B04 i B08) per a l'àrea de Catalunya.
Utilitza l'API de Copernicus Data Space (CDSE).
Ús: python scripts/download_sentinel2.py --start 2024-01-01 --end 2024-03-31 --max-cloud 20
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx

CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
DOWNLOAD_URL = "https://zipper.dataspace.copernicus.eu/odata/v1/Products"
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


def download_bands(product: dict, token: str) -> None:
    product_id = product["Id"]
    date_str = product["ContentDate"]["Start"][:10]
    output_dir = OUTPUT_BASE / date_str
    output_dir.mkdir(parents=True, exist_ok=True)

    for band in ("B04", "B08"):
        output_file = output_dir / f"{product_id}_{band}.tif"
        if output_file.exists():
            print(f"  Ja existeix: {output_file.name}")
            continue

        print(f"  Descarregant {band} per {date_str}...")
        url = f"{DOWNLOAD_URL}({product_id})/$value"
        headers = {"Authorization": f"Bearer {token}"}

        with httpx.stream("GET", url, headers=headers, timeout=300, follow_redirects=True) as r:
            r.raise_for_status()
            with open(output_file, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        print(f"  Guardat: {output_file}")


def get_token(username: str, password: str) -> str:
    r = httpx.post(
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
        data={
            "client_id": "cdse-public",
            "grant_type": "password",
            "username": username,
            "password": password,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


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

    token = get_token(args.username, args.password)
    products = search_products(args.start, args.end, args.max_cloud)

    for product in products:
        download_bands(product, token)

    print("Descàrrega completada.")

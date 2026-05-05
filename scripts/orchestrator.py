"""
Orquestrador autònom per a Raspberry Pi 3B.
Descarrega Sentinel-2, calcula NDVI i classifica parcel·les sense intervenció manual.

Configuració via variables d'entorn (.env o entorn del sistema):
  DATABASE_URL       postgresql://user:pass@host:5432/db
  COPERNICUS_USER    usuari Copernicus
  COPERNICUS_PASS    contrasenya Copernicus
  SENTINEL_DATA_DIR  directori on guardar les imatges (default: data/sentinel2)
  LOOP_INTERVAL_H    hores entre cicles (default: 24)
  LOOKBACK_DAYS      dies enrere a cercar imatges noves (default: 30)
  MAX_CLOUD          cobertura màxima de núvols % (default: 20)
  LOG_FILE           fitxer de log (default: orchestrator.log)
  NOTIFY_EMAIL       adreça destí de les notificacions (opcional)
  NOTIFY_FROM        Gmail des del qual s'envien (opcional)
  NOTIFY_PASSWORD    App Password de Gmail (opcional)

Ús:
  python scripts/orchestrator.py            # loop continu
  python scripts/orchestrator.py --once     # executa un cicle i surt
  python scripts/orchestrator.py --status   # mostra estat actual i surt
"""

import argparse
import logging
import os
import smtplib
import sys
import time
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

# ── Configuració ──────────────────────────────────────────────────────────────

DATA_DIR = Path(os.getenv("SENTINEL_DATA_DIR", "data/sentinel2"))
LOOP_INTERVAL_H = float(os.getenv("LOOP_INTERVAL_H", "24"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "30"))
MAX_CLOUD = float(os.getenv("MAX_CLOUD", "20"))
LOG_FILE = os.getenv("LOG_FILE", "orchestrator.log")

COPERNICUS_USER = os.getenv("COPERNICUS_USER", "")
COPERNICUS_PASS = os.getenv("COPERNICUS_PASS", "")

NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "")
NOTIFY_FROM = os.getenv("NOTIFY_FROM", "")
NOTIFY_PASSWORD = os.getenv("NOTIFY_PASSWORD", "")

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── Notificació per email ─────────────────────────────────────────────────────

def send_email(subject: str, body: str) -> None:
    if not NOTIFY_EMAIL or not NOTIFY_FROM or not NOTIFY_PASSWORD:
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[GeoMap] {subject}"
        msg["From"] = NOTIFY_FROM
        msg["To"] = NOTIFY_EMAIL
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
            smtp.login(NOTIFY_FROM, NOTIFY_PASSWORD)
            smtp.send_message(msg)
        log.info(f"Email enviat: {subject}")
    except Exception as e:
        log.warning(f"No s'ha pogut enviar l'email: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def check_credentials() -> bool:
    if not COPERNICUS_USER or not COPERNICUS_PASS:
        log.error("Falten COPERNICUS_USER / COPERNICUS_PASS. Configura-les al .env")
        return False
    return True


def pending_sentinel_dates(start: date, end: date) -> list[str]:
    """Retorna dates amb imatges descarregades però sense NDVI calculat."""
    from sqlalchemy import create_engine, text
    from app.core.config import settings

    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        processed = {
            row[0]
            for row in conn.execute(
                text("SELECT DISTINCT date::text FROM analytics.parcel_ndvi")
            )
        }

    available = {
        d.name
        for d in DATA_DIR.iterdir()
        if d.is_dir() and any(d.glob("*B04*.tif"))
    } if DATA_DIR.exists() else set()

    all_dates = []
    cur = start
    while cur <= end:
        ds = cur.isoformat()
        if ds in available and ds not in processed:
            all_dates.append(ds)
        cur += timedelta(days=1)
    return sorted(all_dates)


def new_ndvi_since_last_classification() -> bool:
    from sqlalchemy import create_engine, text
    from app.core.config import settings

    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        last_ndvi = conn.execute(text("SELECT MAX(date) FROM analytics.parcel_ndvi")).scalar()
        last_class = conn.execute(
            text("SELECT MAX(calculated_at)::date FROM analytics.parcel_status")
        ).scalar()

    if last_ndvi is None:
        return False
    if last_class is None:
        return True
    return last_ndvi > last_class


def get_classification_summary() -> str:
    from sqlalchemy import create_engine, text
    from app.core.config import settings

    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        parcels = conn.execute(text("SELECT COUNT(*) FROM core.parcel")).scalar()
        ndvi_parcels = conn.execute(
            text("SELECT COUNT(DISTINCT parcel_id) FROM analytics.parcel_ndvi")
        ).scalar()
        ndvi_dates = conn.execute(
            text("SELECT COUNT(DISTINCT date) FROM analytics.parcel_ndvi")
        ).scalar()
        rows = conn.execute(
            text("SELECT status, COUNT(*) FROM analytics.parcel_status GROUP BY status ORDER BY status")
        ).fetchall()

    lines = [
        f"Parcel·les totals : {parcels:,}",
        f"Amb NDVI          : {ndvi_parcels:,} ({ndvi_dates} dates)",
        "",
        "Classificació:",
    ]
    for status, count in rows:
        pct = count / parcels * 100 if parcels else 0
        lines.append(f"  {status:<15}: {count:>7,}  ({pct:.1f}%)")
    return "\n".join(lines)


# ── Passos del pipeline ───────────────────────────────────────────────────────

def step_download_sentinel(start: date, end: date) -> bool:
    log.info(f"[1/3] Cercant imatges Sentinel-2 del {start} al {end} (max {MAX_CLOUD}% núvols)...")
    from scripts.download_sentinel2 import get_token, search_products, download_bands

    if not check_credentials():
        return False

    try:
        get_token(COPERNICUS_USER, COPERNICUS_PASS)
    except Exception as e:
        log.error(f"Error d'autenticació Copernicus: {e}")
        return False

    products = search_products(start.isoformat(), end.isoformat(), MAX_CLOUD)
    if not products:
        log.info("  Cap imatge nova trobada.")
        return False

    total = len(products)
    log.info(f"  {total} imatges trobades. Iniciant descàrrega...")

    downloaded = 0
    errors = 0
    for i, product in enumerate(products, 1):
        name = product.get("Name", "?")[:50]
        pct = i / total * 100
        log.info(f"  [{i}/{total}] {pct:.0f}% — {name}")
        try:
            download_bands(product, COPERNICUS_USER, COPERNICUS_PASS)
            downloaded += 1
        except Exception as e:
            log.warning(f"  Error: {e}")
            errors += 1

    log.info(f"  Descàrrega completada: {downloaded} OK, {errors} errors de {total}.")
    return downloaded > 0


def step_calculate_ndvi(dates: list[str]) -> bool:
    if not dates:
        log.info("[2/3] No hi ha dates noves per calcular NDVI.")
        return False

    total = len(dates)
    log.info(f"[2/3] Calculant NDVI per a {total} data(es): {dates}")
    from sqlalchemy.orm import Session
    from sqlalchemy import create_engine
    from app.core.config import settings
    from scripts.calculate_ndvi import process_date

    engine = create_engine(settings.database_url)
    any_processed = False
    with Session(engine) as session:
        for i, d in enumerate(dates, 1):
            pct = i / total * 100
            log.info(f"  [{i}/{total}] {pct:.0f}% — Processant {d}...")
            try:
                process_date(d, session)
                any_processed = True
            except Exception as e:
                log.error(f"  Error calculant NDVI per {d}: {e}", exc_info=True)

    return any_processed


def step_classify() -> None:
    log.info("[3/3] Classificant parcel·les...")
    try:
        from scripts.classify_parcels import run_classification
        run_classification()
        log.info("  Classificació completada.")
    except Exception as e:
        log.error(f"  Error en la classificació: {e}", exc_info=True)


# ── Cicle principal ───────────────────────────────────────────────────────────

def run_cycle() -> None:
    start_time = datetime.now()
    log.info("=" * 60)
    log.info(f"Iniciant cicle — {start_time.strftime('%Y-%m-%d %H:%M')}")
    log.info("=" * 60)

    end_date = date.today()
    start_date = end_date - timedelta(days=LOOKBACK_DAYS)

    downloaded = step_download_sentinel(start_date, end_date)
    pending = pending_sentinel_dates(start_date, end_date)
    ndvi_updated = step_calculate_ndvi(pending)

    if ndvi_updated or new_ndvi_since_last_classification():
        step_classify()
    else:
        log.info("[3/3] Classificació al dia, res a fer.")

    elapsed = datetime.now() - start_time
    elapsed_str = str(elapsed).split(".")[0]  # HH:MM:SS sense microsegons

    log.info(f"Cicle acabat en {elapsed_str}. Proper cicle en {LOOP_INTERVAL_H:.0f}h.")

    if NOTIFY_EMAIL and (downloaded or ndvi_updated):
        summary = get_classification_summary()
        send_email(
            subject=f"Cicle completat ({elapsed_str})",
            body=(
                f"El pipeline de GeoMap ha acabat.\n"
                f"Durada: {elapsed_str}\n"
                f"Imatges noves: {'sí' if downloaded else 'no'}\n"
                f"NDVI actualitzat: {'sí' if ndvi_updated else 'no'}\n\n"
                f"{summary}\n\n"
                f"Proper cicle en {LOOP_INTERVAL_H:.0f}h."
            ),
        )


def show_status() -> None:
    from sqlalchemy import create_engine, text
    from app.core.config import settings

    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        sentinel_dirs = sorted(DATA_DIR.iterdir()) if DATA_DIR.exists() else []

    print("\n── Estat actual ─────────────────────────────────")
    print(get_classification_summary())
    print(f"  Imatges Sentinel-2 : {len(sentinel_dirs)} dates a {DATA_DIR}")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orquestrador pipeline geo_map")
    parser.add_argument("--once", action="store_true", help="Executa un cicle i surt")
    parser.add_argument("--status", action="store_true", help="Mostra estat i surt")
    args = parser.parse_args()

    if args.status:
        show_status()
        sys.exit(0)

    if args.once:
        run_cycle()
        sys.exit(0)

    log.info(f"Orquestrador iniciat. Interval: {LOOP_INTERVAL_H}h | Lookback: {LOOKBACK_DAYS} dies")
    while True:
        try:
            run_cycle()
        except Exception as e:
            log.error(f"Error inesperat al cicle: {e}", exc_info=True)
        time.sleep(LOOP_INTERVAL_H * 3600)

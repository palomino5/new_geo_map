"""
Classifica les parcel·les com activa | abandonada | desconeguda
basant-se en l'historial NDVI (v2.0).

Regles (v2.0 — variabilitat temporal + llindar absolut):
  activa     → variabilitat NDVI alta (std > 0.08) I pics > 0.3 en ≥2 de les últimes 4 imatges
               Distingeix cultius (NDVI fluctuant) de bosc (NDVI alt i estable)
  abandonada → ndvi_mean < 0.15 en totes les imatges dels últims 12 mesos (≥3 obs)
  desconeguda → bosc/matollar estable, dades insuficients, o ús SIGPAC no agrícola
"""

import os
import sys
from datetime import date, timedelta
from collections import defaultdict
from pathlib import Path
import statistics

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent / "backend" / ".env")

DATABASE_URL = os.getenv("DATABASE_URL") or (
    "postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}".format(
        user=os.getenv("POSTGRES_USER", "geomap"),
        pw=os.getenv("POSTGRES_PASSWORD", "changeme"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        db=os.getenv("POSTGRES_DB", "geomap"),
    )
)

ALGORITMO_VERSION = "v2.0"
NDVI_ACTIVA_THRESHOLD = 0.3
NDVI_ABANDONADA_THRESHOLD = 0.15
ACTIVA_MIN_OBSERVATIONS = 2
ACTIVA_LOOKBACK_COUNT = 4
ABANDONADA_LOOKBACK_MONTHS = 12
NON_AGRICULTURAL_USES = {"FO", "PA", "ED", "VI", "ZU", "AG"}  # usos no agrícoles SIGPAC

# Bosc/matollar: NDVI alt i estable → no és cultiu
STABLE_HIGH_NDVI_MEAN = 0.35   # mitjana mínima per considerar-ho vegetació permanent
STABLE_HIGH_NDVI_STD = 0.06    # desviació màxima per considerar-ho estable


def classify_parcel(ndvi_records: list[dict], uso_sigpac: str | None) -> tuple[str, float]:
    if uso_sigpac and uso_sigpac.upper() in NON_AGRICULTURAL_USES:
        return "desconeguda", 0.3

    if not ndvi_records:
        return "desconeguda", 0.0

    values = [r["ndvi_mean"] for r in ndvi_records if r["ndvi_mean"] is not None]
    if not values:
        return "desconeguda", 0.0

    # Detecta bosc/matollar: NDVI alt i poc variable en tot l'historial
    if len(values) >= 3:
        mean_all = statistics.mean(values)
        std_all = statistics.stdev(values) if len(values) > 1 else 0.0
        if mean_all >= STABLE_HIGH_NDVI_MEAN and std_all <= STABLE_HIGH_NDVI_STD:
            return "desconeguda", 0.25

    # Comprova activa: pics recents + variabilitat (cicle de cultiu)
    recent_4 = ndvi_records[-ACTIVA_LOOKBACK_COUNT:]
    recent_values = [r["ndvi_mean"] for r in recent_4 if r["ndvi_mean"] is not None]
    above_threshold = sum(1 for v in recent_values if v > NDVI_ACTIVA_THRESHOLD)

    if above_threshold >= ACTIVA_MIN_OBSERVATIONS:
        std_recent = statistics.stdev(recent_values) if len(recent_values) > 1 else 0.0
        # Exigim variabilitat mínima per descartar bosc estable
        if std_recent >= 0.05 or len(values) < 4:
            confidence = min(1.0, above_threshold / ACTIVA_LOOKBACK_COUNT + 0.2)
            return "activa", round(confidence, 3)

    # Comprova abandonada: NDVI consistentment baix els últims 12 mesos
    cutoff = date.today() - timedelta(days=ABANDONADA_LOOKBACK_MONTHS * 30)
    last_12m = [r for r in ndvi_records if r["date"] >= cutoff]

    if len(last_12m) >= 3:
        all_low = all(
            r["ndvi_mean"] is not None and r["ndvi_mean"] < NDVI_ABANDONADA_THRESHOLD
            for r in last_12m
        )
        if all_low:
            confidence = min(1.0, len(last_12m) / 8 + 0.3)
            return "abandonada", round(confidence, 3)

    return "desconeguda", 0.2 + min(0.3, len(ndvi_records) * 0.05)


def run_classification() -> None:
    engine = create_engine(DATABASE_URL)

    with Session(engine) as session:
        print("Carregant historial NDVI...")
        rows = session.execute(
            text("""
                SELECT p.id as parcel_id, p.uso_sigpac,
                       n.date, n.ndvi_mean
                FROM core.parcel p
                LEFT JOIN analytics.parcel_ndvi n ON n.parcel_id = p.id
                ORDER BY p.id, n.date
            """)
        ).fetchall()

        ndvi_by_parcel: dict[int, list[dict]] = defaultdict(list)
        uso_by_parcel: dict[int, str | None] = {}

        for parcel_id, uso_sigpac, ndvi_date, ndvi_mean in rows:
            uso_by_parcel[parcel_id] = uso_sigpac
            if ndvi_date is not None:
                ndvi_by_parcel[parcel_id].append({"date": ndvi_date, "ndvi_mean": ndvi_mean})

        print(f"Classificant {len(uso_by_parcel)} parcel·les...")
        batch = []
        for parcel_id, uso_sigpac in uso_by_parcel.items():
            records = ndvi_by_parcel.get(parcel_id, [])
            status, confidence = classify_parcel(records, uso_sigpac)
            batch.append({
                "parcel_id": parcel_id,
                "status": status,
                "confidence": confidence,
                "algoritmo_version": ALGORITMO_VERSION,
            })

        session.execute(
            text("""
                INSERT INTO analytics.parcel_status (parcel_id, status, confidence, algoritmo_version)
                VALUES (:parcel_id, CAST(:status AS analytics.parcel_status_enum), :confidence, :algoritmo_version)
                ON CONFLICT (parcel_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    confidence = EXCLUDED.confidence,
                    algoritmo_version = EXCLUDED.algoritmo_version,
                    calculated_at = NOW()
            """),
            batch,
        )
        session.commit()

    print(f"Classificació completada: {len(batch)} parcel·les.")


if __name__ == "__main__":
    run_classification()

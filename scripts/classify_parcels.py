"""
Classifica les parcel·les com activa | abandonada | desconeguda
basant-se en l'historial NDVI (v1.0).

Regles:
  activa     → ndvi_mean > 0.3 en ≥2 de les últimes 4 imatges
  abandonada → ndvi_mean < 0.15 en totes les imatges dels últims 12 mesos
  desconeguda → dades insuficients o ús SIGPAC no agrícola
"""

import os
import sys
from datetime import date, timedelta
from collections import defaultdict

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings  # noqa: E402

ALGORITMO_VERSION = "v1.0"
NDVI_ACTIVA_THRESHOLD = 0.3
NDVI_ABANDONADA_THRESHOLD = 0.15
ACTIVA_MIN_OBSERVATIONS = 2
ACTIVA_LOOKBACK_COUNT = 4
ABANDONADA_LOOKBACK_MONTHS = 12
NON_AGRICULTURAL_USES = {"FO", "PA", "ED", "VI", "ZU", "AG"}  # usos no agrícoles SIGPAC


def classify_parcel(ndvi_records: list[dict], uso_sigpac: str | None) -> tuple[str, float]:
    if uso_sigpac and uso_sigpac.upper() in NON_AGRICULTURAL_USES:
        return "desconeguda", 0.3

    if not ndvi_records:
        return "desconeguda", 0.0

    recent_4 = ndvi_records[-ACTIVA_LOOKBACK_COUNT:]
    above_threshold = sum(1 for r in recent_4 if r["ndvi_mean"] is not None and r["ndvi_mean"] > NDVI_ACTIVA_THRESHOLD)

    if above_threshold >= ACTIVA_MIN_OBSERVATIONS:
        confidence = min(1.0, above_threshold / ACTIVA_LOOKBACK_COUNT + 0.2)
        return "activa", round(confidence, 3)

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
    engine = create_engine(settings.database_url)

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

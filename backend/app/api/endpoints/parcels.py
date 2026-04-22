import json
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from geoalchemy2.functions import ST_AsGeoJSON, ST_MakeEnvelope, ST_Intersects, ST_SetSRID

from app.core.database import get_db
from app.models.parcel import Parcel
from app.models.analytics import ParcelStatus, ParcelStatusEnum
from app.schemas.parcel import (
    ParcelFeature,
    ParcelFeatureCollection,
    ParcelFeatureProperties,
    ParcelStatusFeature,
    ParcelStatusFeatureCollection,
    ParcelStatusProperties,
)

router = APIRouter()


@router.get("", response_model=ParcelFeatureCollection)
def list_parcels(
    municipality_id: int | None = Query(None),
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> ParcelFeatureCollection:
    query = db.query(Parcel, ST_AsGeoJSON(Parcel.geom).label("geojson"))

    if municipality_id is not None:
        query = query.filter(Parcel.municipality_id == municipality_id)

    if bbox:
        parts = bbox.split(",")
        if len(parts) != 4:
            raise HTTPException(status_code=400, detail="bbox must be: minLon,minLat,maxLon,maxLat")
        try:
            min_lon, min_lat, max_lon, max_lat = map(float, parts)
        except ValueError:
            raise HTTPException(status_code=400, detail="bbox values must be numeric")
        envelope = ST_SetSRID(ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat), 4326)
        query = query.filter(ST_Intersects(Parcel.geom, envelope))

    total = query.count()
    rows = query.limit(limit).all()

    features = [
        ParcelFeature(
            geometry=json.loads(row.geojson),
            properties=ParcelFeatureProperties.model_validate(row.Parcel),
        )
        for row in rows
    ]
    return ParcelFeatureCollection(features=features, total=total)


@router.get("/status", response_model=ParcelStatusFeatureCollection)
def list_parcel_status(
    status: ParcelStatusEnum | None = Query(None),
    municipality_id: int | None = Query(None),
    fecha: str | None = Query(None, description="Data màxima YYYY-MM-DD"),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> ParcelStatusFeatureCollection:
    latest_subq = (
        db.query(
            ParcelStatus.parcel_id,
            text("MAX(calculated_at) AS max_calculated_at"),
        )
        .group_by(ParcelStatus.parcel_id)
        .subquery()
    )

    query = (
        db.query(ParcelStatus, Parcel, ST_AsGeoJSON(Parcel.geom).label("geojson"))
        .join(Parcel, Parcel.id == ParcelStatus.parcel_id)
        .join(
            latest_subq,
            (latest_subq.c.parcel_id == ParcelStatus.parcel_id)
            & (latest_subq.c.max_calculated_at == ParcelStatus.calculated_at),
        )
    )

    if status is not None:
        query = query.filter(ParcelStatus.status == status)

    if municipality_id is not None:
        query = query.filter(Parcel.municipality_id == municipality_id)

    if fecha:
        query = query.filter(ParcelStatus.calculated_at <= fecha)

    total = query.count()
    rows = query.limit(limit).all()

    features = [
        ParcelStatusFeature(
            geometry=json.loads(row.geojson),
            properties=ParcelStatusProperties(
                parcel_id=row.ParcelStatus.parcel_id,
                ref_catastral=row.Parcel.ref_catastral,
                status=row.ParcelStatus.status.value,
                confidence=row.ParcelStatus.confidence,
                algoritmo_version=row.ParcelStatus.algoritmo_version,
                calculated_at=str(row.ParcelStatus.calculated_at) if row.ParcelStatus.calculated_at else None,
            ),
        )
        for row in rows
    ]
    return ParcelStatusFeatureCollection(features=features, total=total)

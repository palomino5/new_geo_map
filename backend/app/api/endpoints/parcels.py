import json
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from geoalchemy2.functions import ST_AsGeoJSON, ST_MakeEnvelope, ST_Intersects, ST_SetSRID
from pydantic import BaseModel

from app.core.auth import get_optional_user
from app.core.database import get_db
from app.models.parcel import Parcel
from app.models.municipality import Municipality
from app.models.analytics import ParcelStatus, ParcelStatusEnum, ParcelNdvi
from app.models.user import FREE_DAILY_LIMIT, User
from app.schemas.parcel import (
    ParcelFeature,
    ParcelFeatureCollection,
    ParcelFeatureProperties,
    ParcelStatusFeature,
    ParcelStatusFeatureCollection,
    ParcelStatusProperties,
)

router = APIRouter()


class NdviPoint(BaseModel):
    date: str
    ndvi_mean: float
    ndvi_min: float | None
    ndvi_max: float | None


class ParcelDetail(BaseModel):
    ref_catastral: str
    municipality_name: str
    status: str
    confidence: float
    superficie_ha: float | None
    uso_sigpac: str | None
    calculated_at: str | None
    ndvi_history: list[NdviPoint]


class ParcelPublic(BaseModel):
    ref_catastral: str
    municipality_name: str
    status: str
    confidence: float
    superficie_ha: float | None
    uso_sigpac: str | None
    calculated_at: str | None
    ndvi_preview: list[NdviPoint]   # últims 3 punts
    ndvi_total_count: int           # total real, per mostrar "X observacions (veure totes)"


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
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    fecha: str | None = Query(None, description="Data màxima YYYY-MM-DD"),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> ParcelStatusFeatureCollection:
    latest_subq = (
        db.query(
            ParcelStatus.parcel_id,
            func.max(ParcelStatus.calculated_at).label("max_calculated_at"),
        )
        .group_by(ParcelStatus.parcel_id)
        .subquery()
    )

    # LEFT JOIN: retorna totes les parcel·les, classificades o no
    query = (
        db.query(Parcel, ST_AsGeoJSON(Parcel.geom).label("geojson"), ParcelStatus)
        .outerjoin(latest_subq, latest_subq.c.parcel_id == Parcel.id)
        .outerjoin(
            ParcelStatus,
            (ParcelStatus.parcel_id == Parcel.id)
            & (ParcelStatus.calculated_at == latest_subq.c.max_calculated_at),
        )
    )

    if status is not None:
        query = query.filter(ParcelStatus.status == status)

    if municipality_id is not None:
        query = query.filter(Parcel.municipality_id == municipality_id)

    if bbox:
        parts = bbox.split(",")
        if len(parts) == 4:
            try:
                min_lon, min_lat, max_lon, max_lat = map(float, parts)
                envelope = ST_SetSRID(ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat), 4326)
                query = query.filter(ST_Intersects(Parcel.geom, envelope))
            except ValueError:
                raise HTTPException(status_code=400, detail="bbox values must be numeric")

    if fecha:
        query = query.filter(ParcelStatus.calculated_at <= fecha)

    total = query.count()
    rows = query.limit(limit).all()

    features = [
        ParcelStatusFeature(
            geometry=json.loads(row.geojson),
            properties=ParcelStatusProperties(
                parcel_id=row.Parcel.id,
                ref_catastral=row.Parcel.ref_catastral,
                status=row.ParcelStatus.status.value if row.ParcelStatus else "desconeguda",
                confidence=row.ParcelStatus.confidence if row.ParcelStatus else 0.0,
                algoritmo_version=row.ParcelStatus.algoritmo_version if row.ParcelStatus else None,
                calculated_at=str(row.ParcelStatus.calculated_at) if row.ParcelStatus and row.ParcelStatus.calculated_at else None,
            ),
        )
        for row in rows
    ]
    return ParcelStatusFeatureCollection(features=features, total=total)


@router.get("/{ref_catastral}/public", response_model=ParcelPublic)
def get_parcel_public(
    ref_catastral: str,
    db: Session = Depends(get_db),
) -> ParcelPublic:
    parcel = db.query(Parcel).filter(Parcel.ref_catastral == ref_catastral).first()
    if not parcel:
        raise HTTPException(status_code=404, detail="Parcel·la no trobada")

    municipality = db.query(Municipality).filter(Municipality.id == parcel.municipality_id).first()
    status_row = (
        db.query(ParcelStatus)
        .filter(ParcelStatus.parcel_id == parcel.id)
        .order_by(ParcelStatus.calculated_at.desc())
        .first()
    )
    ndvi_rows = (
        db.query(ParcelNdvi)
        .filter(ParcelNdvi.parcel_id == parcel.id)
        .order_by(ParcelNdvi.date.desc())
        .all()
    )
    preview = ndvi_rows[:3]

    return ParcelPublic(
        ref_catastral=parcel.ref_catastral,
        municipality_name=municipality.name if municipality else "",
        status=status_row.status.value if status_row else "desconeguda",
        confidence=status_row.confidence if status_row else 0.0,
        superficie_ha=parcel.superficie_ha,
        uso_sigpac=parcel.uso_sigpac,
        calculated_at=str(status_row.calculated_at) if status_row else None,
        ndvi_preview=[
            NdviPoint(
                date=str(r.date),
                ndvi_mean=round(r.ndvi_mean, 4),
                ndvi_min=round(r.ndvi_min, 4) if r.ndvi_min is not None else None,
                ndvi_max=round(r.ndvi_max, 4) if r.ndvi_max is not None else None,
            )
            for r in preview
        ],
        ndvi_total_count=len(ndvi_rows),
    )


@router.get("/{ref_catastral}", response_model=ParcelDetail)
def get_parcel_detail(
    ref_catastral: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> ParcelDetail:
    # Comprova límit freemium
    if current_user is None:
        raise HTTPException(status_code=401, detail="Cal iniciar sessió per consultar detalls")
    if not current_user.consume_query():
        raise HTTPException(
            status_code=429,
            detail=f"Has arribat al límit de {FREE_DAILY_LIMIT} consultes diàries del pla Free. Fes upgrade per continuar.",
        )
    db.commit()
    parcel = db.query(Parcel).filter(Parcel.ref_catastral == ref_catastral).first()
    if not parcel:
        raise HTTPException(status_code=404, detail="Parcel·la no trobada")

    municipality = db.query(Municipality).filter(Municipality.id == parcel.municipality_id).first()

    status_row = (
        db.query(ParcelStatus)
        .filter(ParcelStatus.parcel_id == parcel.id)
        .order_by(ParcelStatus.calculated_at.desc())
        .first()
    )

    ndvi_rows = (
        db.query(ParcelNdvi)
        .filter(ParcelNdvi.parcel_id == parcel.id)
        .order_by(ParcelNdvi.date.asc())
        .all()
    )

    return ParcelDetail(
        ref_catastral=parcel.ref_catastral,
        municipality_name=municipality.name if municipality else "",
        status=status_row.status.value if status_row else "desconeguda",
        confidence=status_row.confidence if status_row else 0.0,
        superficie_ha=parcel.superficie_ha,
        uso_sigpac=parcel.uso_sigpac,
        calculated_at=str(status_row.calculated_at) if status_row else None,
        ndvi_history=[
            NdviPoint(
                date=str(r.date),
                ndvi_mean=round(r.ndvi_mean, 4),
                ndvi_min=round(r.ndvi_min, 4) if r.ndvi_min is not None else None,
                ndvi_max=round(r.ndvi_max, 4) if r.ndvi_max is not None else None,
            )
            for r in ndvi_rows
        ],
    )

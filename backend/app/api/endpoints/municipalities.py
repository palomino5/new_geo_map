import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from geoalchemy2.functions import ST_AsGeoJSON, ST_SimplifyPreserveTopology

from app.core.database import get_db
from app.models.municipality import Municipality
from app.schemas.municipality import MunicipalityBase, MunicipalityList

router = APIRouter()


@router.get("", response_model=MunicipalityList)
def list_municipalities(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=5000),
    province: str | None = Query(None),
    db: Session = Depends(get_db),
) -> MunicipalityList:
    query = db.query(Municipality)
    if province:
        query = query.filter(Municipality.province.ilike(f"%{province}%"))
    total = query.count()
    items = query.order_by(Municipality.name).offset(skip).limit(limit).all()
    return MunicipalityList(items=[MunicipalityBase.model_validate(m) for m in items], total=total)


@router.get("/geojson")
def municipalities_geojson(
    province: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    # Simplifica geometria per reduir mida de resposta (~0.5 km tolerància)
    query = db.query(
        Municipality.id,
        Municipality.name,
        Municipality.code_ine,
        Municipality.province,
        ST_AsGeoJSON(
            ST_SimplifyPreserveTopology(Municipality.geom, 0.005)
        ).label("geojson"),
    )
    if province:
        query = query.filter(Municipality.province.ilike(f"%{province}%"))

    features = [
        {
            "type": "Feature",
            "geometry": json.loads(row.geojson),
            "properties": {
                "id": row.id,
                "name": row.name,
                "code_ine": row.code_ine,
                "province": row.province,
            },
        }
        for row in query.all()
    ]
    return {"type": "FeatureCollection", "features": features}

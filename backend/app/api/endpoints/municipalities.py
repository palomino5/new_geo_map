from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

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

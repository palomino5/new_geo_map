from fastapi import APIRouter

from app.api.endpoints import municipalities, parcels

api_router = APIRouter()

api_router.include_router(municipalities.router, prefix="/municipalities", tags=["municipalities"])
api_router.include_router(parcels.router, prefix="/parcels", tags=["parcels"])

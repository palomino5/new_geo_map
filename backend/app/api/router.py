from fastapi import APIRouter

from app.api.endpoints import auth, municipalities, parcels

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(municipalities.router, prefix="/municipalities", tags=["municipalities"])
api_router.include_router(parcels.router, prefix="/parcels", tags=["parcels"])

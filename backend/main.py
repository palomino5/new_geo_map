import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router

app = FastAPI(
    title="new_geo_map API",
    description="API per consultar l'estat dels camps de Catalunya",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    # Separats per comes. En producció el frontend i l'API comparteixen origen (nginx), CORS no cal
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router)

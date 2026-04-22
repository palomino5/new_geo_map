from typing import Any
from pydantic import BaseModel


class ParcelFeatureProperties(BaseModel):
    id: int
    ref_catastral: str
    municipality_id: int
    superficie_ha: float | None = None
    uso_sigpac: str | None = None

    model_config = {"from_attributes": True}


class ParcelFeature(BaseModel):
    type: str = "Feature"
    geometry: dict[str, Any]
    properties: ParcelFeatureProperties


class ParcelFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[ParcelFeature]
    total: int


class ParcelStatusProperties(BaseModel):
    parcel_id: int
    ref_catastral: str
    status: str
    confidence: float
    algoritmo_version: str
    calculated_at: str | None = None

    model_config = {"from_attributes": True}


class ParcelStatusFeature(BaseModel):
    type: str = "Feature"
    geometry: dict[str, Any]
    properties: ParcelStatusProperties


class ParcelStatusFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[ParcelStatusFeature]
    total: int

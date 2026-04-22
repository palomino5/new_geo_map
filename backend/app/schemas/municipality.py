from pydantic import BaseModel


class MunicipalityBase(BaseModel):
    id: int
    name: str
    code_ine: str
    province: str | None = None
    area_km2: float | None = None

    model_config = {"from_attributes": True}


class MunicipalityList(BaseModel):
    items: list[MunicipalityBase]
    total: int

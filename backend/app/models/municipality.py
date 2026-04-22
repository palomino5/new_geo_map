from sqlalchemy import Column, Integer, String, Float
from geoalchemy2 import Geometry

from app.core.database import Base


class Municipality(Base):
    __tablename__ = "municipality"
    __table_args__ = {"schema": "core"}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    code_ine = Column(String(10), unique=True, nullable=False)
    province = Column(String(100))
    area_km2 = Column(Float)
    geom = Column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True), nullable=False)

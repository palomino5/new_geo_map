from sqlalchemy import Column, Integer, String, Float, ForeignKey
from geoalchemy2 import Geometry

from app.core.database import Base


class Parcel(Base):
    __tablename__ = "parcel"
    __table_args__ = {"schema": "core"}

    id = Column(Integer, primary_key=True, index=True)
    ref_catastral = Column(String(20), unique=True, nullable=False, index=True)
    municipality_id = Column(Integer, ForeignKey("core.municipality.id"), nullable=False, index=True)
    superficie_ha = Column(Float)
    uso_sigpac = Column(String(10))
    geom = Column(Geometry("POLYGON", srid=4326, spatial_index=True), nullable=False)

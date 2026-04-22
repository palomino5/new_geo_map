import enum
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func

from app.core.database import Base


class ParcelStatusEnum(str, enum.Enum):
    activa = "activa"
    abandonada = "abandonada"
    desconeguda = "desconeguda"


class ParcelNdvi(Base):
    __tablename__ = "parcel_ndvi"
    __table_args__ = {"schema": "analytics"}

    id = Column(Integer, primary_key=True, index=True)
    parcel_id = Column(Integer, ForeignKey("core.parcel.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    ndvi_mean = Column(Float)
    ndvi_min = Column(Float)
    ndvi_max = Column(Float)
    ndvi_std = Column(Float)
    cloud_cover_pct = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ParcelStatus(Base):
    __tablename__ = "parcel_status"
    __table_args__ = {"schema": "analytics"}

    id = Column(Integer, primary_key=True, index=True)
    parcel_id = Column(Integer, ForeignKey("core.parcel.id"), nullable=False, index=True)
    status = Column(Enum(ParcelStatusEnum, schema="analytics"), nullable=False)
    confidence = Column(Float, default=0.0)
    algoritmo_version = Column(String(20), default="v1.0")
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

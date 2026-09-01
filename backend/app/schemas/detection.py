from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GeoCoordinate(BaseModel):
    latitude: float
    longitude: float


class ImageCoordinate(BaseModel):
    x: float
    y: float


class PolygonGeometry(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[list[float]]] = Field(default_factory=list)


class DetectionRequest(BaseModel):
    image_path: str | None = None


class DetectionResponse(BaseModel):
    status: str
    spill_detected: bool | None = None
    spill_id: str | None = None
    detected_at: datetime | None = None
    area_pixels: float | None = None
    perimeter_pixels: float | None = None
    centroid: ImageCoordinate | None = None
    polygon: PolygonGeometry | None = None
    confidence: float | None = None
    model: str | None = None
    model_dataset_type: str | None = None
    image_size: int | None = None
    message: str | None = None

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.detection import GeoCoordinate


class DriftRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    timestamp: datetime
    backward_hours: int | None = Field(default=None, ge=1, le=168)
    forward_hours: int | None = Field(default=None, ge=1, le=168)
    particle_count: int | None = Field(default=None, ge=1, le=5000)
    environment_mode: Literal["synthetic_dev", "real_data"] | None = None
    mode: Literal["synthetic_dev", "real_data"] | None = None


class OriginWindow(BaseModel):
    start: datetime
    end: datetime


class LineStringGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]] = Field(default_factory=list)


class PolygonGeometry(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[list[float]]] = Field(default_factory=list)


class DriftMetadata(BaseModel):
    backward_hours: int
    forward_hours: int
    particle_count: int
    time_step_minutes: int
    windage_factor: float
    backward_path_direction: str = "detection_to_past"
    forward_path_direction: str = "detection_to_future"
    particles_requested: int | None = None
    backward_particles_active: int | None = None
    backward_particles_beached: int | None = None
    forward_particles_active: int | None = None
    forward_particles_beached: int | None = None
    nearest_current_substitution_count: int | None = None
    nearest_current_substitutions: list[dict[str, object]] = Field(default_factory=list)
    max_nearest_current_distance_km: float | None = None
    max_actual_substitution_distance_km: float | None = None


class DriftResponse(BaseModel):
    status: str
    mode: str | None = None
    environment: str | None = None
    engine: str | None = None
    input: DriftRequest | None = None
    origin: GeoCoordinate | None = None
    origin_centroid: GeoCoordinate | None = None
    origin_area: PolygonGeometry | None = None
    origin_time_window: OriginWindow | None = None
    backward_path: LineStringGeometry | None = None
    forward_path: LineStringGeometry | None = None
    metadata: DriftMetadata | None = None
    environmental_forcing: dict[str, object] | None = None
    message: str | None = None

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.detection import GeoCoordinate
from app.schemas.drift import OriginWindow


class ScoreRequest(BaseModel):
    origin_time_window: OriginWindow
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    origin_centroid: GeoCoordinate | None = None
    mode: Literal["synthetic_dev", "real_data"] | None = None
    candidate_radius_km: float | None = Field(default=None, gt=0, le=500)
    time_buffer_hours: float | None = Field(default=None, ge=0, le=72)

    @model_validator(mode="after")
    def require_origin_coordinate(self) -> "ScoreRequest":
        has_legacy_coordinate = self.latitude is not None and self.longitude is not None
        if self.origin_centroid is None and not has_legacy_coordinate:
            raise ValueError("Provide origin_centroid or both latitude and longitude.")
        return self

    @property
    def origin_latitude(self) -> float:
        return self.origin_centroid.latitude if self.origin_centroid else float(self.latitude)

    @property
    def origin_longitude(self) -> float:
        return self.origin_centroid.longitude if self.origin_centroid else float(self.longitude)


class VesselScoreFactors(BaseModel):
    proximity: float
    temporal_proximity: float = 0.0
    trajectory_alignment: float
    speed_anomaly: float
    course_anomaly: float = 0.0
    ais_gap: float


class AISTrajectoryPoint(BaseModel):
    timestamp: datetime
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    sog: float | None = None
    cog: float | None = None
    heading: float | None = None


class VesselScore(BaseModel):
    rank: int | None = None
    mmsi: str
    vessel_name: str
    score: float
    priority: str | None = None
    minimum_distance_km: float | None = None
    nearest_approach_time: datetime | None = None
    factors: VesselScoreFactors
    reasons: list[str]
    trajectory: list[AISTrajectoryPoint] = Field(default_factory=list)
    trajectory_source: str | None = None


class ScoreResponse(BaseModel):
    status: str
    mode: str | None = None
    environment: str | None = None
    scenario: str | None = None
    candidate_count: int | None = None
    temporal_filter: dict[str, object] | None = None
    spatial_filter: dict[str, object] | None = None
    suspects: list[VesselScore]
    message: str | None = None

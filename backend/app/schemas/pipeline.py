from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.detection import DetectionResponse, GeoCoordinate
from app.schemas.drift import DriftResponse
from app.schemas.scoring import ScoreResponse, VesselScore


class SpillSeed(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    timestamp: datetime


class PipelineRequest(BaseModel):
    pipeline_mode: Literal["detection_only", "demo", "real_validation"] = "detection_only"
    image_path: str | None = None
    spill_seed: SpillSeed | None = None
    detection_mode: Literal["deep_sar_sos", "synthetic_dev"] | None = "deep_sar_sos"
    drift_mode: Literal["synthetic_dev", "real_data"] = "real_data"
    drift_engine: Literal["development_drift_engine", "opendrift_openoil"] | None = None
    drift_forcing_strategy: Literal["native_grid", "constant_sample"] | None = None
    attribution_mode: Literal["synthetic_dev", "real_data"] = "synthetic_dev"
    persist: bool = True


class PipelineSummary(BaseModel):
    spill_detected: bool | None = None
    origin_centroid: GeoCoordinate | None = None
    candidate_vessels: int | None = None
    top_candidate: VesselScore | None = None


class PersistenceStatus(BaseModel):
    status: str
    reason: str | None = None


class PipelineResponse(BaseModel):
    status: str
    incident_id: str
    scenario: str
    data_provenance: dict[str, str]
    detection: DetectionResponse
    drift: DriftResponse | None = None
    attribution: ScoreResponse | None = None
    summary: PipelineSummary
    timings_ms: dict[str, float]
    persistence: PersistenceStatus
    failed_stage: str | None = None
    message: str | None = None


class IncidentSummary(BaseModel):
    incident_id: str
    created_at: datetime | None = None
    scenario: str | None = None
    status: str | None = None
    pipeline_mode: str | None = None
    provenance: dict[str, object] | None = None


class IncidentDetail(BaseModel):
    status: str
    incident: dict[str, object] | None = None
    detection: dict[str, object] | None = None
    drift: dict[str, object] | None = None
    vessel_candidates: list[dict[str, object]] = Field(default_factory=list)
    message: str | None = None


class IncidentListResponse(BaseModel):
    status: str
    incidents: list[IncidentSummary] = Field(default_factory=list)
    message: str | None = None


class VesselCandidatesResponse(BaseModel):
    status: str
    incident_id: str
    vessels: list[dict[str, object]] = Field(default_factory=list)
    message: str | None = None

from uuid import UUID

from fastapi import APIRouter

from app.db import repository
from app.db.connection import DatabaseUnavailableError, check_database_status
from app.modules.attribution.service import score_suspect_vessels
from app.modules.detection.service import detect_oil_spill
from app.modules.drift.service import estimate_drift
from app.modules.pipeline.service import execute_pipeline
from app.schemas.drift import DriftRequest, DriftResponse
from app.schemas.pipeline import (
    IncidentDetail,
    IncidentListResponse,
    PipelineRequest,
    PipelineResponse,
    VesselCandidatesResponse,
)
from app.schemas.scoring import ScoreRequest, ScoreResponse
from app.schemas.detection import DetectionRequest, DetectionResponse

router = APIRouter()


@router.get("/")
def read_root() -> dict[str, str]:
    return {
        "service": "Marine Oil Spill Intelligence API",
        "problem_statement": "PS 26143",
        "message": "API documentation is available at /docs",
    }


@router.get("/health")
def health_check() -> dict[str, object]:
    database_status, _ = check_database_status()
    return {
        "status": "healthy",
        "service": "marine-oil-spill-intelligence-api",
        "problem_statement": "PS 26143",
        "version": "0.1.0",
        "database": {
            "status": database_status,
            "message": None if database_status == "connected" else "Database is not available.",
        },
    }


@router.post("/detect", response_model=DetectionResponse)
def detect(request: DetectionRequest | None = None) -> DetectionResponse:
    return detect_oil_spill(request)


@router.post("/drift", response_model=DriftResponse)
def drift(request: DriftRequest) -> DriftResponse:
    return estimate_drift(request)


@router.post("/score", response_model=ScoreResponse)
def score(request: ScoreRequest) -> ScoreResponse:
    return score_suspect_vessels(request)


@router.post("/pipeline", response_model=PipelineResponse)
def pipeline(request: PipelineRequest | None = None) -> PipelineResponse:
    return execute_pipeline(request)


@router.get("/incidents", response_model=IncidentListResponse)
def incidents() -> IncidentListResponse:
    try:
        return IncidentListResponse(status="success", incidents=repository.list_incidents())
    except DatabaseUnavailableError:
        return IncidentListResponse(
            status="persistence_unavailable",
            incidents=[],
            message="Database is not available.",
        )


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
def incident_detail(incident_id: str) -> IncidentDetail:
    if not _is_uuid(incident_id):
        return IncidentDetail(status="not_found", message="Incident was not found.")
    try:
        result = repository.get_incident(incident_id)
    except DatabaseUnavailableError:
        return IncidentDetail(status="persistence_unavailable", message="Database is not available.")
    if result is None:
        return IncidentDetail(status="not_found", message="Incident was not found.")
    return IncidentDetail(status="success", **result)


@router.get("/incidents/{incident_id}/vessels", response_model=VesselCandidatesResponse)
def incident_vessels(incident_id: str) -> VesselCandidatesResponse:
    if not _is_uuid(incident_id):
        return VesselCandidatesResponse(status="not_found", incident_id=incident_id, message="Incident was not found.")
    try:
        vessels = repository.get_vessel_candidates_for_incident(incident_id)
    except DatabaseUnavailableError:
        return VesselCandidatesResponse(
            status="persistence_unavailable",
            incident_id=incident_id,
            message="Database is not available.",
        )
    return VesselCandidatesResponse(status="success", incident_id=incident_id, vessels=vessels)


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False

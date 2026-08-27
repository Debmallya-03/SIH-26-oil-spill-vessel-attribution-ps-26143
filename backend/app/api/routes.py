from fastapi import APIRouter

from app.modules.attribution.service import score_suspect_vessels
from app.modules.detection.service import detect_oil_spill
from app.modules.drift.service import estimate_drift
from app.schemas.drift import DriftRequest, DriftResponse
from app.schemas.pipeline import PipelineResponse
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
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "marine-oil-spill-intelligence-api",
        "problem_statement": "PS 26143",
        "version": "0.1.0",
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
def pipeline() -> PipelineResponse:
    detection = detect_oil_spill()
    return PipelineResponse(
        status=detection.status if detection.status != "success" else "detection_only",
        detection=detection,
        drift=None,
        attribution=None,
        message="Pipeline drift requires georeferenced spill latitude/longitude; synthetic detection returns image pixels only.",
    )

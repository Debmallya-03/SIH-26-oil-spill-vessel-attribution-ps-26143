from pydantic import BaseModel

from app.schemas.detection import DetectionResponse
from app.schemas.drift import DriftResponse
from app.schemas.scoring import ScoreResponse


class PipelineResponse(BaseModel):
    status: str
    detection: DetectionResponse
    drift: DriftResponse | None = None
    attribution: ScoreResponse | None = None
    message: str | None = None

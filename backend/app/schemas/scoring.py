from pydantic import BaseModel

from app.schemas.drift import OriginWindow


class ScoreRequest(BaseModel):
    origin_time_window: OriginWindow
    latitude: float
    longitude: float


class VesselScoreFactors(BaseModel):
    proximity: float
    trajectory_alignment: float
    speed_anomaly: float
    ais_gap: float


class VesselScore(BaseModel):
    mmsi: str
    vessel_name: str
    score: float
    factors: VesselScoreFactors
    reasons: list[str]


class ScoreResponse(BaseModel):
    status: str
    suspects: list[VesselScore]

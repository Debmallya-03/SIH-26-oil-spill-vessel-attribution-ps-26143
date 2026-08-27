from app.schemas.scoring import (
    ScoreRequest,
    ScoreResponse,
    VesselScore,
    VesselScoreFactors,
)


def score_suspect_vessels(request: ScoreRequest) -> ScoreResponse:
    return ScoreResponse(
        status="success",
        suspects=[
            VesselScore(
                mmsi="419000001",
                vessel_name="Demo Vessel Alpha",
                score=87.4,
                factors=VesselScoreFactors(
                    proximity=0.92,
                    trajectory_alignment=0.84,
                    speed_anomaly=0.71,
                    ais_gap=0.80,
                ),
                reasons=[
                    "Passed close to estimated origin",
                    "Course changed near origin window",
                    "AIS transmission gap detected",
                ],
            )
        ],
    )

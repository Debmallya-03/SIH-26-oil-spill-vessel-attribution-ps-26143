from dataclasses import dataclass

from app.modules.attribution.features import VesselFeatures


WEIGHTS = {
    "proximity": 0.30,
    "temporal_proximity": 0.20,
    "trajectory_alignment": 0.15,
    "speed_anomaly": 0.15,
    "course_anomaly": 0.10,
    "ais_gap": 0.10,
}


@dataclass(frozen=True)
class CompositeScore:
    total: float
    priority: str
    factors: dict[str, float]
    reasons: list[str]


def score_vessel(features: VesselFeatures, weights: dict[str, float] | None = None) -> CompositeScore:
    active_weights = weights or WEIGHTS
    factors = {
        "proximity": features.proximity.value,
        "temporal_proximity": features.temporal_proximity.value,
        "trajectory_alignment": features.trajectory_alignment.value,
        "speed_anomaly": features.speed_anomaly.value,
        "course_anomaly": features.course_anomaly.value,
        "ais_gap": features.ais_gap.value,
    }
    total = round(sum(factors[name] * active_weights[name] for name in active_weights) * 100, 1)
    reasons: list[str] = []
    for result in (
        features.proximity,
        features.temporal_proximity,
        features.trajectory_alignment,
        features.speed_anomaly,
        features.course_anomaly,
        features.ais_gap,
    ):
        reasons.extend(result.reasons)

    return CompositeScore(total=total, priority=priority_label(total), factors=factors, reasons=reasons)


def priority_label(score: float) -> str:
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.modules.attribution.geometry import bearing_degrees, circular_angle_difference_degrees
from app.modules.attribution.trajectory import VesselTrack, nearest_point_to_origin


@dataclass(frozen=True)
class FeatureResult:
    value: float
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class VesselFeatures:
    proximity: FeatureResult
    temporal_proximity: FeatureResult
    trajectory_alignment: FeatureResult
    speed_anomaly: FeatureResult
    course_anomaly: FeatureResult
    ais_gap: FeatureResult
    nearest_approach_time: datetime
    minimum_distance_km: float


def extract_features(
    track: VesselTrack,
    origin_latitude: float,
    origin_longitude: float,
    window_start: datetime,
    window_end: datetime,
    candidate_radius_km: float,
    time_buffer_hours: float,
    ais_gap_threshold_minutes: float,
) -> VesselFeatures:
    nearest_point, minimum_distance_km, nearest_index = nearest_point_to_origin(
        track,
        origin_latitude,
        origin_longitude,
    )
    return VesselFeatures(
        proximity=score_proximity(minimum_distance_km, candidate_radius_km),
        temporal_proximity=score_temporal_proximity(
            nearest_point.timestamp,
            window_start,
            window_end,
            time_buffer_hours,
        ),
        trajectory_alignment=score_trajectory_alignment(track, nearest_index, origin_latitude, origin_longitude),
        speed_anomaly=score_speed_anomaly(track, nearest_index),
        course_anomaly=score_course_anomaly(track, nearest_index),
        ais_gap=score_ais_gap(track, window_start, window_end, time_buffer_hours, ais_gap_threshold_minutes),
        nearest_approach_time=nearest_point.timestamp,
        minimum_distance_km=minimum_distance_km,
    )


def score_proximity(distance_km: float, candidate_radius_km: float) -> FeatureResult:
    if distance_km <= 2:
        score = 1.0
    elif distance_km <= 5:
        score = 0.8 + (5 - distance_km) / 3 * 0.2
    elif distance_km <= 10:
        score = 0.45 + (10 - distance_km) / 5 * 0.35
    else:
        score = max(0.0, (candidate_radius_km - distance_km) / max(candidate_radius_km - 10, 1) * 0.45)
    return FeatureResult(
        value=round(min(1.0, max(0.0, score)), 4),
        reasons=[f"Closest approach: {distance_km:.2f} km from estimated origin."],
        metadata={"minimum_distance_km": distance_km},
    )


def score_temporal_proximity(
    nearest_time: datetime,
    window_start: datetime,
    window_end: datetime,
    time_buffer_hours: float,
) -> FeatureResult:
    if window_start <= nearest_time <= window_end:
        return FeatureResult(
            value=1.0,
            reasons=["Nearest approach occurred inside origin time window."],
            metadata={"nearest_approach_time": nearest_time.isoformat()},
        )

    if nearest_time < window_start:
        delta = window_start - nearest_time
    else:
        delta = nearest_time - window_end
    buffer = timedelta(hours=time_buffer_hours)
    score = max(0.0, 1 - delta.total_seconds() / max(buffer.total_seconds(), 1))
    return FeatureResult(
        value=round(score, 4),
        reasons=[f"Nearest approach was {delta.total_seconds() / 60:.0f} minutes outside origin time window."],
        metadata={"nearest_approach_time": nearest_time.isoformat()},
    )


def score_trajectory_alignment(
    track: VesselTrack,
    nearest_index: int,
    origin_latitude: float,
    origin_longitude: float,
) -> FeatureResult:
    if nearest_index <= 0 or nearest_index >= len(track.points) - 1:
        return FeatureResult(value=0.25, reasons=["Limited points around nearest approach for trajectory alignment."])

    before = track.points[nearest_index - 1]
    after = track.points[nearest_index + 1]
    track_bearing = bearing_degrees(before.latitude, before.longitude, after.latitude, after.longitude)
    inbound = bearing_degrees(before.latitude, before.longitude, origin_latitude, origin_longitude)
    outbound = bearing_degrees(origin_latitude, origin_longitude, after.latitude, after.longitude)
    alignment_error = min(
        circular_angle_difference_degrees(track_bearing, inbound),
        circular_angle_difference_degrees(track_bearing, outbound),
    )
    score = max(0.0, 1 - alignment_error / 90)
    return FeatureResult(
        value=round(score, 4),
        reasons=[f"Trajectory alignment error near origin: {alignment_error:.0f} degrees."],
        metadata={"track_bearing": track_bearing, "alignment_error_degrees": alignment_error},
    )


def score_speed_anomaly(track: VesselTrack, nearest_index: int) -> FeatureResult:
    start = max(0, nearest_index - 3)
    end = min(len(track.points), nearest_index + 4)
    local = track.points[start:end]
    if len(local) < 3:
        return FeatureResult(value=0.0)

    max_speed = max(point.sog for point in local)
    min_speed = min(point.sog for point in local)
    if max_speed <= 0:
        return FeatureResult(value=0.0)
    drop_fraction = (max_speed - min_speed) / max_speed
    score = min(1.0, max(0.0, drop_fraction / 0.7))
    reasons = []
    if score >= 0.2:
        reasons.append(f"Speed varied from {max_speed:.1f} kn to {min_speed:.1f} kn near origin.")
    return FeatureResult(
        value=round(score, 4),
        reasons=reasons,
        metadata={"max_sog": max_speed, "min_sog": min_speed, "drop_fraction": drop_fraction},
    )


def score_course_anomaly(track: VesselTrack, nearest_index: int) -> FeatureResult:
    start = max(0, nearest_index - 3)
    end = min(len(track.points), nearest_index + 4)
    local = track.points[start:end]
    if len(local) < 2:
        return FeatureResult(value=0.0)

    max_change = max(
        circular_angle_difference_degrees(local[index - 1].cog, local[index].cog)
        for index in range(1, len(local))
    )
    score = min(1.0, max_change / 90)
    reasons = []
    if max_change >= 20:
        reasons.append(f"Course changed by {max_change:.0f} degrees near origin.")
    return FeatureResult(value=round(score, 4), reasons=reasons, metadata={"max_course_change_degrees": max_change})


def score_ais_gap(
    track: VesselTrack,
    window_start: datetime,
    window_end: datetime,
    time_buffer_hours: float,
    threshold_minutes: float,
) -> FeatureResult:
    relevant_start = window_start - timedelta(hours=time_buffer_hours)
    relevant_end = window_end + timedelta(hours=time_buffer_hours)
    largest_gap = 0.0
    relevant_gap = 0.0

    for previous, current in zip(track.points, track.points[1:]):
        gap_minutes = (current.timestamp - previous.timestamp).total_seconds() / 60
        largest_gap = max(largest_gap, gap_minutes)
        overlaps_window = previous.timestamp <= relevant_end and current.timestamp >= relevant_start
        if overlaps_window:
            relevant_gap = max(relevant_gap, gap_minutes)

    if relevant_gap <= threshold_minutes:
        return FeatureResult(value=0.0, metadata={"largest_gap_minutes": largest_gap})

    score = min(1.0, (relevant_gap - threshold_minutes) / threshold_minutes)
    return FeatureResult(
        value=round(score, 4),
        reasons=[f"{relevant_gap:.0f}-minute AIS transmission gap near origin window."],
        metadata={"largest_gap_minutes": largest_gap, "relevant_gap_minutes": relevant_gap},
    )


from datetime import timedelta

from app.core.config import settings
from app.modules.attribution.ais_loader import AISDataError, bbox_around_point, load_ais_file
from app.modules.attribution.features import extract_features
from app.modules.attribution.scoring import WEIGHTS, score_vessel
from app.modules.attribution.synthetic_ais import generate_synthetic_ais_records
from app.modules.attribution.trajectory import build_tracks, filter_track_by_time, nearest_point_to_origin
from app.schemas.scoring import AISTrajectoryPoint, ScoreRequest, ScoreResponse, VesselScore, VesselScoreFactors

MAX_TRAJECTORY_POINTS = 200


def score_suspect_vessels(request: ScoreRequest) -> ScoreResponse:
    mode = request.mode or settings.ais_mode
    candidate_radius_km = request.candidate_radius_km or settings.ais_candidate_radius_km
    time_buffer_hours = request.time_buffer_hours if request.time_buffer_hours is not None else settings.ais_time_buffer_hours
    gap_threshold_minutes = settings.ais_gap_threshold_minutes

    time_start = request.origin_time_window.start - timedelta(hours=time_buffer_hours)
    time_end = request.origin_time_window.end + timedelta(hours=time_buffer_hours)
    try:
        records = _load_records(
            mode=mode,
            latitude=request.origin_latitude,
            longitude=request.origin_longitude,
            radius_km=candidate_radius_km,
            time_start=time_start,
            time_end=time_end,
        )
    except AISDataError as exc:
        return ScoreResponse(status="ais_data_not_ready", mode=mode, suspects=[], message=str(exc))

    tracks = build_tracks(records)
    time_filtered_tracks = [
        filtered
        for track in tracks
        if (filtered := filter_track_by_time(track, time_start, time_end)) is not None
    ]

    candidates = []
    for track in time_filtered_tracks:
        _, minimum_distance_km, _ = nearest_point_to_origin(
            track,
            request.origin_latitude,
            request.origin_longitude,
        )
        if minimum_distance_km <= candidate_radius_km:
            candidates.append(track)

    suspects: list[VesselScore] = []
    for track in candidates:
        features = extract_features(
            track=track,
            origin_latitude=request.origin_latitude,
            origin_longitude=request.origin_longitude,
            window_start=request.origin_time_window.start,
            window_end=request.origin_time_window.end,
            candidate_radius_km=candidate_radius_km,
            time_buffer_hours=time_buffer_hours,
            ais_gap_threshold_minutes=gap_threshold_minutes,
        )
        composite = score_vessel(features, WEIGHTS)
        suspects.append(
            VesselScore(
                mmsi=track.mmsi,
                vessel_name=track.vessel_name,
                score=composite.total,
                priority=composite.priority,
                minimum_distance_km=round(features.minimum_distance_km, 3),
                nearest_approach_time=features.nearest_approach_time,
                factors=VesselScoreFactors(**composite.factors),
                reasons=composite.reasons[:6],
                trajectory=_serialize_trajectory(track.points, features.nearest_approach_time),
                trajectory_source="synthetic_dev" if mode == "synthetic_dev" else "historical_ais",
            )
        )

    suspects.sort(key=lambda suspect: suspect.score, reverse=True)
    ranked_suspects = [
        suspect.model_copy(update={"rank": index + 1})
        for index, suspect in enumerate(suspects)
    ]
    return ScoreResponse(
        status="success",
        mode=mode,
        environment="synthetic_ais" if mode == "synthetic_dev" else "real_ais",
        scenario="mumbai_synthetic_demo" if mode == "synthetic_dev" else "algorithm_validation",
        candidate_count=len(ranked_suspects),
        temporal_filter={
            "start": time_start.isoformat(),
            "end": time_end.isoformat(),
            "buffer_hours": time_buffer_hours,
            "tracks_considered": len(time_filtered_tracks),
        },
        spatial_filter={
            "origin_latitude": request.origin_latitude,
            "origin_longitude": request.origin_longitude,
            "candidate_radius_km": candidate_radius_km,
        },
        suspects=ranked_suspects,
        message=(
            "Synthetic AIS development scoring; ranked investigative aid, not legal attribution."
            if mode == "synthetic_dev"
            else "Real AIS scoring; ranked investigative aid, not legal attribution."
        ),
    )


def _load_records(
    mode: str,
    latitude: float,
    longitude: float,
    radius_km: float,
    time_start,
    time_end,
):
    if mode == "synthetic_dev":
        return generate_synthetic_ais_records()
    if mode == "real_data":
        if not settings.ais_data_path:
            raise AISDataError("AIS_DATA_PATH is not configured.")
        return load_ais_file(
            settings.ais_data_path,
            max_records=settings.ais_max_real_records,
            time_start=time_start,
            time_end=time_end,
            bbox=bbox_around_point(latitude, longitude, radius_km),
        )
    raise AISDataError(f"Unsupported AIS mode: {mode}")


def _serialize_trajectory(records, nearest_approach_time) -> list[AISTrajectoryPoint]:
    ordered = sorted(records, key=lambda record: record.timestamp)
    selected = _downsample_records(ordered, nearest_approach_time, MAX_TRAJECTORY_POINTS)
    return [
        AISTrajectoryPoint(
            timestamp=record.timestamp,
            latitude=record.latitude,
            longitude=record.longitude,
            sog=record.sog,
            cog=record.cog,
            heading=record.heading,
        )
        for record in selected
    ]


def _downsample_records(records, nearest_approach_time, limit: int):
    if len(records) <= limit:
        return records

    keep_indexes = {0, len(records) - 1}
    if nearest_approach_time is not None:
        nearest_index = min(
            range(len(records)),
            key=lambda index: abs((records[index].timestamp - nearest_approach_time).total_seconds()),
        )
        keep_indexes.update(range(max(0, nearest_index - 2), min(len(records), nearest_index + 3)))

    remaining_slots = max(limit - len(keep_indexes), 0)
    if remaining_slots:
        step = max((len(records) - 1) / remaining_slots, 1)
        for offset in range(remaining_slots):
            keep_indexes.add(round(offset * step))

    return [records[index] for index in sorted(keep_indexes)[:limit]]

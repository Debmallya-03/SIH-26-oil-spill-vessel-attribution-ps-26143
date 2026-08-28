from datetime import timedelta

from app.core.config import settings
from app.modules.attribution.ais_loader import AISDataError, bbox_around_point, load_ais_file
from app.modules.attribution.features import extract_features
from app.modules.attribution.scoring import WEIGHTS, score_vessel
from app.modules.attribution.synthetic_ais import generate_synthetic_ais_records
from app.modules.attribution.trajectory import build_tracks, filter_track_by_time, nearest_point_to_origin
from app.schemas.scoring import ScoreRequest, ScoreResponse, VesselScore, VesselScoreFactors


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

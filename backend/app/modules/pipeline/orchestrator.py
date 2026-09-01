from contextlib import contextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from app.core.config import settings
from app.db.connection import DatabaseUnavailableError
from app.db.repository import persist_pipeline_result
from app.modules.attribution.service import score_suspect_vessels
from app.modules.detection.service import detect_oil_spill
from app.modules.drift.service import estimate_drift
from app.schemas.detection import DetectionRequest
from app.schemas.drift import DriftRequest
from app.schemas.pipeline import PersistenceStatus, PipelineRequest, PipelineResponse, PipelineSummary
from app.schemas.scoring import ScoreRequest


class PipelineTimer:
    def __init__(self) -> None:
        self.timings_ms: dict[str, float] = {}
        self.started_at = perf_counter()

    @contextmanager
    def stage(self, name: str):
        started = perf_counter()
        try:
            yield
        finally:
            self.timings_ms[name] = round((perf_counter() - started) * 1000, 2)

    def finish(self) -> dict[str, float]:
        self.timings_ms["total"] = round((perf_counter() - self.started_at) * 1000, 2)
        return self.timings_ms


def run_pipeline(request: PipelineRequest | None = None) -> PipelineResponse:
    pipeline_request = request or PipelineRequest()
    timer = PipelineTimer()
    incident_id = str(uuid4())
    scenario = _scenario_name(pipeline_request)
    provenance = _data_provenance(pipeline_request)

    with timer.stage("detection"):
        with _synthetic_detection_checkpoint(pipeline_request):
            detection = detect_oil_spill(DetectionRequest(image_path=pipeline_request.image_path))

    drift = None
    attribution = None
    failed_stage = None
    message = None

    if detection.status != "success":
        status = "partial" if pipeline_request.pipeline_mode != "detection_only" else "failed"
        failed_stage = "detection"
        message = detection.message or "Detection did not complete; downstream stages were skipped."
    elif pipeline_request.pipeline_mode == "detection_only":
        status = "completed"
        message = "Detection-only pipeline completed; no geospatial seed was requested."
    elif pipeline_request.spill_seed is None:
        status = "partial"
        failed_stage = "drift"
        message = "Pipeline requires user-supplied spill_seed; image-space detection pixels were not converted to latitude/longitude."
    else:
        with timer.stage("drift"):
            drift = estimate_drift(
                DriftRequest(
                    latitude=pipeline_request.spill_seed.latitude,
                    longitude=pipeline_request.spill_seed.longitude,
                    timestamp=pipeline_request.spill_seed.timestamp,
                    mode=pipeline_request.drift_mode,
                    engine=pipeline_request.drift_engine,
                    forcing_strategy=pipeline_request.drift_forcing_strategy,
                )
            )

        if drift.status != "success" or drift.origin_centroid is None or drift.origin_time_window is None:
            status = "partial"
            failed_stage = "drift"
            message = "Drift stage did not complete; attribution was skipped."
        else:
            with timer.stage("attribution"):
                attribution = score_suspect_vessels(
                    ScoreRequest(
                        origin_centroid=drift.origin_centroid,
                        origin_time_window=drift.origin_time_window,
                        mode=pipeline_request.attribution_mode,
                    )
                )
            status = "completed" if attribution.status == "success" else "partial"
            failed_stage = None if attribution.status == "success" else "attribution"
            message = (
                "Development demo pipeline completed; geospatial seed was user supplied."
                if attribution.status == "success"
                else "Attribution stage did not complete."
            )

    summary = PipelineSummary(
        spill_detected=detection.spill_detected,
        origin_centroid=drift.origin_centroid if drift else None,
        candidate_vessels=attribution.candidate_count if attribution else None,
        top_candidate=attribution.suspects[0] if attribution and attribution.suspects else None,
    )
    response = PipelineResponse(
        status=status,
        incident_id=incident_id,
        scenario=scenario,
        data_provenance=provenance,
        detection=detection,
        drift=drift,
        attribution=attribution,
        summary=summary,
        timings_ms=timer.finish(),
        persistence=PersistenceStatus(status="skipped" if not pipeline_request.persist else "pending"),
        failed_stage=failed_stage,
        message=message,
    )
    if pipeline_request.persist:
        with timer.stage("persistence"):
            try:
                persist_pipeline_result(response, pipeline_request)
                response.persistence = PersistenceStatus(status="persisted")
            except DatabaseUnavailableError:
                response.persistence = PersistenceStatus(status="unavailable", reason="Database is not available.")
            except Exception as exc:
                response.persistence = PersistenceStatus(status="failed", reason=str(exc))
        response.timings_ms = timer.finish()
    return response


def _scenario_name(request: PipelineRequest) -> str:
    if request.pipeline_mode == "demo":
        return "development_demo"
    if request.pipeline_mode == "real_validation":
        return "algorithm_validation"
    return "detection_only"


def _data_provenance(request: PipelineRequest) -> dict[str, str]:
    return {
        "pipeline_mode": request.pipeline_mode,
        "sar": "synthetic" if request.detection_mode == "synthetic_dev" else "unknown",
        "detection_model": "synthetic_development_checkpoint" if request.detection_mode == "synthetic_dev" else "configured_checkpoint",
        "spill_seed": "user_supplied" if request.spill_seed else "not_available",
        "currents": "copernicus_real" if request.drift_mode == "real_data" else "synthetic_dev",
        "wind": "noaa_gfs_real" if request.drift_mode == "real_data" else "synthetic_dev",
        "drift_engine": request.drift_engine or settings.drift_engine,
        "drift_forcing_strategy": request.drift_forcing_strategy or settings.opendrift_forcing_strategy,
        "ais": "synthetic_dev" if request.attribution_mode == "synthetic_dev" else "real_ais",
    }


@contextmanager
def _synthetic_detection_checkpoint(request: PipelineRequest):
    previous_path = settings.detection_model_path
    backend_root = Path(__file__).resolve().parents[3]
    synthetic_path = str(backend_root / "models" / "unet-synthetic-dev.pth")
    try:
        if request.detection_mode == "synthetic_dev":
            settings.detection_model_path = synthetic_path
        yield
    finally:
        settings.detection_model_path = previous_path

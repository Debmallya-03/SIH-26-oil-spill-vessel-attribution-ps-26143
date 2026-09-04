from datetime import UTC, datetime
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT / "backend"))

from app.db.connection import DatabaseUnavailableError
from app.db import migrations, repository
from app.core.config import Settings
from app.main import app
from app.modules.pipeline import orchestrator
from app.schemas.detection import DetectionResponse, GeoCoordinate, ImageCoordinate, PolygonGeometry as DetectionPolygon
from app.schemas.drift import DriftMetadata, DriftResponse, LineStringGeometry, OriginWindow, PolygonGeometry as DriftPolygon
from app.schemas.pipeline import PipelineRequest, SpillSeed
from app.schemas.scoring import AISTrajectoryPoint, ScoreResponse, VesselScore, VesselScoreFactors


DEMO_TIME = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
ORIGIN_WINDOW = OriginWindow(
    start=datetime(2026, 8, 26, 5, 0, tzinfo=UTC),
    end=datetime(2026, 8, 26, 7, 0, tzinfo=UTC),
)


def _fake_detection() -> DetectionResponse:
    return DetectionResponse(
        status="success",
        spill_detected=True,
        spill_id="test-spill",
        detected_at=DEMO_TIME,
        area_pixels=144.0,
        perimeter_pixels=48.0,
        centroid=ImageCoordinate(x=64.0, y=66.0),
        polygon=DetectionPolygon(coordinates=[[[10.0, 10.0], [20.0, 10.0], [20.0, 20.0], [10.0, 10.0]]]),
        confidence=0.88,
        model="small-unet-synthetic-dev",
    )


def _fake_drift() -> DriftResponse:
    origin = GeoCoordinate(latitude=18.522014161747748, longitude=72.78917658819358)
    return DriftResponse(
        status="success",
        mode="real_data",
        environment="real",
        engine="development_drift_engine",
        origin=origin,
        origin_centroid=origin,
        origin_area=DriftPolygon(
            coordinates=[
                [
                    [72.788, 18.521],
                    [72.79, 18.521],
                    [72.79, 18.523],
                    [72.788, 18.523],
                    [72.788, 18.521],
                ]
            ]
        ),
        origin_time_window=ORIGIN_WINDOW,
        backward_path=LineStringGeometry(coordinates=[[72.8333511352539, 18.5], [72.78917658819358, 18.522014161747748]]),
        forward_path=LineStringGeometry(coordinates=[[72.8333511352539, 18.5], [72.873, 18.481]]),
        metadata=DriftMetadata(
            backward_hours=6,
            forward_hours=6,
            particle_count=100,
            time_step_minutes=10,
            windage_factor=0.03,
            particles_requested=100,
            backward_particles_active=98,
            backward_particles_beached=2,
            forward_particles_active=99,
            forward_particles_beached=1,
        ),
    )


def _fake_score() -> ScoreResponse:
    return ScoreResponse(
        status="success",
        mode="synthetic_dev",
        environment="synthetic",
        scenario="development_demo",
        candidate_count=1,
        suspects=[
            VesselScore(
                rank=1,
                mmsi="419000001",
                vessel_name="Demo Vessel Alpha",
                score=87.4,
                priority="high",
                minimum_distance_km=0.72,
                nearest_approach_time=datetime(2026, 8, 26, 6, 10, tzinfo=UTC),
                factors=VesselScoreFactors(
                    proximity=0.95,
                    temporal_proximity=0.9,
                    trajectory_alignment=0.81,
                    speed_anomaly=0.72,
                    course_anomaly=0.6,
                    ais_gap=0.8,
                ),
                reasons=["Closest approach: 0.72 km from estimated origin."],
                trajectory=[
                    AISTrajectoryPoint(
                        timestamp=datetime(2026, 8, 26, 6, 0, tzinfo=UTC),
                        latitude=18.522,
                        longitude=72.789,
                        sog=8.0,
                        cog=91.0,
                    ),
                    AISTrajectoryPoint(
                        timestamp=datetime(2026, 8, 26, 6, 10, tzinfo=UTC),
                        latitude=18.523,
                        longitude=72.799,
                        sog=7.5,
                        cog=93.0,
                    ),
                ],
                trajectory_source="synthetic_dev",
            )
        ],
    )


class PipelineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def _patch_orchestrator(self, detection=None, drift=None, score=None, persist=None):
        previous = (
            orchestrator.detect_oil_spill,
            orchestrator.estimate_drift,
            orchestrator.score_suspect_vessels,
            orchestrator.persist_pipeline_result,
        )
        orchestrator.detect_oil_spill = detection or (lambda request: _fake_detection())
        orchestrator.estimate_drift = drift or (lambda request: _fake_drift())
        orchestrator.score_suspect_vessels = score or (lambda request: _fake_score())
        orchestrator.persist_pipeline_result = persist or (lambda result, request: None)
        return previous

    def _restore_orchestrator(self, previous) -> None:
        (
            orchestrator.detect_oil_spill,
            orchestrator.estimate_drift,
            orchestrator.score_suspect_vessels,
            orchestrator.persist_pipeline_result,
        ) = previous

    def test_pipeline_runs_detection_drift_and_attribution_with_user_geospatial_seed(self) -> None:
        previous = self._patch_orchestrator()
        try:
            result = orchestrator.run_pipeline(
                PipelineRequest(
                    pipeline_mode="demo",
                    image_path="data/synthetic_sar/images/sar_001.png",
                    spill_seed=SpillSeed(latitude=18.5, longitude=72.8333511352539, timestamp=DEMO_TIME),
                    drift_mode="real_data",
                    drift_engine="opendrift_openoil",
                    drift_forcing_strategy="native_grid",
                    attribution_mode="synthetic_dev",
                    persist=True,
                )
            )
        finally:
            self._restore_orchestrator(previous)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.scenario, "development_demo")
        self.assertEqual(result.persistence.status, "persisted")
        self.assertEqual(result.summary.candidate_vessels, 1)
        self.assertEqual(result.summary.top_candidate.mmsi, "419000001")
        self.assertEqual(result.summary.top_candidate.trajectory_source, "synthetic_dev")
        self.assertEqual(len(result.summary.top_candidate.trajectory), 2)
        self.assertEqual(result.data_provenance["spill_seed"], "user_supplied")
        self.assertEqual(result.data_provenance["drift_engine"], "opendrift_openoil")
        self.assertEqual(result.data_provenance["drift_forcing_strategy"], "native_grid")
        self.assertGreater(result.timings_ms["total"], 0)

    def test_candidate_without_trajectory_remains_valid(self) -> None:
        candidate = VesselScore(
            rank=1,
            mmsi="419000009",
            vessel_name="No Track Vessel",
            score=42.0,
            priority="low",
            factors=VesselScoreFactors(
                proximity=0.2,
                temporal_proximity=0.2,
                trajectory_alignment=0.2,
                speed_anomaly=0.0,
                course_anomaly=0.0,
                ais_gap=0.0,
            ),
            reasons=["Candidate retained without visualization trajectory."],
        )

        self.assertEqual(candidate.trajectory, [])
        self.assertIsNone(candidate.trajectory_source)

    def test_pipeline_never_converts_image_centroid_to_geographic_coordinates(self) -> None:
        drift_called = False

        def drift_stub(request):
            nonlocal drift_called
            drift_called = True
            return _fake_drift()

        previous = self._patch_orchestrator(detection=orchestrator.detect_oil_spill, drift=drift_stub)
        try:
            result = orchestrator.run_pipeline(
                PipelineRequest(
                    pipeline_mode="demo",
                    image_path="data/synthetic_sar/images/sar_001.png",
                    persist=False,
                )
            )
        finally:
            self._restore_orchestrator(previous)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.failed_stage, "drift")
        self.assertFalse(drift_called)
        self.assertIn("image-space detection pixels", result.message)

    def test_pipeline_returns_partial_status_when_detection_fails(self) -> None:
        drift_called = False

        def failed_detection(request):
            return DetectionResponse(status="model_not_ready", message="checkpoint missing")

        def drift_stub(request):
            nonlocal drift_called
            drift_called = True
            return _fake_drift()

        previous = self._patch_orchestrator(detection=failed_detection, drift=drift_stub)
        try:
            result = orchestrator.run_pipeline(PipelineRequest(pipeline_mode="demo", persist=False))
        finally:
            self._restore_orchestrator(previous)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.failed_stage, "detection")
        self.assertFalse(drift_called)
        self.assertEqual(result.message, "checkpoint missing")

    def test_pipeline_reports_missing_image_without_running_downstream_stages(self) -> None:
        drift_called = False

        def drift_stub(request):
            nonlocal drift_called
            drift_called = True
            return _fake_drift()

        previous = self._patch_orchestrator(detection=orchestrator.detect_oil_spill, drift=drift_stub)
        try:
            result = orchestrator.run_pipeline(
                PipelineRequest(
                    pipeline_mode="demo",
                    image_path="../data/synthetic_sar/images/does-not-exist.png",
                    spill_seed=SpillSeed(latitude=18.5, longitude=72.8333511352539, timestamp=DEMO_TIME),
                    persist=False,
                )
            )
        finally:
            self._restore_orchestrator(previous)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.failed_stage, "detection")
        self.assertIn("Image not found", result.message)
        self.assertFalse(drift_called)

    def test_pipeline_keeps_result_when_database_is_unavailable(self) -> None:
        previous = self._patch_orchestrator(
            persist=lambda result, request: (_ for _ in ()).throw(DatabaseUnavailableError("connection refused"))
        )
        try:
            result = orchestrator.run_pipeline(
                PipelineRequest(
                    pipeline_mode="demo",
                    image_path="data/synthetic_sar/images/sar_001.png",
                    spill_seed=SpillSeed(latitude=18.5, longitude=72.8333511352539, timestamp=DEMO_TIME),
                    persist=True,
                )
            )
        finally:
            self._restore_orchestrator(previous)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.persistence.status, "unavailable")
        self.assertEqual(result.persistence.reason, "Database is not available.")

    def test_wkt_helpers_use_longitude_latitude_order(self) -> None:
        self.assertEqual(repository._point_wkt(18.5, 72.8333511352539), "POINT(72.8333511352539 18.5)")
        self.assertEqual(
            repository._line_wkt(LineStringGeometry(coordinates=[[72.8, 18.5], [72.9, 18.6]])),
            "LINESTRING(72.8 18.5, 72.9 18.6)",
        )
        self.assertEqual(
            repository._trajectory_line_wkt(_fake_score().suspects[0].trajectory),
            "LINESTRING(72.789 18.522, 72.799 18.523)",
        )
        self.assertEqual(
            repository._polygon_wkt(DriftPolygon(coordinates=[[[72.8, 18.5], [72.9, 18.5], [72.9, 18.6], [72.8, 18.5]]])),
            "POLYGON((72.8 18.5, 72.9 18.5, 72.9 18.6, 72.8 18.5))",
        )

    def test_schema_sql_contains_postgis_and_day_5_tables(self) -> None:
        self.assertIn("CREATE EXTENSION IF NOT EXISTS postgis", migrations.SCHEMA_SQL)
        self.assertIn("CREATE TABLE IF NOT EXISTS incidents", migrations.SCHEMA_SQL)
        self.assertIn("CREATE TABLE IF NOT EXISTS detections", migrations.SCHEMA_SQL)
        self.assertIn("CREATE TABLE IF NOT EXISTS drift_runs", migrations.SCHEMA_SQL)
        self.assertIn("CREATE TABLE IF NOT EXISTS vessel_candidates", migrations.SCHEMA_SQL)
        self.assertIn("trajectory_points JSONB", migrations.SCHEMA_SQL)
        self.assertIn("trajectory_source TEXT", migrations.SCHEMA_SQL)

    def test_database_url_is_built_from_database_fields_when_url_is_placeholder(self) -> None:
        settings = Settings(
            database_url="postgresql://USER:PASSWORD@localhost:5432/DATABASE",
            database_host="localhost",
            database_port=5432,
            database_name="oilspill",
            database_user="oilspill_user",
            database_password="local_password",
        )

        self.assertEqual(settings.database_target["database"], "oilspill")
        self.assertEqual(settings.database_target["user"], "oilspill_user")
        self.assertEqual(
            settings.resolved_database_url,
            "postgresql://oilspill_user:local_password@localhost:5432/oilspill",
        )

    def test_pipeline_api_accepts_optional_body_and_reports_persistence_unavailable(self) -> None:
        previous = self._patch_orchestrator(
            persist=lambda result, request: (_ for _ in ()).throw(DatabaseUnavailableError("connection refused"))
        )
        try:
            response = self.client.post(
                "/pipeline",
                json={
                    "pipeline_mode": "demo",
                    "image_path": "data/synthetic_sar/images/sar_001.png",
                    "spill_seed": {
                        "latitude": 18.5,
                        "longitude": 72.8333511352539,
                        "timestamp": "2026-08-26T12:00:00Z",
                    },
                    "persist": True,
                },
            )
        finally:
            self._restore_orchestrator(previous)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["persistence"]["status"], "unavailable")
        self.assertEqual(payload["summary"]["top_candidate"]["mmsi"], "419000001")

    def test_incident_routes_handle_unavailable_and_not_found(self) -> None:
        self.assertEqual(self.client.get("/incidents/not-a-uuid").json()["status"], "not_found")
        self.assertEqual(self.client.get("/incidents/not-a-uuid/vessels").json()["status"], "not_found")

        previous_list = repository.list_incidents
        repository.list_incidents = lambda: (_ for _ in ()).throw(DatabaseUnavailableError("connection refused"))
        try:
            payload = self.client.get("/incidents").json()
        finally:
            repository.list_incidents = previous_list

        self.assertEqual(payload["status"], "persistence_unavailable")


if __name__ == "__main__":
    unittest.main()

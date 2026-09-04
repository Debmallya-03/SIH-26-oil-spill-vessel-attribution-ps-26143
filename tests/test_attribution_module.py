from datetime import UTC, datetime
import shutil
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT / "backend"))

from app.core.config import settings
from app.main import app
from app.modules.attribution.ais_loader import AISDataError, iter_ais_rows, load_ais_file, normalize_record, parse_timestamp
from app.modules.attribution.features import (
    score_ais_gap,
    score_course_anomaly,
    score_proximity,
    score_speed_anomaly,
    score_temporal_proximity,
)
from app.modules.attribution.geometry import circular_angle_difference_degrees, haversine_distance_km
from app.modules.attribution.scoring import WEIGHTS, score_vessel
from app.modules.attribution.service import score_suspect_vessels
from app.modules.attribution.synthetic_ais import generate_synthetic_ais_records
from app.modules.attribution.trajectory import build_tracks, filter_track_by_time
from app.schemas.scoring import ScoreRequest


ORIGIN = {"latitude": 18.522014161747748, "longitude": 72.78917658819358}
WINDOW = {"start": "2026-08-26T05:00:00Z", "end": "2026-08-26T07:00:00Z"}


class AttributionModuleTests(unittest.TestCase):
    def test_ais_column_normalization_timestamp_and_coordinate_validation(self) -> None:
        record = normalize_record(
            {
                "MMSI": "419000001",
                "BaseDateTime": "2026-08-26T06:00:00Z",
                "LAT": "18.5",
                "LON": "72.8",
                "SOG": "10.5",
                "COG": "359",
                "VesselName": "Demo",
            }
        )

        self.assertEqual(record.mmsi, "419000001")
        self.assertEqual(record.timestamp.tzinfo, UTC)
        self.assertEqual(record.latitude, 18.5)
        self.assertEqual(record.longitude, 72.8)
        self.assertEqual(record.cog, 359.0)
        self.assertEqual(record.vessel_name, "Demo")

        with self.assertRaises(AISDataError):
            normalize_record({"MMSI": "1", "BaseDateTime": "2026-08-26T06:00:00Z", "LAT": "99", "LON": "72.8", "SOG": "1", "COG": "2"})

        with self.assertRaises(AISDataError):
            normalize_record({"MMSI": "1", "BaseDateTime": "2026-08-26T06:00:00Z", "LAT": "18.5", "LON": "72.8", "SOG": "1", "COG": ""})

    def test_parse_timestamp_assumes_utc_when_naive(self) -> None:
        parsed = parse_timestamp("2026-08-26T06:00:00")

        self.assertEqual(parsed.tzinfo, UTC)
        self.assertEqual(parsed.isoformat(), "2026-08-26T06:00:00+00:00")

    def test_trajectory_grouping_and_time_filtering(self) -> None:
        records = generate_synthetic_ais_records()
        tracks = build_tracks(records)
        filtered = filter_track_by_time(
            tracks[0],
            datetime(2026, 8, 26, 5, 0, tzinfo=UTC),
            datetime(2026, 8, 26, 7, 0, tzinfo=UTC),
        )

        self.assertEqual(len(tracks), 10)
        self.assertIsNotNone(filtered)
        self.assertTrue(all(filtered.points[index].timestamp <= filtered.points[index + 1].timestamp for index in range(len(filtered.points) - 1)))

    def test_spatial_filter_and_ranking_order(self) -> None:
        response = score_suspect_vessels(
            ScoreRequest(
                origin_centroid=ORIGIN,
                origin_time_window=WINDOW,
                mode="synthetic_dev",
            )
        )

        self.assertEqual(response.status, "success")
        self.assertEqual(response.mode, "synthetic_dev")
        self.assertEqual(response.candidate_count, 10)
        self.assertEqual(response.suspects[0].rank, 1)
        self.assertEqual(response.suspects[0].mmsi, "419000002")
        self.assertGreaterEqual(response.suspects[0].score, response.suspects[1].score)
        self.assertLessEqual(max(suspect.minimum_distance_km for suspect in response.suspects), 25.0)

    def test_synthetic_candidates_include_ordered_trajectory_provenance(self) -> None:
        response = score_suspect_vessels(
            ScoreRequest(origin_centroid=ORIGIN, origin_time_window=WINDOW, mode="synthetic_dev")
        )
        top = response.suspects[0]

        self.assertEqual(top.trajectory_source, "synthetic_dev")
        self.assertGreaterEqual(len(top.trajectory), 2)
        self.assertTrue(all(top.trajectory[index].timestamp <= top.trajectory[index + 1].timestamp for index in range(len(top.trajectory) - 1)))
        self.assertTrue(all(-90 <= point.latitude <= 90 and -180 <= point.longitude <= 180 for point in top.trajectory))
        self.assertTrue(any(point.timestamp == top.nearest_approach_time for point in top.trajectory))

    def test_haversine_and_circular_cog_difference(self) -> None:
        self.assertAlmostEqual(haversine_distance_km(18.5, 72.8, 18.5, 72.8), 0.0)
        self.assertEqual(circular_angle_difference_degrees(359, 2), 3)

    def test_proximity_and_temporal_scores(self) -> None:
        self.assertEqual(score_proximity(1.0, 25.0).value, 1.0)
        self.assertGreater(score_proximity(4.0, 25.0).value, score_proximity(12.0, 25.0).value)
        self.assertEqual(
            score_temporal_proximity(
                datetime(2026, 8, 26, 6, 0, tzinfo=UTC),
                datetime(2026, 8, 26, 5, 0, tzinfo=UTC),
                datetime(2026, 8, 26, 7, 0, tzinfo=UTC),
                2,
            ).value,
            1.0,
        )

    def test_speed_course_and_gap_features(self) -> None:
        tracks = build_tracks(generate_synthetic_ais_records())
        bravo = next(track for track in tracks if track.mmsi == "419000002")
        charlie = next(track for track in tracks if track.mmsi == "419000003")
        delta = next(track for track in tracks if track.mmsi == "419000004")

        self.assertGreater(score_speed_anomaly(bravo, 18).value, 0.9)
        self.assertGreater(score_course_anomaly(charlie, 18).value, 0.5)
        self.assertEqual(
            score_ais_gap(
                delta,
                datetime(2026, 8, 26, 5, 0, tzinfo=UTC),
                datetime(2026, 8, 26, 7, 0, tzinfo=UTC),
                2,
                15,
            ).metadata["relevant_gap_minutes"],
            50.0,
        )

    def test_composite_score_weights(self) -> None:
        response = score_suspect_vessels(
            ScoreRequest(origin_centroid=ORIGIN, origin_time_window=WINDOW, mode="synthetic_dev")
        )
        top = response.suspects[0]

        self.assertEqual(set(WEIGHTS), set(top.factors.model_dump()))
        self.assertEqual(top.priority, "high")
        self.assertTrue(top.reasons)

    def test_deterministic_synthetic_generation(self) -> None:
        first = generate_synthetic_ais_records()
        second = generate_synthetic_ais_records()

        self.assertEqual(first, second)
        self.assertEqual(len({record.mmsi for record in first}), 10)

    def test_score_api_synthetic_dev_response_and_legacy_request(self) -> None:
        client = TestClient(app)
        modern = client.post("/score", json={
            "origin_centroid": ORIGIN,
            "origin_time_window": WINDOW,
            "mode": "synthetic_dev",
        })
        legacy = client.post("/score", json={
            "latitude": ORIGIN["latitude"],
            "longitude": ORIGIN["longitude"],
            "origin_time_window": WINDOW,
        })

        self.assertEqual(modern.status_code, 200)
        self.assertEqual(modern.json()["status"], "success")
        self.assertIn("reasons", modern.json()["suspects"][0])
        self.assertEqual(legacy.status_code, 200)

    def test_real_data_missing_file_behavior(self) -> None:
        previous_mode = settings.ais_mode
        previous_path = settings.ais_data_path
        try:
            settings.ais_mode = "real_data"
            settings.ais_data_path = None
            response = score_suspect_vessels(
                ScoreRequest(origin_centroid=ORIGIN, origin_time_window=WINDOW, mode="real_data")
            )
        finally:
            settings.ais_mode = previous_mode
            settings.ais_data_path = previous_path

        self.assertEqual(response.status, "ais_data_not_ready")
        self.assertEqual(response.mode, "real_data")
        self.assertEqual(response.suspects, [])

    def test_real_data_csv_loader_smoke(self) -> None:
        previous_path = settings.ais_data_path
        temp_dir = REPO_ROOT / ".test_tmp_attribution"
        try:
            temp_dir.mkdir(exist_ok=True)
            csv_path = temp_dir / "ais.csv"
            csv_path.write_text(
                "MMSI,BaseDateTime,LAT,LON,SOG,COG,VesselName\n"
                "419111111,2026-08-26T06:00:00Z,18.522,72.789,8,91,CSV Vessel\n"
                "419111111,2026-08-26T06:10:00Z,18.522,72.799,8,91,CSV Vessel\n",
                encoding="utf-8",
            )
            settings.ais_data_path = str(csv_path)
            response = score_suspect_vessels(
                ScoreRequest(origin_centroid=ORIGIN, origin_time_window=WINDOW, mode="real_data")
            )
        finally:
            settings.ais_data_path = previous_path
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

        self.assertEqual(response.status, "success")
        self.assertEqual(response.mode, "real_data")
        self.assertEqual(response.candidate_count, 1)
        self.assertEqual(response.suspects[0].trajectory_source, "historical_ais")
        self.assertEqual([point.timestamp.isoformat() for point in response.suspects[0].trajectory], [
            "2026-08-26T06:00:00+00:00",
            "2026-08-26T06:10:00+00:00",
        ])

    def test_real_data_gulf_coast_validation_does_not_mix_with_mumbai_demo(self) -> None:
        previous_path = settings.ais_data_path
        temp_dir = REPO_ROOT / ".test_tmp_attribution_gulf"
        gulf_origin = {"latitude": 29.7732211097852, "longitude": -90.06771383054893}
        gulf_window = {"start": "2024-01-14T03:00:00Z", "end": "2024-01-14T04:00:00Z"}
        try:
            temp_dir.mkdir(exist_ok=True)
            csv_path = temp_dir / "ais_gulf.csv"
            csv_path.write_text(
                "mmsi,base_date_time,latitude,longitude,sog,cog,heading,vessel_name\n"
                "367111111,2024-01-14T03:10:00Z,29.773,-90.068,6,180,180,Gulf Validation Vessel\n"
                "367111111,2024-01-14T03:20:00Z,29.774,-90.067,6,181,181,Gulf Validation Vessel\n",
                encoding="utf-8",
            )
            settings.ais_data_path = str(csv_path)
            real_response = score_suspect_vessels(
                ScoreRequest(origin_centroid=gulf_origin, origin_time_window=gulf_window, mode="real_data")
            )
            demo_response = score_suspect_vessels(
                ScoreRequest(origin_centroid=ORIGIN, origin_time_window=WINDOW, mode="synthetic_dev")
            )
        finally:
            settings.ais_data_path = previous_path
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

        self.assertEqual(real_response.status, "success")
        self.assertEqual(real_response.scenario, "algorithm_validation")
        self.assertEqual(real_response.suspects[0].trajectory_source, "historical_ais")
        self.assertEqual(real_response.suspects[0].mmsi, "367111111")
        self.assertEqual(demo_response.scenario, "mumbai_synthetic_demo")
        self.assertTrue(all(suspect.trajectory_source == "synthetic_dev" for suspect in demo_response.suspects))

    def test_csv_zst_streaming_and_chunk_limit(self) -> None:
        import zstandard as zstd

        temp_dir = REPO_ROOT / ".test_tmp_attribution_zst"
        try:
            temp_dir.mkdir(exist_ok=True)
            zst_path = temp_dir / "ais.csv.zst"
            csv_text = (
                "mmsi,base_date_time,longitude,latitude,sog,cog,heading,vessel_name,vessel_type,status\n"
                "111,2024-01-14 03:00:00,-90.0,29.7,8,90,90,A,70,0\n"
                "111,2024-01-14 03:10:00,-90.1,29.8,8,91,91,A,70,0\n"
                "222,2024-01-14 03:20:00,-91.0,30.0,7,88,88,B,70,0\n"
            )
            zst_path.write_bytes(zstd.ZstdCompressor().compress(csv_text.encode("utf-8")))

            rows = list(iter_ais_rows(zst_path))
            records = load_ais_file(zst_path, max_records=2)
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["base_date_time"], "2024-01-14 03:00:00")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].mmsi, "111")

    def test_tiny_processed_subset_generation_helpers(self) -> None:
        from scripts.validate_real_ais import collect_subset

        import zstandard as zstd

        temp_dir = REPO_ROOT / ".test_tmp_attribution_subset"
        try:
            temp_dir.mkdir(exist_ok=True)
            zst_path = temp_dir / "ais.csv.zst"
            csv_text = (
                "mmsi,base_date_time,longitude,latitude,sog,cog,heading,vessel_name,vessel_type,status\n"
                "111,2024-01-14 03:00:00,-90.0,29.7,8,90,90,A,70,0\n"
                "111,2024-01-14 03:10:00,-90.1,29.8,8,91,91,A,70,0\n"
                "222,2024-01-14 03:00:00,-90.2,29.9,7,88,88,B,70,0\n"
                "222,2024-01-14 03:10:00,-90.3,30.0,7,89,89,B,70,0\n"
            )
            zst_path.write_bytes(zstd.ZstdCompressor().compress(csv_text.encode("utf-8")))
            rows, vessel_counts = collect_subset(
                zst_path,
                (29.0, 31.0, -91.0, -89.0),
                datetime(2024, 1, 14, 3, 0, tzinfo=UTC),
                datetime(2024, 1, 14, 4, 0, tzinfo=UTC),
                max_vessels=1,
                min_points=2,
            )
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

        self.assertEqual(len(vessel_counts), 1)
        self.assertEqual(len(rows), 2)

    def test_day_1_2_3_api_regression(self) -> None:
        client = TestClient(app)

        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.get("/health").status_code, 200)
        self.assertEqual(client.get("/docs").status_code, 200)
        self.assertEqual(client.post("/detect", json={}).status_code, 200)
        self.assertEqual(client.post("/drift", json={
            "latitude": 18.5204,
            "longitude": 72.89,
            "timestamp": "2026-08-26T12:00:00Z",
        }).status_code, 200)
        self.assertEqual(client.post("/pipeline").status_code, 200)


if __name__ == "__main__":
    unittest.main()

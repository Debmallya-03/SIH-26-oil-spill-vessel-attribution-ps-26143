from datetime import UTC, datetime
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT / "backend"))

from app.main import app
from app.modules.drift.environmental import (
    CurrentUnavailableError,
    EnvironmentDataError,
    EnvironmentalForcing,
    RealDataEnvironmentProvider,
    haversine_distance_km,
)
from app.modules.drift.engine import DevelopmentDriftEngine, InsufficientParticlesError
from app.modules.drift.geometry import move_coordinate, validate_coordinate
from app.modules.drift.service import estimate_drift
from app.modules.drift.synthetic_environment import SyntheticDevelopmentEnvironment
from app.schemas.drift import DriftRequest


class DriftModuleTests(unittest.TestCase):
    def test_coordinate_validation(self) -> None:
        validate_coordinate(18.5204, 72.89)

        with self.assertRaises(ValueError):
            validate_coordinate(91.0, 72.89)
        with self.assertRaises(ValueError):
            validate_coordinate(18.5204, 181.0)

    def test_move_coordinate_uses_longitude_scaling(self) -> None:
        latitude, longitude = move_coordinate(18.5204, 72.89, east_meters=1000, north_meters=0)

        self.assertAlmostEqual(latitude, 18.5204, places=5)
        self.assertGreater(longitude, 72.89)

    def test_haversine_distance_calculation(self) -> None:
        distance = haversine_distance_km(18.5204, 72.89, 18.5, 72.8333511352539)

        self.assertAlmostEqual(distance, 6.3894, places=3)

    def test_deterministic_output_with_fixed_seed(self) -> None:
        engine_a = DevelopmentDriftEngine(SyntheticDevelopmentEnvironment(), random_seed=42)
        engine_b = DevelopmentDriftEngine(SyntheticDevelopmentEnvironment(), random_seed=42)
        timestamp = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)

        result_a = engine_a.simulate(18.5204, 72.89, timestamp, 6, 6, 25)
        result_b = engine_b.simulate(18.5204, 72.89, timestamp, 6, 6, 25)

        self.assertEqual(result_a.backward_path.coordinates, result_b.backward_path.coordinates)
        self.assertEqual(result_a.forward_path.coordinates, result_b.forward_path.coordinates)

    def test_backward_forward_paths_and_geojson_order(self) -> None:
        request = DriftRequest(
            latitude=18.5204,
            longitude=72.89,
            timestamp=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
            particle_count=25,
        )
        response = estimate_drift(request)

        self.assertEqual(response.status, "success")
        self.assertEqual(response.backward_path.coordinates[0], [72.89, 18.5204])
        self.assertEqual(response.forward_path.coordinates[0], [72.89, 18.5204])
        self.assertGreater(len(response.backward_path.coordinates), 2)
        self.assertGreater(len(response.forward_path.coordinates), 2)
        self.assertLess(response.backward_path.coordinates[-1][0], 72.89)
        self.assertGreater(response.forward_path.coordinates[-1][0], 72.89)

    def test_origin_polygon_time_window_and_particle_count(self) -> None:
        request = DriftRequest(
            latitude=18.5204,
            longitude=72.89,
            timestamp=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
            particle_count=40,
        )
        response = estimate_drift(request)

        self.assertEqual(response.metadata.particle_count, 40)
        self.assertEqual(response.origin_time_window.start.isoformat(), "2026-08-26T05:00:00+00:00")
        self.assertEqual(response.origin_time_window.end.isoformat(), "2026-08-26T07:00:00+00:00")
        self.assertEqual(response.origin_area.type, "Polygon")
        self.assertGreaterEqual(len(response.origin_area.coordinates[0]), 4)
        self.assertEqual(response.origin_area.coordinates[0][0], response.origin_area.coordinates[0][-1])

    def test_real_data_missing_file_handling(self) -> None:
        provider = RealDataEnvironmentProvider(current_path="missing.nc", wind_glob="missing*.grib2")
        self.assertFalse(provider.is_ready())

    def test_real_netcdf_discovery_and_target_coverage(self) -> None:
        import xarray as xr

        path = REPO_ROOT / "data" / "ocean" / "currents" / "cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i_1787833203663.nc"
        with xr.open_dataset(path) as dataset:
            self.assertIn("uo", dataset.data_vars)
            self.assertIn("vo", dataset.data_vars)
            self.assertEqual(dataset["uo"].attrs.get("units"), "m s-1")
            self.assertLessEqual(float(dataset.latitude.min()), 18.5204)
            self.assertGreaterEqual(float(dataset.latitude.max()), 18.5204)
            self.assertLessEqual(float(dataset.longitude.min()), 72.89)
            self.assertGreaterEqual(float(dataset.longitude.max()), 72.89)
            self.assertIn("2026-08-26T12:00:00.000000000", [str(value) for value in dataset.time.values])

    def test_nearest_valid_water_lookup(self) -> None:
        provider = RealDataEnvironmentProvider(
            current_path="../data/ocean/currents/cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i_1787833203663.nc",
            wind_glob="../data/ocean/wind/gfs.t06z.pgrb2.0p25.f*",
        )
        cells = provider.nearest_valid_current_cells(
            18.5204,
            72.89,
            datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
            limit=10,
        )

        self.assertEqual(len(cells), 10)
        self.assertAlmostEqual(cells[0].latitude, 18.5, places=4)
        self.assertAlmostEqual(cells[0].longitude, 72.8333511352539, places=4)
        self.assertAlmostEqual(cells[0].distance_km, 6.3894, places=3)
        self.assertTrue(all(np.isfinite(cell.current_u_mps) and np.isfinite(cell.current_v_mps) for cell in cells))

    def test_real_grib_discovery_with_u_and_v_wind(self) -> None:
        import xarray as xr

        files = sorted((REPO_ROOT / "data" / "ocean" / "wind").glob("gfs.t06z.pgrb2.0p25.f*"))
        self.assertEqual(len(files), 3)
        valid_times = []
        for path in files:
            with xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""}) as dataset:
                self.assertIn("v10", dataset.data_vars)
                self.assertIn("u10", dataset.data_vars)
                self.assertEqual(float(dataset.heightAboveGround.values), 10.0)
                self.assertLessEqual(float(dataset.latitude.min()), 18.5204)
                self.assertGreaterEqual(float(dataset.latitude.max()), 18.5204)
                self.assertLessEqual(float(dataset.longitude.min()), 72.89)
                self.assertGreaterEqual(float(dataset.longitude.max()), 72.89)
                valid_times.append(str(dataset.valid_time.values))
        self.assertEqual(
            valid_times,
            [
                "2026-08-26T06:00:00.000000000",
                "2026-08-26T12:00:00.000000000",
                "2026-08-26T18:00:00.000000000",
            ],
        )

    def test_grib_message_inspection_detects_u10_and_v10(self) -> None:
        provider = RealDataEnvironmentProvider(
            current_path="../data/ocean/currents/cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i_1787833203663.nc",
            wind_glob="../data/ocean/wind/gfs.t06z.pgrb2.0p25.f*",
        )
        messages = provider.inspect_grib_messages()

        self.assertEqual(len(messages), 6)
        self.assertEqual([message.short_name for message in messages].count("10u"), 3)
        self.assertEqual([message.short_name for message in messages].count("10v"), 3)
        self.assertTrue(all(message.type_of_level == "heightAboveGround" for message in messages))
        self.assertTrue(all(message.level == 10 for message in messages))

    def test_masked_current_uses_nearest_valid_within_radius(self) -> None:
        provider = RealDataEnvironmentProvider(
            current_path="../data/ocean/currents/cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i_1787833203663.nc",
            wind_glob="../data/ocean/wind/gfs.t06z.pgrb2.0p25.f*",
        )
        self.assertTrue(provider.is_ready())
        forcing = provider.get_forcing(18.5204, 72.89, datetime(2026, 8, 26, 12, 0, tzinfo=UTC))
        substitution = forcing.source_metadata["current"]["nearest_current_substitution"]

        self.assertAlmostEqual(forcing.current_u_mps, 0.05565712973475456)
        self.assertAlmostEqual(forcing.current_v_mps, -0.08426374942064285)
        self.assertAlmostEqual(substitution["substituted_grid_position"]["latitude"], 18.5)
        self.assertAlmostEqual(substitution["substituted_grid_position"]["longitude"], 72.8333511352539)
        self.assertLessEqual(substitution["distance_km"], 10.0)

    def test_nearest_valid_current_beyond_radius_is_rejected(self) -> None:
        provider = RealDataEnvironmentProvider(
            current_path="../data/ocean/currents/cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i_1787833203663.nc",
            wind_glob="../data/ocean/wind/gfs.t06z.pgrb2.0p25.f*",
            max_nearest_current_distance_km=1.0,
        )

        with self.assertRaises(CurrentUnavailableError):
            provider.get_forcing(18.5204, 72.89, datetime(2026, 8, 26, 12, 0, tzinfo=UTC))

    def test_real_data_out_of_range_coordinate_and_timestamp(self) -> None:
        provider = RealDataEnvironmentProvider(
            current_path="../data/ocean/currents/cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i_1787833203663.nc",
            wind_glob="../data/ocean/wind/gfs.t06z.pgrb2.0p25.f*",
        )
        with self.assertRaises(EnvironmentDataError):
            provider.get_forcing(30.0, 72.89, datetime(2026, 8, 26, 12, 0, tzinfo=UTC))
        with self.assertRaises(EnvironmentDataError):
            provider.get_forcing(18.0, 72.1, datetime(2026, 8, 28, 12, 0, tzinfo=UTC))

    def test_real_data_api_mode_runs_with_real_forcing(self) -> None:
        request = DriftRequest(
            latitude=18.5,
            longitude=72.8333511352539,
            timestamp=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
            mode="real_data",
        )
        response = estimate_drift(request)

        self.assertEqual(response.status, "success")
        self.assertEqual(response.mode, "real_data")
        self.assertEqual(response.environment, "real")
        self.assertEqual(response.engine, "development_drift_engine")
        self.assertGreater(response.metadata.nearest_current_substitution_count, 0)
        self.assertEqual(response.metadata.backward_particles_active, 100)
        self.assertEqual(response.metadata.forward_particles_active, 100)
        self.assertEqual(response.metadata.backward_particles_beached, 0)
        self.assertEqual(response.metadata.forward_particles_beached, 0)

    def test_particle_beaching_does_not_stop_other_particles(self) -> None:
        class OneBeachedProvider:
            mode = "test"

            def __init__(self) -> None:
                self.calls = 0

            def get_forcing(self, latitude, longitude, timestamp):
                self.calls += 1
                if self.calls == 1:
                    raise CurrentUnavailableError("no finite current within threshold")
                return EnvironmentalForcing(0.02, -0.01, 1.0, 0.5)

        engine = DevelopmentDriftEngine(OneBeachedProvider(), random_seed=42, time_step_minutes=60)
        result = engine.simulate(
            18.5,
            72.8333511352539,
            datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
            backward_hours=1,
            forward_hours=1,
            particle_count=5,
        )

        self.assertEqual(result.metadata.backward_particles_beached, 1)
        self.assertEqual(result.metadata.backward_particles_active, 4)
        self.assertEqual(result.metadata.forward_particles_active, 5)
        self.assertGreaterEqual(len(result.origin_area.coordinates[0]), 4)

    def test_all_particles_beached_returns_insufficient_particles(self) -> None:
        class BeachedProvider:
            mode = "test"

            def get_forcing(self, latitude, longitude, timestamp):
                raise CurrentUnavailableError("no finite current within threshold")

        engine = DevelopmentDriftEngine(BeachedProvider(), random_seed=42, time_step_minutes=60)
        with self.assertRaises(InsufficientParticlesError) as context:
            engine.simulate(
                18.5,
                72.8333511352539,
                datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
                backward_hours=1,
                forward_hours=1,
                particle_count=5,
            )

        self.assertEqual(context.exception.metadata.backward_particles_beached, 5)
        self.assertEqual(context.exception.metadata.backward_particles_active, 0)

    def test_substitution_metadata_and_deterministic_real_data_output(self) -> None:
        request = DriftRequest(
            latitude=18.5,
            longitude=72.8333511352539,
            timestamp=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
            mode="real_data",
            particle_count=10,
        )
        response_a = estimate_drift(request)
        response_b = estimate_drift(request)

        self.assertEqual(response_a.status, "success")
        self.assertEqual(response_a.backward_path.coordinates, response_b.backward_path.coordinates)
        self.assertEqual(response_a.forward_path.coordinates, response_b.forward_path.coordinates)
        self.assertGreater(response_a.metadata.nearest_current_substitution_count, 0)
        first_substitution = response_a.metadata.nearest_current_substitutions[0]
        self.assertIn("requested_position", first_substitution)
        self.assertIn("substituted_grid_position", first_substitution)
        self.assertIn("distance_km", first_substitution)

    def test_drift_api_response_schema_and_invalid_coordinates(self) -> None:
        client = TestClient(app)

        response = client.post("/drift", json={
            "latitude": 18.5204,
            "longitude": 72.89,
            "timestamp": "2026-08-26T12:00:00Z",
        })
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["mode"], "synthetic_dev")
        self.assertEqual(payload["engine"], "development_drift_engine")
        self.assertEqual(payload["backward_path"]["coordinates"][0], [72.89, 18.5204])
        self.assertIn("origin_area", payload)
        self.assertIn("metadata", payload)

        invalid = client.post("/drift", json={
            "latitude": 100.0,
            "longitude": 72.89,
            "timestamp": "2026-08-26T12:00:00Z",
        })
        self.assertEqual(invalid.status_code, 422)


if __name__ == "__main__":
    unittest.main()

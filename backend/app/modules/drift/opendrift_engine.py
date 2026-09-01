from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Any, Literal

import numpy as np

from app.modules.drift.engine import DriftSimulationResult, InsufficientParticlesError
from app.modules.drift.environmental import EnvironmentDataError, EnvironmentalForcing
from app.modules.drift.geometry import (
    line_string_from_coordinates,
    origin_polygon_from_particles,
    particle_centroid,
    validate_coordinate,
)
from app.schemas.detection import GeoCoordinate
from app.schemas.drift import DriftMetadata, OriginWindow

OPENDRIFT_ENGINE_NAME = "opendrift_openoil"
FORCING_NATIVE_GRID = "native_grid"
FORCING_CONSTANT_SAMPLE = "constant_sample"
OPENDRIFT_VARIABLE_MAPPING = {
    "current_u_mps": "x_sea_water_velocity",
    "current_v_mps": "y_sea_water_velocity",
    "wind_u_mps": "x_wind",
    "wind_v_mps": "y_wind",
}


class OpenDriftUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenDriftRun:
    final_particles: list[tuple[float, float]]
    centroids: list[GeoCoordinate]
    active_count: int
    deactivated_count: int


@dataclass(frozen=True)
class OpenDriftReaderBundle:
    current_reader: Any
    wind_reader: Any
    current_reader_class: str
    wind_reader_class: str
    metadata: dict[str, object]


def get_opendrift_capability() -> dict[str, str | None]:
    try:
        opendrift = _import_opendrift_package()
        from opendrift.models.openoil import OpenOil  # noqa: F401

        return {
            "status": "available",
            "engine": OPENDRIFT_ENGINE_NAME,
            "model": "OpenOil",
            "version": getattr(opendrift, "__version__", None),
        }
    except Exception as exc:
        return {
            "status": "not_available",
            "engine": OPENDRIFT_ENGINE_NAME,
            "model": "OpenOil",
            "version": None,
            "message": str(exc),
        }


class OpenDriftOpenOilEngine:
    name = OPENDRIFT_ENGINE_NAME

    def __init__(
        self,
        *,
        time_step_minutes: int = 60,
        seed_radius_meters: float = 100.0,
        forcing_strategy: Literal["native_grid", "constant_sample"] = FORCING_NATIVE_GRID,
        current_path: Path | None = None,
        wind_files: list[Path] | None = None,
    ) -> None:
        self.time_step_minutes = time_step_minutes
        self.seed_radius_meters = seed_radius_meters
        self.forcing_strategy = forcing_strategy
        self.current_path = current_path
        self.wind_files = wind_files or []

    def simulate(
        self,
        *,
        latitude: float,
        longitude: float,
        timestamp: datetime,
        backward_hours: int,
        forward_hours: int,
        particle_count: int,
        forcing: EnvironmentalForcing,
    ) -> DriftSimulationResult:
        validate_coordinate(latitude, longitude)
        readers = self._reader_bundle() if self.forcing_strategy == FORCING_NATIVE_GRID else None
        backward = self._run_openoil(
            latitude=latitude,
            longitude=longitude,
            timestamp=timestamp,
            hours=backward_hours,
            particle_count=particle_count,
            forcing=forcing,
            readers=readers,
            direction=-1,
        )
        forward = self._run_openoil(
            latitude=latitude,
            longitude=longitude,
            timestamp=timestamp,
            hours=forward_hours,
            particle_count=particle_count,
            forcing=forcing,
            readers=readers,
            direction=1,
        )

        metadata = DriftMetadata(
            backward_hours=backward_hours,
            forward_hours=forward_hours,
            particle_count=particle_count,
            time_step_minutes=self.time_step_minutes,
            windage_factor=0.0,
            particles_requested=particle_count,
            backward_particles_active=backward.active_count,
            backward_particles_beached=particle_count - backward.active_count,
            forward_particles_active=forward.active_count,
            forward_particles_beached=particle_count - forward.active_count,
            nearest_current_substitution_count=0,
            nearest_current_substitutions=[],
            max_nearest_current_distance_km=None,
            max_actual_substitution_distance_km=0.0,
            forcing_strategy=self.forcing_strategy,
            opendrift_version=get_opendrift_capability().get("version"),
            current_reader=readers.current_reader_class if readers else "opendrift.readers.reader_constant.Reader",
            wind_reader=readers.wind_reader_class if readers else "opendrift.readers.reader_constant.Reader",
            forcing_coverage_status="complete",
            backward_particles_deactivated=backward.deactivated_count,
            forward_particles_deactivated=forward.deactivated_count,
            backward_final_centroid=_coordinate_dict(particle_centroid(backward.final_particles))
            if backward.final_particles
            else None,
            forward_final_centroid=_coordinate_dict(particle_centroid(forward.final_particles))
            if forward.final_particles
            else None,
        )

        if len(backward.final_particles) < 3:
            raise InsufficientParticlesError(
                "Too few OpenDrift particles remained available to produce an origin polygon.",
                metadata,
            )

        endpoint_time = timestamp - timedelta(hours=backward_hours)
        return DriftSimulationResult(
            engine=self.name,
            origin_centroid=particle_centroid(backward.final_particles),
            origin_area=origin_polygon_from_particles(backward.final_particles),
            origin_time_window=OriginWindow(
                start=endpoint_time - timedelta(hours=1),
                end=endpoint_time + timedelta(hours=1),
            ),
            backward_path=line_string_from_coordinates(backward.centroids),
            forward_path=line_string_from_coordinates(forward.centroids),
            metadata=metadata,
        )

    def _run_openoil(
        self,
        *,
        latitude: float,
        longitude: float,
        timestamp: datetime,
        hours: int,
        particle_count: int,
        forcing: EnvironmentalForcing,
        readers: OpenDriftReaderBundle | None,
        direction: int,
    ) -> OpenDriftRun:
        try:
            _import_opendrift_package()
            from opendrift.models.openoil import OpenOil
            from opendrift.readers import reader_constant
        except Exception as exc:
            raise OpenDriftUnavailableError(str(exc)) from exc

        model = OpenOil(loglevel=50)
        if readers:
            model.add_reader([readers.current_reader, readers.wind_reader])
        else:
            model.add_reader(reader_constant.Reader(_constant_reader_values(forcing)))
        model.seed_elements(
            lon=longitude,
            lat=latitude,
            time=_opendrift_datetime(timestamp),
            number=particle_count,
            radius=self.seed_radius_meters,
        )
        model.run(
            duration=timedelta(hours=hours),
            time_step=direction * timedelta(minutes=self.time_step_minutes),
            time_step_output=timedelta(minutes=self.time_step_minutes),
            stop_on_error=False,
        )
        return _extract_openoil_run(model.result)

    def _reader_bundle(self) -> OpenDriftReaderBundle:
        if not self.current_path or not self.current_path.exists():
            raise EnvironmentDataError("OpenDrift native grid current reader requires a configured Copernicus NetCDF file.")
        if not self.wind_files:
            raise EnvironmentDataError("OpenDrift native grid wind reader requires configured GFS GRIB files.")
        return create_native_grid_readers(self.current_path, self.wind_files)


def create_native_grid_readers(current_path: Path, wind_files: list[Path]) -> OpenDriftReaderBundle:
    try:
        _import_opendrift_package()
        from opendrift.readers import reader_netCDF_CF_generic
    except Exception as exc:
        raise OpenDriftUnavailableError(str(exc)) from exc

    current_reader = reader_netCDF_CF_generic.Reader(
        str(current_path),
        name="copernicus-currents",
        standard_name_mapping={"uo": OPENDRIFT_VARIABLE_MAPPING["current_u_mps"], "vo": OPENDRIFT_VARIABLE_MAPPING["current_v_mps"]},
    )
    wind_dataset, wind_metadata = _build_gfs_wind_dataset(wind_files)
    wind_reader = reader_netCDF_CF_generic.Reader(wind_dataset, name="noaa-gfs-wind")
    reader_class = "opendrift.readers.reader_netCDF_CF_generic.Reader"
    return OpenDriftReaderBundle(
        current_reader=current_reader,
        wind_reader=wind_reader,
        current_reader_class=reader_class,
        wind_reader_class=reader_class,
        metadata={
            "current": {
                "path": str(current_path),
                "source_variables": {"uo": OPENDRIFT_VARIABLE_MAPPING["current_u_mps"], "vo": OPENDRIFT_VARIABLE_MAPPING["current_v_mps"]},
            },
            "wind": wind_metadata,
        },
    )


def query_native_reader_values(
    current_path: Path,
    wind_files: list[Path],
    *,
    latitude: float,
    longitude: float,
    timestamp: datetime,
) -> dict[str, float | dict[str, object]]:
    readers = create_native_grid_readers(current_path, wind_files)
    time_value = _opendrift_datetime(timestamp)
    current, _ = readers.current_reader.get_variables_interpolated(
        [OPENDRIFT_VARIABLE_MAPPING["current_u_mps"], OPENDRIFT_VARIABLE_MAPPING["current_v_mps"]],
        lon=[longitude],
        lat=[latitude],
        z=[0],
        time=time_value,
    )
    wind, _ = readers.wind_reader.get_variables_interpolated(
        [OPENDRIFT_VARIABLE_MAPPING["wind_u_mps"], OPENDRIFT_VARIABLE_MAPPING["wind_v_mps"]],
        lon=[longitude],
        lat=[latitude],
        z=[0],
        time=time_value,
    )
    return {
        "current_u_mps": _first_float(current[OPENDRIFT_VARIABLE_MAPPING["current_u_mps"]]),
        "current_v_mps": _first_float(current[OPENDRIFT_VARIABLE_MAPPING["current_v_mps"]]),
        "wind_u_mps": _first_float(wind[OPENDRIFT_VARIABLE_MAPPING["wind_u_mps"]]),
        "wind_v_mps": _first_float(wind[OPENDRIFT_VARIABLE_MAPPING["wind_v_mps"]]),
        "source_metadata": readers.metadata,
    }


def _build_gfs_wind_dataset(wind_files: list[Path]):
    try:
        import xarray as xr
    except ImportError as exc:
        raise EnvironmentDataError("xarray/cfgrib/eccodes are required to build the GFS OpenDrift wind reader.") from exc

    u_slices = []
    v_slices = []
    times = []
    files_metadata: list[dict[str, object]] = []
    for path in sorted(wind_files):
        with xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""}) as dataset:
            if "u10" not in dataset.data_vars or "v10" not in dataset.data_vars:
                raise EnvironmentDataError(f"GFS file {path} must contain both u10 and v10 for native-grid OpenDrift forcing.")
            valid_time = np.datetime64(dataset["valid_time"].values)
            times.append(valid_time)
            u_slices.append(dataset["u10"].load())
            v_slices.append(dataset["v10"].load())
            files_metadata.append(
                {
                    "path": str(path),
                    "source_variables": {"u10": OPENDRIFT_VARIABLE_MAPPING["wind_u_mps"], "v10": OPENDRIFT_VARIABLE_MAPPING["wind_v_mps"]},
                    "valid_time": str(valid_time),
                    "height_above_ground_m": float(dataset["heightAboveGround"].values)
                    if "heightAboveGround" in dataset
                    else None,
                }
            )

    u = xr.concat(u_slices, dim="time").assign_coords(time=times).sortby("time")
    v = xr.concat(v_slices, dim="time").assign_coords(time=times).sortby("time")
    wind = xr.Dataset({OPENDRIFT_VARIABLE_MAPPING["wind_u_mps"]: u, OPENDRIFT_VARIABLE_MAPPING["wind_v_mps"]: v})
    wind[OPENDRIFT_VARIABLE_MAPPING["wind_u_mps"]].attrs.update({"standard_name": OPENDRIFT_VARIABLE_MAPPING["wind_u_mps"], "units": "m s-1"})
    wind[OPENDRIFT_VARIABLE_MAPPING["wind_v_mps"]].attrs.update({"standard_name": OPENDRIFT_VARIABLE_MAPPING["wind_v_mps"], "units": "m s-1"})
    wind["longitude"].attrs["standard_name"] = "longitude"
    wind["latitude"].attrs["standard_name"] = "latitude"
    return wind, {"files": files_metadata, "valid_times": [str(value) for value in times]}


def _constant_reader_values(forcing: EnvironmentalForcing) -> dict[str, float]:
    return {
        OPENDRIFT_VARIABLE_MAPPING["current_u_mps"]: forcing.current_u_mps,
        OPENDRIFT_VARIABLE_MAPPING["current_v_mps"]: forcing.current_v_mps,
        OPENDRIFT_VARIABLE_MAPPING["wind_u_mps"]: forcing.wind_u_mps,
        OPENDRIFT_VARIABLE_MAPPING["wind_v_mps"]: forcing.wind_v_mps,
    }


def _extract_openoil_run(result: Any) -> OpenDriftRun:
    lon = np.asarray(result.lon.values, dtype=float)
    lat = np.asarray(result.lat.values, dtype=float)
    status = np.asarray(result.status.values, dtype=float) if "status" in result else np.zeros_like(lon)

    centroids: list[GeoCoordinate] = []
    for time_index in range(lon.shape[1]):
        valid = np.isfinite(lon[:, time_index]) & np.isfinite(lat[:, time_index]) & (status[:, time_index] == 0)
        if not valid.any():
            continue
        centroids.append(
            GeoCoordinate(
                latitude=float(np.mean(lat[valid, time_index])),
                longitude=float(np.mean(lon[valid, time_index])),
            )
        )

    final_valid = np.isfinite(lon[:, -1]) & np.isfinite(lat[:, -1]) & (status[:, -1] == 0)
    final_particles = [
        (float(latitude), float(longitude))
        for latitude, longitude in zip(lat[final_valid, -1], lon[final_valid, -1], strict=False)
    ]
    return OpenDriftRun(
        final_particles=final_particles,
        centroids=centroids,
        active_count=len(final_particles),
        deactivated_count=int(np.count_nonzero(~final_valid)),
    )


def _first_float(values: Any) -> float:
    value = float(np.asarray(values, dtype=float).reshape(-1)[0])
    if not np.isfinite(value):
        raise EnvironmentDataError("OpenDrift native reader returned missing environmental forcing at the requested point/time.")
    return value


def _coordinate_dict(coordinate: GeoCoordinate) -> dict[str, float]:
    return {"latitude": coordinate.latitude, "longitude": coordinate.longitude}


def _opendrift_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _import_opendrift_package() -> Any:
    repo_root = Path(__file__).resolve().parents[4]
    os.environ.setdefault("MPLCONFIGDIR", str(repo_root / ".mpl-cache"))
    import opendrift

    return opendrift

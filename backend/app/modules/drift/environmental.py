from dataclasses import dataclass
from datetime import datetime
from glob import glob
import math
from pathlib import Path
from typing import Protocol

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class EnvironmentalForcing:
    current_u_mps: float
    current_v_mps: float
    wind_u_mps: float
    wind_v_mps: float
    source_metadata: dict[str, object] | None = None


class EnvironmentDataError(RuntimeError):
    pass


class CurrentUnavailableError(EnvironmentDataError):
    pass


class WindUnavailableError(EnvironmentDataError):
    pass


@dataclass(frozen=True)
class CurrentGridCell:
    latitude: float
    longitude: float
    current_u_mps: float
    current_v_mps: float
    distance_km: float


@dataclass(frozen=True)
class GribMessageInfo:
    file: str
    short_name: str
    name: str
    type_of_level: str
    level: float | int
    valid_time: str
    units: str


class EnvironmentalProvider(Protocol):
    mode: str

    def get_forcing(self, latitude: float, longitude: float, timestamp: datetime) -> EnvironmentalForcing:
        ...


class RealDataEnvironmentProvider:
    mode = "real_data"

    def __init__(
        self,
        current_path: str | None = None,
        wind_glob: str | None = None,
        variable_mapping: dict[str, str] | None = None,
        max_nearest_current_distance_km: float = 10.0,
    ) -> None:
        self.current_path = self._resolve_path(current_path) if current_path else None
        self.wind_glob = wind_glob
        self.variable_mapping = variable_mapping or {}
        self.max_nearest_current_distance_km = max_nearest_current_distance_km
        self._current_dataset = None
        self._wind_cache: tuple[object, object, list[dict[str, object]]] | None = None

    def is_ready(self) -> bool:
        return bool(self.current_path and self.current_path.exists() and self.wind_files)

    @property
    def wind_files(self) -> list[Path]:
        if not self.wind_glob:
            return []
        matches = glob(self.wind_glob)
        if not matches:
            matches = glob(str(BACKEND_ROOT / self.wind_glob))
        if not matches:
            matches = glob(str(REPO_ROOT / self.wind_glob))
        return sorted(Path(path).resolve() for path in matches)

    def _resolve_path(self, path: str) -> Path:
        raw_path = Path(path)
        candidates = [
            raw_path,
            BACKEND_ROOT / raw_path,
            REPO_ROOT / raw_path,
        ]
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.exists():
                return resolved
        return (BACKEND_ROOT / raw_path).resolve()

    def get_forcing(self, latitude: float, longitude: float, timestamp: datetime) -> EnvironmentalForcing:
        if not self.is_ready():
            raise EnvironmentDataError("Real current NetCDF or wind GRIB files are not configured or available.")

        current_u, current_v, current_meta = self._read_current(latitude, longitude, timestamp)
        wind_u, wind_v, wind_meta = self._read_wind(latitude, longitude, timestamp)
        return EnvironmentalForcing(
            current_u_mps=current_u,
            current_v_mps=current_v,
            wind_u_mps=wind_u,
            wind_v_mps=wind_v,
            source_metadata={
                "current": current_meta,
                "wind": wind_meta,
            },
        )

    def nearest_valid_current_cells(
        self,
        latitude: float,
        longitude: float,
        timestamp: datetime,
        limit: int = 10,
    ) -> list[CurrentGridCell]:
        if not self.current_path or not self.current_path.exists():
            raise EnvironmentDataError("Current NetCDF file is not configured or available.")

        dataset = self._get_current_dataset()
        u_name = self.variable_mapping.get("current_u") or self._find_var(dataset, ["uo"], "eastward")
        v_name = self.variable_mapping.get("current_v") or self._find_var(dataset, ["vo"], "northward")
        if not u_name or not v_name:
            raise EnvironmentDataError("Current file does not contain discoverable u/v current variables.")

        selected = dataset[[u_name, v_name]].sel(
            time=np.datetime64(timestamp.replace(tzinfo=None)),
            method="nearest",
        )
        if "depth" in selected.dims:
            selected = selected.isel(depth=0)

        cells: list[CurrentGridCell] = []
        u_values = selected[u_name].values
        v_values = selected[v_name].values
        for lat_index, candidate_lat in enumerate(dataset["latitude"].values):
            for lon_index, candidate_lon in enumerate(dataset["longitude"].values):
                current_u = float(u_values[lat_index, lon_index])
                current_v = float(v_values[lat_index, lon_index])
                if np.isfinite(current_u) and np.isfinite(current_v):
                    cells.append(
                        CurrentGridCell(
                            latitude=float(candidate_lat),
                            longitude=float(candidate_lon),
                            current_u_mps=current_u,
                            current_v_mps=current_v,
                            distance_km=haversine_distance_km(
                                latitude,
                                longitude,
                                float(candidate_lat),
                                float(candidate_lon),
                            ),
                        )
                    )

        return sorted(cells, key=lambda cell: cell.distance_km)[:limit]

    def inspect_grib_messages(self) -> list[GribMessageInfo]:
        try:
            from eccodes import codes_get, codes_grib_new_from_file, codes_release
        except ImportError as exc:
            raise EnvironmentDataError("eccodes is required for GRIB message inspection.") from exc

        messages: list[GribMessageInfo] = []
        for path in self.wind_files:
            with open(path, "rb") as handle:
                while True:
                    message_id = codes_grib_new_from_file(handle)
                    if message_id is None:
                        break
                    try:
                        data_date = int(codes_get(message_id, "validityDate"))
                        data_time = int(codes_get(message_id, "validityTime"))
                        valid_time = f"{data_date:08d}T{data_time:04d}"
                        messages.append(
                            GribMessageInfo(
                                file=str(path),
                                short_name=str(codes_get(message_id, "shortName")),
                                name=str(codes_get(message_id, "name")),
                                type_of_level=str(codes_get(message_id, "typeOfLevel")),
                                level=codes_get(message_id, "level"),
                                valid_time=valid_time,
                                units=str(codes_get(message_id, "units")),
                            )
                        )
                    finally:
                        codes_release(message_id)
        return messages

    def _read_current(self, latitude: float, longitude: float, timestamp: datetime) -> tuple[float, float, dict[str, object]]:
        dataset = self._get_current_dataset()
        u_name = self.variable_mapping.get("current_u") or self._find_var(dataset, ["uo"], "eastward")
        v_name = self.variable_mapping.get("current_v") or self._find_var(dataset, ["vo"], "northward")
        if not u_name or not v_name:
            raise EnvironmentDataError("Current file does not contain discoverable u/v current variables.")

        self._validate_coverage(dataset, latitude, longitude, timestamp, source="current")
        selected = dataset[[u_name, v_name]].interp(
            latitude=latitude,
            longitude=longitude,
            time=np.datetime64(timestamp.replace(tzinfo=None)),
            method="linear",
        )
        if "depth" in selected.dims:
            selected = selected.isel(depth=0)

        current_u = float(selected[u_name].values)
        current_v = float(selected[v_name].values)
        metadata = self._current_metadata(dataset, u_name, v_name)
        if np.isfinite(current_u) and np.isfinite(current_v):
            metadata["interpolation_method"] = "linear"
            return current_u, current_v, metadata

        nearest_cells = self.nearest_valid_current_cells(latitude, longitude, timestamp, limit=1)
        if not nearest_cells or nearest_cells[0].distance_km > self.max_nearest_current_distance_km:
            nearest_distance = nearest_cells[0].distance_km if nearest_cells else None
            raise CurrentUnavailableError(
                "Current values are missing/masked and no finite Copernicus grid cell was found "
                f"within {self.max_nearest_current_distance_km} km. Nearest distance: {nearest_distance}."
            )

        nearest = nearest_cells[0]
        substitution = {
            "requested_position": {"latitude": latitude, "longitude": longitude},
            "substituted_grid_position": {"latitude": nearest.latitude, "longitude": nearest.longitude},
            "distance_km": nearest.distance_km,
            "current_u_mps": nearest.current_u_mps,
            "current_v_mps": nearest.current_v_mps,
            "timestamp": timestamp.isoformat(),
            "max_distance_km": self.max_nearest_current_distance_km,
        }
        metadata["interpolation_method"] = "nearest_valid_current_cell_for_masked_source"
        metadata["nearest_current_substitution"] = substitution
        return nearest.current_u_mps, nearest.current_v_mps, metadata

    def _read_wind(self, latitude: float, longitude: float, timestamp: datetime) -> tuple[float, float, dict[str, object]]:
        u, v, metadata = self._get_wind_arrays()
        self._validate_coverage(u, latitude, longitude, None, source="wind")
        target_time = np.datetime64(timestamp.replace(tzinfo=None))
        if target_time < u.valid_time.min().values or target_time > u.valid_time.max().values:
            raise WindUnavailableError("Requested timestamp is outside wind GRIB valid_time coverage.")

        selected_u = u.interp(valid_time=target_time, latitude=latitude, longitude=longitude, method="linear")
        selected_v = v.interp(valid_time=target_time, latitude=latitude, longitude=longitude, method="linear")
        wind_u = float(selected_u.values)
        wind_v = float(selected_v.values)
        if not np.isfinite(wind_u) or not np.isfinite(wind_v):
            raise WindUnavailableError("Wind values are missing at requested coordinate/time; no extrapolation performed.")

        return wind_u, wind_v, {
            "files": metadata,
            "valid_times": [str(value) for value in u.valid_time.values],
        }

    def _get_current_dataset(self):
        if self._current_dataset is None:
            try:
                import xarray as xr
            except ImportError as exc:
                raise EnvironmentDataError("xarray/netCDF4 are required to read Copernicus NetCDF currents.") from exc
            self._current_dataset = xr.open_dataset(self.current_path)
        return self._current_dataset

    def _get_wind_arrays(self):
        if self._wind_cache is not None:
            return self._wind_cache

        try:
            import xarray as xr
        except ImportError as exc:
            raise WindUnavailableError("xarray/cfgrib/eccodes are required to read GFS GRIB2 winds.") from exc

        u_slices = []
        v_slices = []
        metadata: list[dict[str, object]] = []
        missing_u_files: list[str] = []
        missing_v_files: list[str] = []
        for path in self.wind_files:
            with xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""}) as dataset:
                u_name = self.variable_mapping.get("wind_u") or self._find_var(dataset, ["u10", "10u"], "eastward")
                v_name = self.variable_mapping.get("wind_v") or self._find_var(dataset, ["v10", "10v"], "northward")
                if not u_name:
                    missing_u_files.append(str(path))
                if not v_name:
                    missing_v_files.append(str(path))
                if not u_name or not v_name:
                    metadata.append(self._wind_file_metadata(path, dataset, u_name, v_name))
                    continue

                valid_time = np.datetime64(dataset["valid_time"].values)
                u_slices.append(dataset[u_name].expand_dims(valid_time=[valid_time]).load())
                v_slices.append(dataset[v_name].expand_dims(valid_time=[valid_time]).load())
                metadata.append(self._wind_file_metadata(path, dataset, u_name, v_name))

        if missing_u_files or missing_v_files:
            raise WindUnavailableError(
                "Wind GRIB files must include both 10 m U and V wind components. "
                f"Missing U files: {missing_u_files}; missing V files: {missing_v_files}"
            )
        if not u_slices or not v_slices:
            raise WindUnavailableError("No usable wind slices were found.")

        u = xr.concat(u_slices, dim="valid_time").sortby("valid_time")
        v = xr.concat(v_slices, dim="valid_time").sortby("valid_time")
        self._wind_cache = (u, v, metadata)
        return self._wind_cache

    def _find_var(self, dataset, preferred_names: list[str], standard_name_fragment: str) -> str | None:
        for name in preferred_names:
            if name in dataset.data_vars:
                return name
        for name, variable in dataset.data_vars.items():
            attrs = {key: str(value).lower() for key, value in variable.attrs.items()}
            haystack = " ".join(attrs.values()) + " " + name.lower()
            if standard_name_fragment in haystack:
                return name
        return None

    def _validate_coverage(self, dataset, latitude: float, longitude: float, timestamp: datetime | None, source: str) -> None:
        lat_min = float(dataset.latitude.min())
        lat_max = float(dataset.latitude.max())
        lon_min = float(dataset.longitude.min())
        lon_max = float(dataset.longitude.max())
        if not min(lat_min, lat_max) <= latitude <= max(lat_min, lat_max):
            raise EnvironmentDataError(f"Requested latitude is outside {source} spatial coverage.")
        if not min(lon_min, lon_max) <= longitude <= max(lon_min, lon_max):
            raise EnvironmentDataError(f"Requested longitude is outside {source} spatial coverage.")
        if timestamp is not None and "time" in dataset:
            target_time = np.datetime64(timestamp.replace(tzinfo=None))
            if target_time < dataset.time.min().values or target_time > dataset.time.max().values:
                raise EnvironmentDataError(f"Requested timestamp is outside {source} temporal coverage.")

    def _current_metadata(self, dataset, u_name: str, v_name: str) -> dict[str, object]:
        return {
            "path": str(self.current_path),
            "u_variable": u_name,
            "v_variable": v_name,
            "units": {
                u_name: dataset[u_name].attrs.get("units"),
                v_name: dataset[v_name].attrs.get("units"),
            },
            "time_values": [str(value) for value in dataset["time"].values],
            "depth_values": [float(value) for value in dataset["depth"].values] if "depth" in dataset else [],
            "max_nearest_current_distance_km": self.max_nearest_current_distance_km,
        }

    def _wind_file_metadata(self, path: Path, dataset, u_name: str | None, v_name: str | None) -> dict[str, object]:
        return {
            "path": str(path),
            "variables": list(dataset.data_vars),
            "u_variable": u_name,
            "v_variable": v_name,
            "valid_time": str(dataset["valid_time"].values) if "valid_time" in dataset else None,
            "forecast_reference_time": str(dataset["time"].values) if "time" in dataset else None,
            "step": str(dataset["step"].values) if "step" in dataset else None,
            "height_above_ground_m": float(dataset["heightAboveGround"].values)
            if "heightAboveGround" in dataset
            else None,
        }


def haversine_distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    earth_radius_km = 6371.0088
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lon_b - lon_a)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    return 2 * earth_radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))

from dataclasses import dataclass
from datetime import UTC, datetime
import csv
import io
from math import cos, radians
from pathlib import Path
from typing import Iterable, Iterator

from app.modules.attribution.geometry import validate_coordinate


class AISDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class AISRecord:
    mmsi: str
    timestamp: datetime
    latitude: float
    longitude: float
    sog: float
    cog: float
    vessel_name: str | None = None
    ship_type: str | None = None
    heading: float | None = None
    navigation_status: str | None = None


ALIASES = {
    "mmsi": "mmsi",
    "MMSI": "mmsi",
    "timestamp": "timestamp",
    "BaseDateTime": "timestamp",
    "base_datetime": "timestamp",
    "base_date_time": "timestamp",
    "LAT": "latitude",
    "lat": "latitude",
    "latitude": "latitude",
    "LON": "longitude",
    "lon": "longitude",
    "longitude": "longitude",
    "SOG": "sog",
    "sog": "sog",
    "COG": "cog",
    "cog": "cog",
    "VesselName": "vessel_name",
    "vessel_name": "vessel_name",
    "ShipType": "ship_type",
    "ship_type": "ship_type",
    "vessel_type": "ship_type",
    "Heading": "heading",
    "heading": "heading",
    "Status": "navigation_status",
    "status": "navigation_status",
    "navigation_status": "navigation_status",
}


def parse_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def normalize_record(row: dict[str, object]) -> AISRecord:
    normalized: dict[str, object] = {}
    for key, value in row.items():
        mapped = ALIASES.get(key, ALIASES.get(key.strip()))
        if mapped:
            normalized[mapped] = value

    missing = [name for name in ("mmsi", "timestamp", "latitude", "longitude", "sog", "cog") if name not in normalized]
    if missing:
        raise AISDataError(f"AIS record missing required fields: {missing}")

    try:
        latitude = float(normalized["latitude"])
        longitude = float(normalized["longitude"])
        sog = float(normalized["sog"])
        cog = float(normalized["cog"]) % 360
    except (TypeError, ValueError) as exc:
        raise AISDataError("AIS record contains invalid numeric fields.") from exc
    try:
        validate_coordinate(latitude, longitude)
    except ValueError as exc:
        raise AISDataError(str(exc)) from exc
    return AISRecord(
        mmsi=str(normalized["mmsi"]),
        timestamp=parse_timestamp(normalized["timestamp"]),
        latitude=latitude,
        longitude=longitude,
        sog=sog,
        cog=cog,
        vessel_name=_optional_string(normalized.get("vessel_name")),
        ship_type=_optional_string(normalized.get("ship_type")),
        heading=_optional_float(normalized.get("heading")),
        navigation_status=_optional_string(normalized.get("navigation_status")),
    )


def normalize_records(rows: Iterable[dict[str, object]]) -> list[AISRecord]:
    records: list[AISRecord] = []
    for row in rows:
        records.append(normalize_record(row))
    return records


def iter_ais_rows(path: str | Path) -> Iterator[dict[str, object]]:
    data_path = Path(path)
    if not data_path.exists():
        raise AISDataError("AIS data file is not configured or available.")

    if str(data_path).lower().endswith(".csv.zst"):
        try:
            import zstandard as zstd
        except ImportError as exc:
            raise AISDataError("zstandard is required to read compressed AIS .csv.zst files.") from exc
        with data_path.open("rb") as handle:
            decompressor = zstd.ZstdDecompressor()
            with decompressor.stream_reader(handle) as reader:
                text_stream = io.TextIOWrapper(reader, encoding="utf-8-sig", newline="")
                yield from csv.DictReader(text_stream)
        return

    suffix = data_path.suffix.lower()
    if suffix == ".csv":
        with data_path.open("r", newline="", encoding="utf-8-sig") as handle:
            yield from csv.DictReader(handle)
        return
    raise AISDataError("AIS row streaming supports CSV or compressed CSV Zstandard files.")


def load_ais_file(
    path: str | Path,
    max_records: int | None = None,
    time_start: datetime | None = None,
    time_end: datetime | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> list[AISRecord]:
    data_path = Path(path)
    if not data_path.exists():
        raise AISDataError("AIS data file is not configured or available.")

    suffix = data_path.suffix.lower()
    if str(data_path).lower().endswith(".csv.zst") or suffix == ".csv":
        records: list[AISRecord] = []
        for row in iter_ais_rows(data_path):
            try:
                record = normalize_record(row)
            except AISDataError:
                continue
            if time_start and record.timestamp < time_start:
                continue
            if time_end and record.timestamp > time_end:
                continue
            if bbox and not _record_in_bbox(record, bbox):
                continue
            records.append(record)
            if max_records and len(records) >= max_records:
                break
        return records

    if suffix in {".parquet", ".pq"}:
        try:
            import pandas as pd
        except ImportError as exc:
            raise AISDataError("pandas/pyarrow are required to read AIS parquet files.") from exc
        records = normalize_records(pd.read_parquet(data_path).to_dict(orient="records"))
        return _filter_records(records, max_records, time_start, time_end, bbox)
    raise AISDataError("AIS file must be CSV, CSV Zstandard, or parquet.")


def bbox_around_point(latitude: float, longitude: float, radius_km: float) -> tuple[float, float, float, float]:
    lat_delta = radius_km / 111.32
    lon_delta = radius_km / max(111.32 * cos(radians(latitude)), 0.01)
    return latitude - lat_delta, latitude + lat_delta, longitude - lon_delta, longitude + lon_delta


def _filter_records(
    records: list[AISRecord],
    max_records: int | None,
    time_start: datetime | None,
    time_end: datetime | None,
    bbox: tuple[float, float, float, float] | None,
) -> list[AISRecord]:
    filtered = []
    for record in records:
        if time_start and record.timestamp < time_start:
            continue
        if time_end and record.timestamp > time_end:
            continue
        if bbox and not _record_in_bbox(record, bbox):
            continue
        filtered.append(record)
        if max_records and len(filtered) >= max_records:
            break
    return filtered


def _record_in_bbox(record: AISRecord, bbox: tuple[float, float, float, float]) -> bool:
    min_lat, max_lat, min_lon, max_lon = bbox
    return min_lat <= record.latitude <= max_lat and min_lon <= record.longitude <= max_lon


def _optional_string(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: object | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)

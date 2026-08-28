from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "backend"))

from app.modules.attribution.ais_loader import iter_ais_rows, normalize_record


CANDIDATE_BOXES = {
    "New York / New Jersey": (40.0, 41.2, -75.0, -72.5),
    "Norfolk / Chesapeake Bay": (36.5, 38.5, -77.0, -75.0),
    "Los Angeles / Long Beach": (33.2, 34.3, -119.0, -117.0),
    "San Francisco Bay": (37.2, 38.4, -123.3, -121.5),
    "Gulf Coast / Houston": (28.5, 30.5, -96.0, -93.5),
    "Gulf Coast / Mississippi River": (28.0, 31.5, -91.5, -88.0),
}

OUTPUT_COLUMNS = [
    "mmsi",
    "base_date_time",
    "longitude",
    "latitude",
    "sog",
    "cog",
    "heading",
    "vessel_name",
    "vessel_type",
    "status",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a small real AIS validation subset from a raw .csv.zst file.")
    parser.add_argument("--input", default="../data/ais/raw/ais-2024-01-14.csv.zst")
    parser.add_argument("--output", default="../data/ais/processed/ais_real_validation.csv")
    parser.add_argument("--max-vessels", type=int, default=15)
    parser.add_argument("--min-points", type=int, default=8)
    args = parser.parse_args()

    input_path = (Path(__file__).resolve().parent / args.input).resolve()
    output_path = (Path(__file__).resolve().parent / args.output).resolve()

    first_pass = inspect_density(input_path)
    selected_name = max(first_pass["boxes"], key=lambda name: first_pass["boxes"][name]["rows"])
    selected_bbox = CANDIDATE_BOXES[selected_name]
    second_pass = inspect_time_density(input_path, selected_bbox)
    selected_hour = second_pass["top_hour"]
    window_start = selected_hour
    window_end = selected_hour + timedelta(hours=1)
    retained_rows, vessel_counts = collect_subset(input_path, selected_bbox, window_start, window_end, args.max_vessels, args.min_points)

    if not retained_rows:
        raise RuntimeError("No AIS rows retained. Try a different bbox/window or lower --min-points.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(retained_rows)

    latitudes = [float(row["latitude"]) for row in retained_rows]
    longitudes = [float(row["longitude"]) for row in retained_rows]
    result = {
        "raw_file": str(input_path),
        "processed_file": str(output_path),
        "compressed_size_bytes": input_path.stat().st_size,
        "compressed_size_mb": round(input_path.stat().st_size / 1024 / 1024, 2),
        "raw_rows_scanned": first_pass["raw_rows_scanned"],
        "validation_geography": selected_name,
        "validation_bbox": {
            "min_latitude": selected_bbox[0],
            "max_latitude": selected_bbox[1],
            "min_longitude": selected_bbox[2],
            "max_longitude": selected_bbox[3],
        },
        "validation_origin_centroid": {
            "latitude": sum(latitudes) / len(latitudes),
            "longitude": sum(longitudes) / len(longitudes),
        },
        "validation_time_window": {
            "start": window_start.isoformat().replace("+00:00", "Z"),
            "end": window_end.isoformat().replace("+00:00", "Z"),
        },
        "rows_retained": len(retained_rows),
        "vessels_retained": len(vessel_counts),
        "selected_vessels": dict(vessel_counts),
        "scenario": "real AIS algorithm validation scenario",
        "notice": "This does not represent the Mumbai oil-spill demonstration scenario.",
    }
    print(json.dumps(result, indent=2))


def inspect_density(path: Path) -> dict[str, object]:
    raw_rows_scanned = 0
    boxes = {name: {"rows": 0, "vessels": set()} for name in CANDIDATE_BOXES}
    for row in iter_ais_rows(path):
        raw_rows_scanned += 1
        try:
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
            mmsi = str(row["mmsi"])
        except (KeyError, TypeError, ValueError):
            continue
        for name, bbox in CANDIDATE_BOXES.items():
            if in_bbox(latitude, longitude, bbox):
                boxes[name]["rows"] += 1
                boxes[name]["vessels"].add(mmsi)

    return {
        "raw_rows_scanned": raw_rows_scanned,
        "boxes": {
            name: {"rows": data["rows"], "vessels": len(data["vessels"])}
            for name, data in boxes.items()
        },
    }


def inspect_time_density(path: Path, bbox: tuple[float, float, float, float]) -> dict[str, object]:
    hourly_counts: Counter = Counter()
    for row in iter_ais_rows(path):
        try:
            record = normalize_record(row)
        except Exception:
            continue
        if in_bbox(record.latitude, record.longitude, bbox):
            hour = record.timestamp.replace(minute=0, second=0, microsecond=0)
            hourly_counts[hour] += 1
    top_hour = hourly_counts.most_common(1)[0][0]
    return {"top_hour": top_hour, "hourly_counts": {time.isoformat(): count for time, count in hourly_counts.items()}}


def collect_subset(
    path: Path,
    bbox: tuple[float, float, float, float],
    window_start,
    window_end,
    max_vessels: int,
    min_points: int,
) -> tuple[list[dict[str, str]], Counter]:
    rows_by_mmsi: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in iter_ais_rows(path):
        try:
            record = normalize_record(row)
        except Exception:
            continue
        if not in_bbox(record.latitude, record.longitude, bbox):
            continue
        if not window_start <= record.timestamp <= window_end:
            continue
        rows_by_mmsi[record.mmsi].append(_project_row(row))

    vessel_counts = Counter({
        mmsi: len(rows)
        for mmsi, rows in rows_by_mmsi.items()
        if len(rows) >= min_points
    })
    selected_mmsi = [mmsi for mmsi, _ in vessel_counts.most_common(max_vessels)]
    retained_rows = [
        row
        for mmsi in selected_mmsi
        for row in rows_by_mmsi[mmsi]
    ]
    return retained_rows, Counter({mmsi: len(rows_by_mmsi[mmsi]) for mmsi in selected_mmsi})


def in_bbox(latitude: float, longitude: float, bbox: tuple[float, float, float, float]) -> bool:
    min_lat, max_lat, min_lon, max_lon = bbox
    return min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon


def _project_row(row: dict[str, object]) -> dict[str, str]:
    return {column: str(row.get(column, "")) for column in OUTPUT_COLUMNS}


if __name__ == "__main__":
    main()

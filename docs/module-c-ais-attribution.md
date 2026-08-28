# Module C: AIS Correlation and Explainable Vessel Scoring

Module C ranks candidate vessels near an estimated spill origin. It is an investigative aid only and must never be interpreted as legal certainty.

## Input

`POST /score` accepts either the Day-4 shape:

```json
{
  "origin_centroid": {
    "latitude": 18.522014161747748,
    "longitude": 72.78917658819358
  },
  "origin_time_window": {
    "start": "2026-08-26T05:00:00Z",
    "end": "2026-08-26T07:00:00Z"
  },
  "mode": "synthetic_dev"
}
```

or the Day-1-compatible shape with top-level `latitude` and `longitude`.

## AIS Fields

Normalized AIS records require:

```text
MMSI
timestamp
latitude
longitude
SOG
COG
```

Optional fields:

```text
vessel_name
ship_type
heading
navigation_status
```

Common aliases are normalized, including `LAT -> latitude`, `LON -> longitude`, `BaseDateTime -> timestamp`, `base_date_time -> timestamp`, `SOG -> sog`, and `COG -> cog`. Timestamps are parsed as UTC-aware values. Invalid coordinates are rejected.

## Modes

`synthetic_dev` generates deterministic AIS tracks around the Day-3 development origin:

```text
lat=18.522014161747748
lon=72.78917658819358
window=2026-08-26T05:00:00Z to 2026-08-26T07:00:00Z
```

The synthetic set includes vessels passing close to the origin, slowing near the origin, changing course, showing an AIS transmission gap, and normal vessels farther away. This is only for software validation.

`real_data` loads a configured AIS CSV, CSV Zstandard, or parquet file from `AIS_DATA_PATH`. If the file is missing, invalid, or unsupported, the API returns `ais_data_not_ready`. It never silently falls back to synthetic data.

The Marine Cadastre / NOAA `.csv.zst` loader uses streaming Zstandard decompression. The raw compressed national AIS file must not be fully decompressed into the repository.

Local validation paths:

```text
raw source: data/ais/raw/ais-2024-01-14.csv.zst
processed subset: data/ais/processed/ais_real_validation.csv
```

The processed subset can be regenerated with:

```bash
python backend/scripts/validate_real_ais.py --input ../../data/ais/raw/ais-2024-01-14.csv.zst --output ../../data/ais/processed/ais_real_validation.csv
```

Detected raw schema:

```text
mmsi
base_date_time
longitude
latitude
sog
cog
heading
vessel_name
imo
call_sign
vessel_type
status
length
width
draft
cargo
transceiver
```

The current real AIS algorithm validation scenario uses the Gulf Coast / Mississippi River region selected from actual record density in the `2024-01-14` file:

```text
origin latitude: 29.7732211097852
origin longitude: -90.06771383054893
window: 2024-01-14T03:00:00Z to 2024-01-14T04:00:00Z
rows retained: 838
vessels retained: 15
```

The real AIS dataset validates ingestion, trajectory reconstruction, filtering, and scoring behavior. It does not represent the Mumbai oil-spill demonstration scenario.

## Filtering

AIS records are grouped by MMSI and sorted by timestamp. Tracks with fewer than two points in the buffered window are skipped.

Temporal filter:

```text
origin window +/- AIS_TIME_BUFFER_HOURS
default: 2 hours
```

Spatial filter:

```text
minimum distance to origin centroid <= AIS_CANDIDATE_RADIUS_KM
default: 25 km
```

GeoJSON and coordinate handling elsewhere in the pipeline remains longitude/latitude for geometry arrays; AIS records are normalized as latitude and longitude fields.

## Features

The scorer computes deterministic, explainable features:

- proximity to origin centroid
- temporal proximity to origin time window
- trajectory alignment near closest approach
- speed anomaly from SOG variation
- course anomaly from circular COG changes
- AIS transmission gap near the origin window

Circular course changes are handled correctly, so `359` to `2` degrees is treated as a `3` degree change.

AIS gaps are treated as an anomaly signal, not proof of wrongdoing.

## Weights

Initial development weights:

```text
proximity: 30%
temporal proximity: 20%
trajectory alignment: 15%
speed anomaly: 15%
course anomaly: 10%
AIS gap: 10%
```

Scores are reported from `0` to `100` and sorted descending.

Priority bands:

```text
80-100: high investigative priority
60-79: medium investigative priority
<60: low investigative priority
```

These are development bands, not legal conclusions.

## Limitations

The current implementation does not perform legal attribution, dark-vessel detection, port-call analysis, ownership analysis, satellite cross-confirmation, or ML-based vessel scoring. Real AIS integration needs representative regional data, data-quality checks, duplicate handling, and validation with domain experts before operational use.

# Day 5: Backend Pipeline Integration and Persistence

Day 5 connects the completed development modules into a backend orchestration path:

```text
Module A detection
-> user supplied geospatial spill seed
-> Module B drift hindcast/forecast
-> Module C AIS attribution
-> optional PostGIS persistence
```

This is still a development validation pipeline. The synthetic detection checkpoint is not a scientific Sentinel-1 model, the drift engine is still the development drift engine, and AIS scoring is an investigative ranking aid rather than legal attribution.

## Pipeline Input

`POST /pipeline` accepts an optional request body:

```json
{
  "pipeline_mode": "demo",
  "image_path": "data/synthetic_sar/images/sar_001.png",
  "spill_seed": {
    "latitude": 18.5,
    "longitude": 72.8333511352539,
    "timestamp": "2026-08-26T12:00:00Z"
  },
  "drift_mode": "real_data",
  "attribution_mode": "synthetic_dev",
  "persist": true
}
```

`spill_seed` is required for drift and attribution. Module A currently returns image-space pixels, so the pipeline does not convert the synthetic detection centroid into latitude/longitude.

Supported pipeline modes:

```text
detection_only
demo
real_validation
```

## Provenance

The response includes `data_provenance` so reviewers can distinguish development data from real environmental forcing:

```text
SAR/detection model: synthetic development checkpoint
currents: synthetic_dev or Copernicus real data
wind: synthetic_dev or NOAA GFS real data
AIS: synthetic_dev or configured real AIS file
```

The `real_validation` mode is a backend scenario label only. It does not imply scientific validation.

## Persistence

The orchestrator can store pipeline output in PostgreSQL/PostGIS when the database is available.

Tables:

```text
incidents
detections
drift_runs
vessel_candidates
```

Spatial values are stored as SRID 4326 geometries:

```text
seed_point
origin_centroid
origin_polygon
backward_path
forward_path
```

GeoJSON coordinates and WKT conversion use longitude/latitude ordering.

If PostGIS is unavailable, `/pipeline` still returns the computed result and reports:

```json
{
  "persistence": {
    "status": "unavailable"
  }
}
```

The pipeline is not rerun during persistence, and a persistence failure does not fabricate any module output.

## Database Setup

Start the database from the repository root:

```bash
docker compose up -d db
```

Initialize the schema from `backend/`:

```bash
python scripts/init_db.py
```

The script creates the PostGIS extension and Day-5 tables if they do not already exist.

## Retrieval Endpoints

Day 5 adds lightweight backend retrieval endpoints:

```text
GET /incidents
GET /incidents/{incident_id}
GET /incidents/{incident_id}/vessels
```

When the database is unavailable, these endpoints return `persistence_unavailable` instead of failing with an unstructured server error.

## Limitations

The pipeline requires an explicit geospatial spill seed until real georeferenced SAR detections are available. Module A image-space centroids must not be silently treated as geographic coordinates.

The persistence schema is intentionally minimal and designed for collaborative Day-5 validation. Production hardening, migrations tooling, authentication, audit trails, and frontend integration are future work.

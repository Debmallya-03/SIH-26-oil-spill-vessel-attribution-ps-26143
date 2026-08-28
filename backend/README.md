# Marine Oil Spill Intelligence API

Backend for SIH 2026 Problem Statement PS 26143: AI-Powered Marine Oil Spill Detection & Vessel Attribution System.

The backend now includes the Day-5 development pipeline across Module A detection, Module B drift, Module C AIS attribution, and optional PostgreSQL/PostGIS persistence. The current model, drift engine, and AIS scoring remain development validation components, not scientific or legal conclusions.

## Start the Backend

```bash
cd backend
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
uvicorn app.main:app --reload
```

Open Swagger documentation:

```text
http://127.0.0.1:8000/docs
```

## Endpoints

- `GET /` - project identity and documentation location
- `GET /health` - service health check
- `POST /detect` - Module A detection entrypoint; requires `image_path` and a trained checkpoint
- `POST /drift` - Module B drift hindcast/forecast from explicit latitude/longitude input
- `POST /score` - Module C AIS vessel attribution and explainable ranking
- `POST /pipeline` - Day-5 backend orchestration across detection, drift, attribution, and optional persistence
- `GET /incidents` - list persisted pipeline incidents when PostGIS is available
- `GET /incidents/{incident_id}` - retrieve a persisted incident with module outputs
- `GET /incidents/{incident_id}/vessels` - retrieve persisted vessel candidates for an incident

Example detection request:

```json
{
  "image_path": "data/kaggle/data/Class_1/class_1_00001.jpg"
}
```

If `backend/models/unet-baseline.pth` is missing, `/detect` returns `model_not_ready` instead of pretending an untrained model is detecting spills.

## Module A Detection

Inspect the dataset:

```bash
python ..\notebooks\detection\explore_dataset.py
```

Train the segmentation baseline only after real image/mask pairs are added:

```bash
python scripts\train_detection.py --dataset-root ..\data\kaggle --dataset-type classification --epochs 3 --batch-size 4 --image-size 256 --output-path models\unet-baseline.pth
```

The current `data/kaggle` dataset is binary chip classification data (`Class_0`, `Class_1`) and does not contain semantic segmentation masks. The training script detects this and skips training safely.

Synthetic development smoke-test command:

```bash
python scripts\train_detection.py --dataset-root ..\data\synthetic_sar --dataset-type synthetic_dev --epochs 20 --batch-size 2 --image-size 128 --learning-rate 0.0001 --output-path models\unet-synthetic-dev.pth
```

The synthetic checkpoint name intentionally includes `synthetic` and `dev`. It is only for software pipeline validation and must not be presented as real Sentinel-1 model performance.

## Module B Drift

Development scenario:

```json
{
  "latitude": 18.5204,
  "longitude": 72.89,
  "timestamp": "2026-08-26T12:00:00Z"
}
```

The drift module supports `synthetic_dev` forcing and `real_data` forcing from local Copernicus current and NOAA GFS wind files. The engine remains the development drift engine, not OpenDrift/OpenOil.

## Module C AIS Attribution

Synthetic development scoring request:

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

Module C returns ranked candidate vessels with factor scores and concise reasons. AIS gaps are treated as anomaly signals, not proof of wrongdoing.

## Day-5 Pipeline

Development demo request:

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

`spill_seed` is required for drift and attribution because Module A currently returns image-space pixels, not georeferenced latitude/longitude.

If PostgreSQL/PostGIS is unavailable, the pipeline still returns computed module output and reports persistence as unavailable.

## Database

Start PostGIS from the repository root:

```bash
docker compose up -d db
```

Initialize Day-5 tables from `backend/`:

```bash
python scripts/init_db.py
```

Tables created:

```text
incidents
detections
drift_runs
vessel_candidates
```

## Environment

Copy `.env.example` to `.env` if local overrides are needed.

```env
APP_NAME=Marine Oil Spill Intelligence API
APP_VERSION=0.1.0
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=oilspill
DATABASE_USER=oilspill_user
DATABASE_PASSWORD=change_me_for_local_dev
DATABASE_CONNECT_TIMEOUT_SECONDS=2
FRONTEND_ORIGIN=http://localhost:5173
DETECTION_MODEL_PATH=models/unet-synthetic-dev.pth
DRIFT_ENVIRONMENT_MODE=synthetic_dev
DRIFT_BACKWARD_HOURS=6
DRIFT_FORWARD_HOURS=6
DRIFT_PARTICLE_COUNT=100
DRIFT_RANDOM_SEED=42
DRIFT_WINDAGE_FACTOR=0.03
DRIFT_MAX_NEAREST_CURRENT_DISTANCE_KM=10.0
DRIFT_ENVIRONMENT_DATA_PATH=
AIS_MODE=synthetic_dev
AIS_DATA_PATH=
AIS_CANDIDATE_RADIUS_KM=25.0
AIS_TIME_BUFFER_HOURS=2.0
AIS_GAP_THRESHOLD_MINUTES=15.0
AIS_MAX_REAL_RECORDS=20000
```

For local synthetic development only, override:

```env
DETECTION_MODEL_PATH=models/unet-synthetic-dev.pth
```

For real AIS scoring, keep raw AIS files outside Git and set either the raw compressed source:

```env
AIS_MODE=real_data
AIS_DATA_PATH=../data/ais/raw/ais-2024-01-14.csv.zst
```

or the recommended small repeatable validation subset:

```env
AIS_MODE=real_data
AIS_DATA_PATH=../data/ais/processed/ais_real_validation.csv
```

Build the subset with:

```bash
python scripts\validate_real_ais.py --input ..\..\data\ais\raw\ais-2024-01-14.csv.zst --output ..\..\data\ais\processed\ais_real_validation.csv
```

The real AIS dataset validates ingestion, trajectory reconstruction, filtering, and scoring behavior. It does not represent the Mumbai oil-spill demonstration scenario.

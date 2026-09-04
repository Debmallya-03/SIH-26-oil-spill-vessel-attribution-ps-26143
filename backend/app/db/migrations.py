from app.db.connection import get_connection


SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scenario TEXT NOT NULL,
    status TEXT NOT NULL,
    pipeline_mode TEXT NOT NULL,
    input_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS detections (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    confidence DOUBLE PRECISION,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS drift_runs (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    seed_point GEOMETRY(Point, 4326),
    origin_centroid GEOMETRY(Point, 4326),
    origin_polygon GEOMETRY(Polygon, 4326),
    origin_start TIMESTAMPTZ,
    origin_end TIMESTAMPTZ,
    backward_path GEOMETRY(LineString, 4326),
    forward_path GEOMETRY(LineString, 4326),
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vessel_candidates (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    rank INTEGER,
    mmsi TEXT,
    vessel_name TEXT,
    score DOUBLE PRECISION,
    priority TEXT,
    minimum_distance_km DOUBLE PRECISION,
    nearest_approach_time TIMESTAMPTZ,
    factors JSONB NOT NULL DEFAULT '{}'::jsonb,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    trajectory GEOMETRY(LineString, 4326),
    trajectory_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    trajectory_source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE vessel_candidates
    ADD COLUMN IF NOT EXISTS trajectory_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS trajectory_source TEXT;
"""


def initialize_database() -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(SCHEMA_SQL)
        connection.commit()

from datetime import datetime
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseUnavailableError, get_connection
from app.schemas.detection import GeoCoordinate
from app.schemas.drift import DriftResponse, LineStringGeometry, PolygonGeometry
from app.schemas.pipeline import PipelineRequest, PipelineResponse
from app.schemas.scoring import ScoreResponse


def persist_pipeline_result(result: PipelineResponse, request: PipelineRequest) -> None:
    with get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                incident_uuid = UUID(result.incident_id)
                cursor.execute(
                    """
                    INSERT INTO incidents (id, scenario, status, pipeline_mode, input_metadata, provenance)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        incident_uuid,
                        result.scenario,
                        result.status,
                        request.pipeline_mode,
                        Jsonb(request.model_dump(mode="json")),
                        Jsonb(result.data_provenance),
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO detections (id, incident_id, status, confidence, result)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        uuid4(),
                        incident_uuid,
                        result.detection.status,
                        result.detection.confidence,
                        Jsonb(result.detection.model_dump(mode="json")),
                    ),
                )
                if result.drift is not None:
                    _insert_drift(cursor, incident_uuid, result.drift, request)
                if result.attribution is not None:
                    _insert_vessels(cursor, incident_uuid, result.attribution)
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def list_incidents() -> list[dict[str, object]]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, created_at, scenario, status, pipeline_mode, provenance
                FROM incidents
                ORDER BY created_at DESC
                LIMIT 100
                """
            )
            return [
                {
                    "incident_id": row[0],
                    "created_at": row[1],
                    "scenario": row[2],
                    "status": row[3],
                    "pipeline_mode": row[4],
                    "provenance": row[5],
                }
                for row in cursor.fetchall()
            ]


def get_incident(incident_id: str) -> dict[str, object] | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id::text, created_at, scenario, status, pipeline_mode, input_metadata, provenance FROM incidents WHERE id = %s",
                (incident_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            incident = {
                "id": row[0],
                "created_at": row[1],
                "scenario": row[2],
                "status": row[3],
                "pipeline_mode": row[4],
                "input_metadata": row[5],
                "provenance": row[6],
            }
            cursor.execute("SELECT result FROM detections WHERE incident_id = %s ORDER BY created_at DESC LIMIT 1", (incident_id,))
            detection_row = cursor.fetchone()
            cursor.execute("SELECT result FROM drift_runs WHERE incident_id = %s ORDER BY created_at DESC LIMIT 1", (incident_id,))
            drift_row = cursor.fetchone()
            vessels = get_vessel_candidates_for_incident(incident_id)
            return {
                "incident": incident,
                "detection": detection_row[0] if detection_row else None,
                "drift": drift_row[0] if drift_row else None,
                "vessel_candidates": vessels,
            }


def get_vessel_candidates_for_incident(incident_id: str) -> list[dict[str, object]]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            _ensure_vessel_trajectory_columns(cursor)
            connection.commit()
            cursor.execute(
                """
                SELECT rank, mmsi, vessel_name, score, priority, minimum_distance_km,
                       nearest_approach_time, factors, reasons, trajectory_points, trajectory_source
                FROM vessel_candidates
                WHERE incident_id = %s
                ORDER BY rank NULLS LAST, score DESC
                """,
                (incident_id,),
            )
            return [
                {
                    "rank": row[0],
                    "mmsi": row[1],
                    "vessel_name": row[2],
                    "score": row[3],
                    "priority": row[4],
                    "minimum_distance_km": row[5],
                    "nearest_approach_time": row[6],
                    "factors": row[7],
                    "reasons": row[8],
                    "trajectory": row[9] or [],
                    "trajectory_source": row[10],
                }
                for row in cursor.fetchall()
            ]


def _insert_drift(cursor, incident_uuid: UUID, drift: DriftResponse, request: PipelineRequest) -> None:
    seed_point = _point_wkt(request.spill_seed.latitude, request.spill_seed.longitude) if request.spill_seed else None
    cursor.execute(
        """
        INSERT INTO drift_runs (
            id, incident_id, status, seed_point, origin_centroid, origin_polygon,
            origin_start, origin_end, backward_path, forward_path, result
        )
        VALUES (
            %s, %s, %s,
            ST_SetSRID(ST_GeomFromText(%s), 4326),
            ST_SetSRID(ST_GeomFromText(%s), 4326),
            ST_SetSRID(ST_GeomFromText(%s), 4326),
            %s, %s,
            ST_SetSRID(ST_GeomFromText(%s), 4326),
            ST_SetSRID(ST_GeomFromText(%s), 4326),
            %s
        )
        """,
        (
            uuid4(),
            incident_uuid,
            drift.status,
            seed_point,
            _point_wkt_from_coordinate(drift.origin_centroid),
            _polygon_wkt(drift.origin_area),
            drift.origin_time_window.start if drift.origin_time_window else None,
            drift.origin_time_window.end if drift.origin_time_window else None,
            _line_wkt(drift.backward_path),
            _line_wkt(drift.forward_path),
            Jsonb(drift.model_dump(mode="json")),
        ),
    )


def _insert_vessels(cursor, incident_uuid: UUID, attribution: ScoreResponse) -> None:
    _ensure_vessel_trajectory_columns(cursor)
    for vessel in attribution.suspects:
        cursor.execute(
            """
            INSERT INTO vessel_candidates (
                id, incident_id, rank, mmsi, vessel_name, score, priority,
                minimum_distance_km, nearest_approach_time, factors, reasons,
                trajectory, trajectory_points, trajectory_source
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                ST_SetSRID(ST_GeomFromText(%s), 4326), %s, %s
            )
            """,
            (
                uuid4(),
                incident_uuid,
                vessel.rank,
                vessel.mmsi,
                vessel.vessel_name,
                vessel.score,
                vessel.priority,
                vessel.minimum_distance_km,
                vessel.nearest_approach_time,
                Jsonb(vessel.factors.model_dump(mode="json")),
                Jsonb(vessel.reasons),
                _trajectory_line_wkt(vessel.trajectory),
                Jsonb([point.model_dump(mode="json") for point in vessel.trajectory]),
                vessel.trajectory_source,
            ),
        )


def _point_wkt(latitude: float, longitude: float) -> str:
    return f"POINT({longitude} {latitude})"


def _point_wkt_from_coordinate(coordinate: GeoCoordinate | None) -> str | None:
    if coordinate is None:
        return None
    return _point_wkt(coordinate.latitude, coordinate.longitude)


def _line_wkt(line: LineStringGeometry | None) -> str | None:
    if line is None or len(line.coordinates) < 2:
        return None
    return "LINESTRING(" + ", ".join(f"{longitude} {latitude}" for longitude, latitude in line.coordinates) + ")"


def _polygon_wkt(polygon: PolygonGeometry | None) -> str | None:
    if polygon is None or not polygon.coordinates:
        return None
    ring = polygon.coordinates[0]
    if len(ring) < 4:
        return None
    return "POLYGON((" + ", ".join(f"{longitude} {latitude}" for longitude, latitude in ring) + "))"


def _trajectory_line_wkt(points) -> str | None:
    if len(points) < 2:
        return None
    return "LINESTRING(" + ", ".join(f"{point.longitude} {point.latitude}" for point in points) + ")"


def _ensure_vessel_trajectory_columns(cursor) -> None:
    cursor.execute(
        """
        ALTER TABLE vessel_candidates
            ADD COLUMN IF NOT EXISTS trajectory_points JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS trajectory_source TEXT
        """
    )

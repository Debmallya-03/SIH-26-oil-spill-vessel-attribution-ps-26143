from dataclasses import dataclass
from datetime import datetime

from app.modules.attribution.ais_loader import AISRecord
from app.modules.attribution.geometry import haversine_distance_km


@dataclass(frozen=True)
class VesselTrack:
    mmsi: str
    vessel_name: str
    points: list[AISRecord]


def build_tracks(records: list[AISRecord]) -> list[VesselTrack]:
    grouped: dict[str, list[AISRecord]] = {}
    for record in records:
        grouped.setdefault(record.mmsi, []).append(record)

    tracks: list[VesselTrack] = []
    for mmsi, points in grouped.items():
        sorted_points = sorted(points, key=lambda point: point.timestamp)
        name = next((point.vessel_name for point in sorted_points if point.vessel_name), f"Vessel {mmsi}")
        tracks.append(VesselTrack(mmsi=mmsi, vessel_name=name, points=sorted_points))
    return tracks


def filter_track_by_time(track: VesselTrack, start: datetime, end: datetime) -> VesselTrack | None:
    points = [point for point in track.points if start <= point.timestamp <= end]
    if len(points) < 2:
        return None
    return VesselTrack(mmsi=track.mmsi, vessel_name=track.vessel_name, points=points)


def nearest_point_to_origin(track: VesselTrack, latitude: float, longitude: float) -> tuple[AISRecord, float, int]:
    distances = [
        haversine_distance_km(point.latitude, point.longitude, latitude, longitude)
        for point in track.points
    ]
    index = min(range(len(distances)), key=distances.__getitem__)
    return track.points[index], distances[index], index


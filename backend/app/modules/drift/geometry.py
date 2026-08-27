from math import cos, radians

from app.schemas.detection import GeoCoordinate
from app.schemas.drift import LineStringGeometry, PolygonGeometry

EARTH_METERS_PER_DEGREE_LAT = 111_320.0


def validate_coordinate(latitude: float, longitude: float) -> None:
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")


def meters_to_degrees(east_meters: float, north_meters: float, latitude: float) -> tuple[float, float]:
    latitude_delta = north_meters / EARTH_METERS_PER_DEGREE_LAT
    longitude_scale = EARTH_METERS_PER_DEGREE_LAT * max(0.01, cos(radians(latitude)))
    longitude_delta = east_meters / longitude_scale
    return latitude_delta, longitude_delta


def move_coordinate(latitude: float, longitude: float, east_meters: float, north_meters: float) -> tuple[float, float]:
    latitude_delta, longitude_delta = meters_to_degrees(east_meters, north_meters, latitude)
    return latitude + latitude_delta, longitude + longitude_delta


def particle_centroid(particles: list[tuple[float, float]]) -> GeoCoordinate:
    latitude = sum(point[0] for point in particles) / len(particles)
    longitude = sum(point[1] for point in particles) / len(particles)
    return GeoCoordinate(latitude=latitude, longitude=longitude)


def line_string_from_coordinates(points: list[GeoCoordinate]) -> LineStringGeometry:
    return LineStringGeometry(coordinates=[[point.longitude, point.latitude] for point in points])


def _cross(origin: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    unique_points = sorted(set(points))
    if len(unique_points) <= 1:
        return unique_points

    lower: list[tuple[float, float]] = []
    for point in unique_points:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(unique_points):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    return lower[:-1] + upper[:-1]


def origin_polygon_from_particles(particles: list[tuple[float, float]]) -> PolygonGeometry:
    lon_lat_points = [(longitude, latitude) for latitude, longitude in particles]
    hull = convex_hull(lon_lat_points)
    if len(hull) < 3:
        longitudes = [point[1] for point in particles]
        latitudes = [point[0] for point in particles]
        min_lon, max_lon = min(longitudes), max(longitudes)
        min_lat, max_lat = min(latitudes), max(latitudes)
        hull = [
            (min_lon, min_lat),
            (max_lon, min_lat),
            (max_lon, max_lat),
            (min_lon, max_lat),
        ]

    coordinates = [[list(point) for point in hull]]
    if coordinates[0][0] != coordinates[0][-1]:
        coordinates[0].append(coordinates[0][0])
    return PolygonGeometry(coordinates=coordinates)

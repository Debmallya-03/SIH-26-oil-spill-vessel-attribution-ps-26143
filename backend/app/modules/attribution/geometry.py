from math import atan2, cos, degrees, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088


def validate_coordinate(latitude: float, longitude: float) -> None:
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")


def haversine_distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    phi_a = radians(lat_a)
    phi_b = radians(lat_b)
    delta_phi = radians(lat_b - lat_a)
    delta_lambda = radians(lon_b - lon_a)
    a = sin(delta_phi / 2) ** 2 + cos(phi_a) * cos(phi_b) * sin(delta_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * atan2(sqrt(a), sqrt(1 - a))


def bearing_degrees(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    phi_a = radians(lat_a)
    phi_b = radians(lat_b)
    delta_lambda = radians(lon_b - lon_a)
    y = sin(delta_lambda) * cos(phi_b)
    x = cos(phi_a) * sin(phi_b) - sin(phi_a) * cos(phi_b) * cos(delta_lambda)
    return (degrees(atan2(y, x)) + 360) % 360


def circular_angle_difference_degrees(angle_a: float, angle_b: float) -> float:
    return abs((angle_a - angle_b + 180) % 360 - 180)


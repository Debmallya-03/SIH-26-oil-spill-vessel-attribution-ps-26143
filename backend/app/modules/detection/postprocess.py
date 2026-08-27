from dataclasses import dataclass

import numpy as np

from app.schemas.detection import ImageCoordinate, PolygonGeometry


@dataclass(frozen=True)
class SpillGeometry:
    spill_detected: bool
    area_pixels: float
    perimeter_pixels: float
    centroid: ImageCoordinate | None
    polygon: PolygonGeometry


def extract_spill_geometry(mask: np.ndarray, threshold: float = 0.5, min_area_pixels: float = 10.0) -> SpillGeometry:
    try:
        import cv2
    except ImportError:
        return _extract_spill_geometry_numpy(mask, threshold=threshold, min_area_pixels=min_area_pixels)

    if mask.ndim == 3:
        mask = mask.squeeze()

    binary_mask = (mask >= threshold).astype(np.uint8) * 255
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_contours = [contour for contour in contours if cv2.contourArea(contour) >= min_area_pixels]

    if not valid_contours:
        return SpillGeometry(
            spill_detected=False,
            area_pixels=0.0,
            perimeter_pixels=0.0,
            centroid=None,
            polygon=PolygonGeometry(coordinates=[]),
        )

    contour = max(valid_contours, key=cv2.contourArea)
    area_pixels = float(cv2.contourArea(contour))
    perimeter_pixels = float(cv2.arcLength(contour, closed=True))
    moments = cv2.moments(contour)
    centroid = None
    if moments["m00"] != 0:
        centroid = ImageCoordinate(x=float(moments["m10"] / moments["m00"]), y=float(moments["m01"] / moments["m00"]))

    epsilon = 0.01 * perimeter_pixels
    polygon_points = cv2.approxPolyDP(contour, epsilon, closed=True).reshape(-1, 2)
    coordinates = [[[float(x), float(y)] for x, y in polygon_points]]
    if coordinates[0] and coordinates[0][0] != coordinates[0][-1]:
        coordinates[0].append(coordinates[0][0])

    return SpillGeometry(
        spill_detected=True,
        area_pixels=area_pixels,
        perimeter_pixels=perimeter_pixels,
        centroid=centroid,
        polygon=PolygonGeometry(coordinates=coordinates),
    )


def _extract_spill_geometry_numpy(mask: np.ndarray, threshold: float, min_area_pixels: float) -> SpillGeometry:
    if mask.ndim == 3:
        mask = mask.squeeze()

    binary_mask = mask >= threshold
    height, width = binary_mask.shape
    visited = np.zeros_like(binary_mask, dtype=bool)
    components: list[list[tuple[int, int]]] = []

    for y in range(height):
        for x in range(width):
            if not binary_mask[y, x] or visited[y, x]:
                continue

            stack = [(y, x)]
            visited[y, x] = True
            component: list[tuple[int, int]] = []
            while stack:
                cy, cx = stack.pop()
                component.append((cy, cx))
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < height and 0 <= nx < width and binary_mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
            components.append(component)

    valid_components = [component for component in components if len(component) >= min_area_pixels]
    if not valid_components:
        return SpillGeometry(
            spill_detected=False,
            area_pixels=0.0,
            perimeter_pixels=0.0,
            centroid=None,
            polygon=PolygonGeometry(coordinates=[]),
        )

    component = max(valid_components, key=len)
    ys = np.array([point[0] for point in component])
    xs = np.array([point[1] for point in component])
    area_pixels = float(len(component))
    perimeter_pixels = float(_component_perimeter(binary_mask, component))
    centroid = ImageCoordinate(x=float(xs.mean()), y=float(ys.mean()))
    min_x, max_x = float(xs.min()), float(xs.max())
    min_y, max_y = float(ys.min()), float(ys.max())
    polygon = PolygonGeometry(
        coordinates=[
            [
                [min_x, min_y],
                [max_x, min_y],
                [max_x, max_y],
                [min_x, max_y],
                [min_x, min_y],
            ]
        ]
    )
    return SpillGeometry(
        spill_detected=True,
        area_pixels=area_pixels,
        perimeter_pixels=perimeter_pixels,
        centroid=centroid,
        polygon=polygon,
    )


def _component_perimeter(binary_mask: np.ndarray, component: list[tuple[int, int]]) -> int:
    height, width = binary_mask.shape
    perimeter = 0
    for y, x in component:
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if ny < 0 or ny >= height or nx < 0 or nx >= width or not binary_mask[ny, nx]:
                perimeter += 1
    return perimeter

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.modules.detection.inference import predict_spill
from app.modules.detection.postprocess import extract_spill_geometry
from app.schemas.detection import DetectionRequest, DetectionResponse


def detect_oil_spill(request: DetectionRequest | None = None) -> DetectionResponse:
    if request is None or request.image_path is None:
        return DetectionResponse(
            status="model_not_ready",
            spill_detected=None,
            model="small-unet-baseline",
            message="Provide image_path and train/place a checkpoint before running detection.",
        )

    image_path = Path(request.image_path)
    try:
        prediction = predict_spill(image_path)
    except FileNotFoundError as exc:
        return DetectionResponse(
            status="image_not_found",
            spill_detected=None,
            model="small-unet-synthetic-dev",
            message=str(exc),
        )
    if prediction.status != "success" or prediction.mask is None:
        return DetectionResponse(
            status=prediction.status,
            spill_detected=None,
            confidence=prediction.confidence,
            model=prediction.model_name,
            message=prediction.message,
        )

    geometry = extract_spill_geometry(prediction.mask)
    return DetectionResponse(
        status="success",
        spill_detected=geometry.spill_detected,
        spill_id=f"spill-{uuid4().hex[:12]}",
        detected_at=datetime.now(UTC),
        area_pixels=geometry.area_pixels,
        perimeter_pixels=geometry.perimeter_pixels,
        centroid=geometry.centroid,
        polygon=geometry.polygon,
        confidence=prediction.confidence,
        model=prediction.model_name,
        model_dataset_type=prediction.dataset_type,
        image_size=prediction.image_size,
    )

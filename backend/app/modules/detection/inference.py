from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from app.core.config import settings
from app.modules.detection.model import build_model
from app.modules.detection.preprocess import preprocess_image, to_chw_tensor_array

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class PredictionResult:
    status: str
    mask: np.ndarray | None
    confidence: float | None
    model_name: str
    message: str | None = None
    dataset_type: str | None = None
    image_size: int | None = None


def resolve_checkpoint_path(checkpoint_path: str | Path | None = None) -> Path:
    raw_path = Path(checkpoint_path or settings.detection_model_path)
    if raw_path.is_absolute() or raw_path.exists():
        return raw_path

    repo_relative = REPO_ROOT / raw_path
    if repo_relative.exists():
        return repo_relative

    backend_relative = BACKEND_ROOT / raw_path
    if backend_relative.exists():
        return backend_relative

    return repo_relative


def checkpoint_model_name(checkpoint: Path, state: dict | None = None) -> str:
    if state and state.get("dataset_type") == "deep_sar_sos":
        return "small-unet-deep-sar-sos"
    if state and state.get("dataset_notice"):
        return "small-unet-synthetic-dev"
    lowered_name = checkpoint.name.lower()
    if "synthetic" in lowered_name and "dev" in lowered_name:
        return "small-unet-synthetic-dev"
    return "small-unet-baseline"


def predict_spill(
    image_path: str | Path,
    checkpoint_path: str | Path | None = None,
    image_size: int = 256,
    threshold: float = 0.5,
) -> PredictionResult:
    checkpoint = resolve_checkpoint_path(checkpoint_path)
    if not checkpoint.exists():
        return PredictionResult(
            status="model_not_ready",
            mask=None,
            confidence=None,
            model_name=checkpoint_model_name(checkpoint),
            message=f"Detection model checkpoint not found: {checkpoint}",
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    state = torch.load(checkpoint, map_location=device)
    model_name = checkpoint_model_name(checkpoint, state if isinstance(state, dict) else None)
    metadata = state if isinstance(state, dict) else {}
    architecture = metadata.get("architecture", "small_unet")
    input_channels = int(metadata.get("input_channels", 3))
    output_classes = int(metadata.get("output_classes", 1))
    checkpoint_image_size = int(metadata.get("image_size", image_size))
    model = build_model(architecture, in_channels=input_channels, out_channels=output_classes).to(device)
    model.load_state_dict(state["model_state_dict"] if "model_state_dict" in state else state)
    model.eval()

    image = preprocess_image(image_path, image_size=checkpoint_image_size, input_channels=input_channels)
    tensor = torch.from_numpy(to_chw_tensor_array(image)).unsqueeze(0).to(device)

    with torch.no_grad():
        logits = model(tensor)
        probabilities = torch.sigmoid(logits).squeeze().cpu().numpy()

    mask = (probabilities >= threshold).astype(np.float32)
    confidence = float(probabilities[mask > 0].mean()) if np.any(mask > 0) else float(probabilities.mean())
    return PredictionResult(
        status="success",
        mask=mask,
        confidence=confidence,
        model_name=model_name,
        dataset_type=metadata.get("dataset_type"),
        image_size=checkpoint_image_size,
    )

from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = Path(__file__).resolve().parents[3]


def load_image(image_path: str | Path) -> np.ndarray:
    path = resolve_image_path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    image = Image.open(path).convert("RGB")
    return np.asarray(image)


def resolve_image_path(image_path: str | Path) -> Path:
    path = Path(image_path)
    candidates = [path] if path.is_absolute() else [path, BACKEND_ROOT / path, REPO_ROOT / path]
    for candidate in candidates:
        resolved = candidate.resolve()
        if _is_allowed_project_path(resolved) and resolved.exists():
            return resolved
    return candidates[-1].resolve()


def _is_allowed_project_path(path: Path) -> bool:
    allowed_roots = (REPO_ROOT.resolve(), BACKEND_ROOT.resolve())
    return any(path == root or root in path.parents for root in allowed_roots)


def resize_image(image: np.ndarray, image_size: int) -> np.ndarray:
    pil_image = Image.fromarray(image)
    resized = pil_image.resize((image_size, image_size), Image.Resampling.BILINEAR)
    return np.asarray(resized)


def resize_mask(mask: np.ndarray, image_size: int) -> np.ndarray:
    pil_mask = Image.fromarray(mask)
    resized = pil_mask.resize((image_size, image_size), Image.Resampling.NEAREST)
    return np.asarray(resized)


def normalize_image(image: np.ndarray) -> np.ndarray:
    image_float = image.astype(np.float32) / 255.0
    return image_float


def median_speckle_filter(image: np.ndarray, kernel_size: int = 3) -> np.ndarray:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("opencv-python is required for speckle filtering") from exc

    return cv2.medianBlur(image, kernel_size)


def preprocess_image(
    image_path: str | Path,
    image_size: int = 256,
    apply_speckle_filter: bool = False,
) -> np.ndarray:
    image = load_image(image_path)
    if apply_speckle_filter:
        image = median_speckle_filter(image)
    image = resize_image(image, image_size)
    return normalize_image(image)


def to_chw_tensor_array(image: np.ndarray) -> np.ndarray:
    return np.transpose(image, (2, 0, 1)).astype(np.float32)

from pathlib import Path

import numpy as np
from PIL import Image


def load_image(image_path: str | Path) -> np.ndarray:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    image = Image.open(path).convert("RGB")
    return np.asarray(image)


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

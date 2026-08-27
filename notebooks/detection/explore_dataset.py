from pathlib import Path
import sys

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "backend"))

from app.modules.detection.dataset import find_segmentation_pairs, inspect_image, list_image_files, list_mask_files, summarize_dataset


def describe_array(path: Path) -> None:
    image = Image.open(path)
    array = np.asarray(image)
    unique_values = np.unique(array)
    print(f"  path: {path}")
    print(f"  mode: {image.mode}")
    print(f"  size: {image.size}")
    print(f"  shape: {array.shape}")
    print(f"  dtype: {array.dtype}")
    print(f"  min/max: {array.min()} / {array.max()}")
    print(f"  unique values shown: {unique_values[:20].tolist()}")


def main() -> None:
    dataset_root = REPO_ROOT / "data" / "kaggle"
    summary = summarize_dataset(dataset_root)
    print("Dataset summary")
    print(f"  root: {summary.root}")
    print(f"  image_count: {summary.image_count}")
    print(f"  mask_count: {summary.mask_count}")
    print(f"  class_folders: {summary.class_folders}")
    print(f"  image_extensions: {summary.image_extensions}")
    print(f"  mask_extensions: {summary.mask_extensions}")
    print(f"  train_validation_exists: {summary.train_validation_exists}")
    print(f"  segmentation_ready: {summary.segmentation_ready}")

    images = list_image_files(dataset_root)
    masks = list_mask_files(dataset_root)
    pairs = find_segmentation_pairs(dataset_root)

    print("\nSample image files")
    for path in images[:10]:
        print(f"  {path}")

    print("\nSample image inspection")
    for path in images[:3]:
        describe_array(path)

    if masks:
        print("\nSample mask inspection")
        for path in masks[:3]:
            describe_array(path)
    else:
        print("\nNo segmentation masks or label rasters were found.")

    print("\nImage-to-mask pairing")
    if pairs:
        for image_path, mask_path in pairs[:10]:
            print(f"  {image_path.name} -> {mask_path.name}")
    else:
        print("  No image/mask pairs found. Current dataset supports binary chip classification, not supervised semantic segmentation.")


if __name__ == "__main__":
    main()

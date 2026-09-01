import argparse
from pathlib import Path
import sys

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "backend"))

from app.modules.detection.dataset import find_segmentation_pairs


def make_overlay(image: Image.Image, mask: Image.Image, alpha: float = 0.45) -> Image.Image:
    rgb = image.convert("RGB")
    mask_array = np.asarray(mask.convert("L"))
    red = Image.new("RGB", rgb.size, (255, 0, 0))
    overlay_mask = Image.fromarray((mask_array >= 128).astype(np.uint8) * int(255 * alpha), mode="L")
    return Image.composite(red, rgb, overlay_mask)


def build_contact_sheet(dataset_root: Path, output_path: Path, sample_count: int) -> None:
    pairs = find_segmentation_pairs(dataset_root)[:sample_count]
    if not pairs:
        raise ValueError(f"No image/mask pairs found under {dataset_root}")

    rows = []
    for image_path, mask_path in pairs:
        with Image.open(image_path) as image, Image.open(mask_path) as mask:
            image_rgb = image.convert("RGB")
            mask_rgb = mask.convert("RGB")
            overlay = make_overlay(image_rgb, mask)
            row = Image.new("RGB", (image_rgb.width * 3, image_rgb.height), (255, 255, 255))
            row.paste(image_rgb, (0, 0))
            row.paste(mask_rgb, (image_rgb.width, 0))
            row.paste(overlay, (image_rgb.width * 2, 0))
            rows.append(row)

    sheet = Image.new("RGB", (rows[0].width, sum(row.height for row in rows)), (255, 255, 255))
    y = 0
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    print(f"Saved inspection sheet: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create Deep-SAR SOS image/mask/overlay inspection sheet.")
    parser.add_argument("--dataset-root", type=Path, default=REPO_ROOT / "data" / "deep_sar_sos" / "extracted")
    parser.add_argument("--output-path", type=Path, default=REPO_ROOT / "artifacts" / "deep_sar_sos_overlay.png")
    parser.add_argument("--sample-count", type=int, default=6)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_contact_sheet(args.dataset_root, args.output_path, args.sample_count)

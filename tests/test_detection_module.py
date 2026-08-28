import sys
import unittest
from pathlib import Path
import shutil

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT / "backend"))

from app.modules.detection.dataset import SARSegmentationDataset, find_segmentation_pairs, summarize_dataset, validate_segmentation_dataset
from app.modules.detection.inference import predict_spill
from app.modules.detection.model import build_model
from app.modules.detection.postprocess import extract_spill_geometry
from app.modules.detection.preprocess import preprocess_image, resize_mask, resolve_image_path


class DetectionModuleTests(unittest.TestCase):
    def test_preprocess_image_normalizes_and_resizes(self) -> None:
        temp_dir = REPO_ROOT / ".test_tmp"
        try:
            temp_dir.mkdir(exist_ok=True)
            image_path = temp_dir / "sample.jpg"
            Image.fromarray(np.full((16, 12, 3), 128, dtype=np.uint8)).save(image_path)

            image = preprocess_image(image_path, image_size=8)
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

        self.assertEqual(image.shape, (8, 8, 3))
        self.assertEqual(image.dtype, np.float32)
        self.assertGreaterEqual(float(image.min()), 0.0)
        self.assertLessEqual(float(image.max()), 1.0)

    def test_resolve_image_path_supports_backend_and_repo_relative_paths(self) -> None:
        actual = REPO_ROOT / "data" / "synthetic_sar" / "images" / "sar_001.png"

        self.assertEqual(resolve_image_path("../data/synthetic_sar/images/sar_001.png"), actual)
        self.assertEqual(resolve_image_path("data/synthetic_sar/images/sar_001.png"), actual)

    def test_dataset_summary_reports_no_segmentation_masks(self) -> None:
        summary = summarize_dataset(REPO_ROOT / "data" / "kaggle")

        self.assertGreater(summary.image_count, 0)
        self.assertEqual(summary.mask_count, 0)
        self.assertFalse(summary.segmentation_ready)
        self.assertIn(".jpg", summary.image_extensions)

    def test_synthetic_pairing_and_strict_validation(self) -> None:
        root = REPO_ROOT / "data" / "synthetic_sar"
        pairs = find_segmentation_pairs(root)
        report = validate_segmentation_dataset(root)

        self.assertEqual(len(pairs), 7)
        self.assertEqual(report.image_count, 7)
        self.assertEqual(report.mask_count, 7)
        self.assertEqual(report.missing_masks, [])
        self.assertEqual(report.orphan_masks, [])
        self.assertEqual(report.empty_masks, [])
        self.assertEqual(len(report.dimension_mismatches), 7)
        self.assertFalse(report.is_trainable)

    def test_synthetic_dev_accepts_and_aligns_mismatched_dimensions(self) -> None:
        report = validate_segmentation_dataset(
            REPO_ROOT / "data" / "synthetic_sar",
            allow_synthetic_alignment=True,
        )

        self.assertTrue(report.is_trainable)
        self.assertEqual(len(report.valid_pairs), 7)
        self.assertEqual(len(report.corrected_pairs), 7)
        self.assertEqual(report.dimension_mismatches, [])
        self.assertTrue(all(pair.alignment_applied for pair in report.valid_pairs))
        self.assertTrue(all(pair.aligned_mask_size == pair.image_size for pair in report.valid_pairs))
        self.assertTrue(all((pair.aligned_foreground_pixels or 0) > 0 for pair in report.valid_pairs))

    def test_mask_resize_uses_binary_nearest_neighbour_values(self) -> None:
        mask = np.array([[0, 255], [255, 0]], dtype=np.uint8)
        resized = resize_mask(mask, image_size=8)
        binary = (resized > 0).astype(np.uint8)

        self.assertEqual(set(np.unique(binary).tolist()), {0, 1})

    def test_training_dataset_rejects_mismatched_dimensions(self) -> None:
        pairs = find_segmentation_pairs(REPO_ROOT / "data" / "synthetic_sar")
        dataset = SARSegmentationDataset(pairs, image_size=64, strict_dimensions=True)

        with self.assertRaises(ValueError):
            dataset[0]

    def test_training_dataset_initializes_with_synthetic_alignment(self) -> None:
        report = validate_segmentation_dataset(
            REPO_ROOT / "data" / "synthetic_sar",
            allow_synthetic_alignment=True,
        )
        dataset = SARSegmentationDataset(
            report.valid_pairs,
            image_size=64,
            strict_dimensions=False,
            align_mask_to_image=True,
        )

        image_tensor, mask_tensor = dataset[0]

        self.assertEqual(tuple(image_tensor.shape), (3, 64, 64))
        self.assertEqual(tuple(mask_tensor.shape), (1, 64, 64))
        self.assertTrue(set(np.unique(mask_tensor.numpy()).tolist()).issubset({0.0, 1.0}))

    def test_predict_spill_loads_checkpoint(self) -> None:
        import torch

        temp_dir = REPO_ROOT / ".test_tmp"
        try:
            temp_dir.mkdir(exist_ok=True)
            image_path = temp_dir / "sample.png"
            checkpoint_path = temp_dir / "unet-synthetic-dev.pth"
            Image.fromarray(np.full((32, 32, 3), 128, dtype=np.uint8)).save(image_path)
            model = build_model("small_unet")
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "dataset_notice": "synthetic development data only",
                },
                checkpoint_path,
            )

            result = predict_spill(image_path, checkpoint_path=checkpoint_path, image_size=32)
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.model_name, "small-unet-synthetic-dev")
        self.assertEqual(result.mask.shape, (32, 32))
        self.assertIsNotNone(result.confidence)

    def test_extract_spill_geometry_from_synthetic_mask(self) -> None:
        mask = np.zeros((32, 32), dtype=np.float32)
        mask[8:24, 10:26] = 1.0

        geometry = extract_spill_geometry(mask, min_area_pixels=10)

        self.assertTrue(geometry.spill_detected)
        self.assertGreater(geometry.area_pixels, 0)
        self.assertGreater(geometry.perimeter_pixels, 0)
        self.assertIsNotNone(geometry.centroid)
        self.assertEqual(geometry.polygon.type, "Polygon")
        self.assertGreaterEqual(len(geometry.polygon.coordinates[0]), 4)


if __name__ == "__main__":
    unittest.main()

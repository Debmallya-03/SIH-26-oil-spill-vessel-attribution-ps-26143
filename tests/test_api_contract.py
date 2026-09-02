import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT / "backend"))

from app.main import app
from app.core.config import settings
from app.modules.detection.model import build_model


class ApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_day_1_endpoints_still_exist(self) -> None:
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.post("/drift", json={
            "latitude": 18.5204,
            "longitude": 72.89,
            "timestamp": "2026-08-26T12:00:00Z",
        }).status_code, 200)
        self.assertEqual(self.client.post("/score", json={
            "latitude": 18.41,
            "longitude": 72.74,
            "origin_time_window": {
                "start": "2026-08-26T06:00:00Z",
                "end": "2026-08-26T08:00:00Z",
            },
        }).status_code, 200)
        self.assertEqual(self.client.post("/pipeline").status_code, 200)

    def test_detect_reports_model_not_ready_without_checkpoint(self) -> None:
        previous_model_path = settings.detection_model_path
        try:
            settings.detection_model_path = "models/does-not-exist.pth"
            response = self.client.post("/detect", json={"image_path": "data/kaggle/data/Class_1/class_1_00001.jpg"})
        finally:
            settings.detection_model_path = previous_model_path

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "model_not_ready")
        self.assertIn("checkpoint not found", payload["message"])

    def test_detect_integration_with_temporary_checkpoint(self) -> None:
        import torch

        temp_dir = REPO_ROOT / ".test_tmp"
        checkpoint_path = temp_dir / "unet-synthetic-dev.pth"
        previous_model_path = settings.detection_model_path
        try:
            temp_dir.mkdir(exist_ok=True)
            model = build_model("small_unet")
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "dataset_notice": "synthetic development data only",
                },
                checkpoint_path,
            )
            settings.detection_model_path = str(checkpoint_path)

            response = self.client.post("/detect", json={
                "image_path": "data/synthetic_sar/images/sar_001.png",
            })
        finally:
            settings.detection_model_path = previous_model_path
            if temp_dir.exists():
                import shutil

                shutil.rmtree(temp_dir)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["model"], "small-unet-synthetic-dev")
        self.assertIn("spill_detected", payload)
        self.assertIn("area_pixels", payload)
        self.assertIn("perimeter_pixels", payload)
        self.assertIn("polygon", payload)


if __name__ == "__main__":
    unittest.main()

# Module A: SAR Oil Spill Detection

## Scope

Module A is the Day 2 backend foundation for SAR oil-spill detection. It prepares the path from image input to binary mask post-processing and structured detection output. It does not implement drift modeling, AIS processing, legal attribution, frontend visualization, OpenDrift, or live satellite ingestion.

## Dataset Discovered

Expected prompt path `data/sar/` is not present in this workspace.

The available dataset is:

```text
data/kaggle/
├── data/
│   ├── Class_0/
│   ├── Class_1/
│   └── sample/
└── metadata/
    ├── dataset_metadata.xml
    ├── dataset_readme.md
    └── license.html
```

`dataset_metadata.xml` identifies it as the CSIRO Sentinel-1 SAR image dataset of oil and non-oil features for machine learning. It contains grayscale Sentinel-1 SAR image chips saved as JPEG files. In this local copy, images open as RGB JPEGs with 400 x 400 pixels.

Observed folders:

- `data/kaggle/data/Class_0`: non-oil chips
- `data/kaggle/data/Class_1`: oil chips
- `data/kaggle/data/sample/Class_0` and `sample/Class_1`: small sample copy

Observed labels:

- `Class_0`: binary class label 0, not oil
- `Class_1`: binary class label 1, oil

No segmentation mask, label raster, annotation JSON, train folder, validation folder, or image-to-mask pairs were found.

## Segmentation Mask Status

Semantic segmentation masks do not currently exist in the workspace. This dataset supports binary image-chip classification, not supervised pixel-level oil-spill segmentation.

Because of that, the code does not train a supervised U-Net on this dataset and does not fabricate masks from class labels.

## Preprocessing

Implemented in:

```text
backend/app/modules/detection/preprocess.py
```

Supported operations:

- Load JPEG/PNG/TIFF-style image files through Pillow.
- Convert to RGB.
- Resize to configurable square model input size.
- Normalize pixel values to `[0, 1]`.
- Convert HWC arrays to CHW tensor layout.
- Optionally apply median filtering for simple speckle reduction when OpenCV is available.

The current dataset consists of processed JPEG chips, so no Sentinel-1 GRD calibration or geospatial raster processing is claimed.

## Data Loading

Implemented in:

```text
backend/app/modules/detection/dataset.py
```

The module can:

- Summarize dataset folders and image extensions.
- Detect whether segmentation masks are present.
- Find image/mask pairs using conservative filename matching.
- Create deterministic train/validation splits when pairs exist.
- Provide a PyTorch segmentation dataset only when image/mask pairs are available.

Current Kaggle status: no image/mask pairs are available. Synthetic development pairs are handled separately and are not mixed with Kaggle classification data.

## Model Architecture

Implemented in:

```text
backend/app/modules/detection/model.py
```

The baseline model builder supports:

- `small_unet`: a compact PyTorch U-Net suitable for hackathon experiments.
- `smp_unet_resnet34`: optional future path if `segmentation-models-pytorch` is installed.

No trained checkpoint is included in Git.

## Training

Training script:

```text
backend/scripts/train_detection.py
```

Example command:

```bash
cd backend
python scripts\train_detection.py --dataset-root ..\data\synthetic_sar --dataset-type synthetic_dev --epochs 20 --batch-size 2 --learning-rate 0.0001 --image-size 128 --output-path models\unet-synthetic-dev.pth
```

With the current Kaggle classification-only dataset, the script prints a clear message and skips training. With `dataset_type=segmentation`, mismatched source image/mask dimensions are rejected. With `dataset_type=synthetic_dev`, masks may be aligned to image dimensions using nearest-neighbour interpolation for smoke testing only.

- `BCEWithLogitsLoss`
- validation loss
- Dice score
- IoU score
- CUDA when available, CPU otherwise
- best-checkpoint saving

All metrics emitted from synthetic data are labelled `SYNTHETIC DEVELOPMENT METRICS`.

## Checkpoint Location

Local checkpoints should be placed under:

```text
backend/models/
```

The repository ignores:

```text
*.pth
*.pt
*.ckpt
backend/models/*
```

Large model artifacts should not be committed.

## Synthetic Development Dataset

A synthetic development-only dataset was added under:

```text
data/synthetic_sar/
├── images/
└── masks/
```

This data is synthetic and is intended only for pipeline validation, training smoke tests, checkpoint generation, API integration testing, and mask-to-polygon testing. It is not real Sentinel-1 scientific training data.

Expected pairing convention:

```text
images/sar_001.png
masks/sar_001_mask.png
```

Current inspection found 7 image files and 7 mask files with expected filenames. Each mask contains foreground pixels after grayscale thresholding. In `synthetic_dev` mode only, the synthetic development masks are aligned to their corresponding image dimensions using nearest-neighbour interpolation solely for software pipeline smoke testing. This alignment policy must not be applied blindly to real scientific datasets.

The development checkpoint path is:

```text
backend/models/unet-synthetic-dev.pth
```

The filename intentionally includes `synthetic` and `dev` so it is not mistaken for a future real model. It must eventually be replaced by a model trained and validated on real Sentinel-1 imagery with proper segmentation labels.

## Inference

Implemented in:

```text
backend/app/modules/detection/inference.py
```

Primary interface:

```python
predict_spill(image_path)
```

If `DETECTION_MODEL_PATH` does not exist, inference returns `model_not_ready` instead of crashing at startup or returning fake predictions.

## Post-Processing

Implemented in:

```text
backend/app/modules/detection/postprocess.py
```

Given a binary or probabilistic mask, it computes:

- valid contours
- largest spill region
- polygon in image coordinates
- area in pixels
- perimeter in pixels
- centroid in image coordinates

No latitude, longitude, or square-kilometer area is fabricated. Geospatial conversion is pending real georeferenced Sentinel-1 input.

## API Integration

Endpoint:

```http
POST /detect
```

Example request:

```json
{
  "image_path": "data/kaggle/data/Class_1/class_1_00001.jpg"
}
```

If no checkpoint exists, response status is:

```json
{
  "status": "model_not_ready",
  "message": "Detection model checkpoint not found: ..."
}
```

Successful future detections return image-space geometry with `area_pixels`, `perimeter_pixels`, `centroid`, and `polygon`.

## Known Limitations

This is a hackathon baseline. It does not claim perfect oil-spill detection, automatic legal attribution, or robust discrimination between true spills and natural look-alikes. Distinguishing oil slicks from look-alikes remains a known research limitation and requires better labels, validation data, and domain review.

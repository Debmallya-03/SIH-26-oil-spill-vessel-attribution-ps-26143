# Module A: Refined Deep-SAR Oil Spill SOS Dataset

## Scope

This document describes local integration of the Refined Deep-SAR Oil Spill (SOS) segmentation dataset into Module A.

The dataset is real SAR oil-spill imagery/segmentation data according to the downloaded dataset source, but local model metrics are dataset validation metrics only. They do not prove operational real-world oil-spill detection accuracy.

## Local Files

Archives are expected at:

```text
data/deep_sar_sos/archives/images.zip
data/deep_sar_sos/archives/masks.zip
```

Extracted data is expected at:

```text
data/deep_sar_sos/extracted/
|-- images/
|   |-- train/
|   `-- val/
`-- masks/
    |-- train/
    `-- val/
```

`data/deep_sar_sos/` is ignored by Git because it contains large external data.

## Archive Inspection

The downloaded archives contain author-provided `train` and `val` splits. No `test` split was found locally.

Legitimate PNG counts after ignoring `__MACOSX`, Apple resource-fork files, and `.DS_Store`:

```text
images: 8070
masks: 8070
train images/masks: 6455
val images/masks: 1615
```

## Image And Mask Format

Observed image format:

```text
size: 256 x 256
mode: RGB
dtype: uint8
range: 0..255
```

Observed mask format:

```text
size: 256 x 256
mode: RGB or L
dtype: uint8
```

Masks are paired by matching relative path and filename:

```text
images/train/palsar_0.png -> masks/train/palsar_0.png
images/val/palsar_0.png   -> masks/val/palsar_0.png
```

## Mask Classes

A full mask scan found pixel values from `0` through `255` after grayscale conversion.

Most pixels are exactly:

```text
0: background-dominant
255: oil-spill-mask-dominant
```

Intermediate values are a small minority and appear consistent with antialiasing or soft mask edges. The local loader therefore uses an explicit binary threshold for training:

```text
mask >= 128 -> oil_spill_candidate
mask < 128  -> background
```

The raw audit values are preserved in reporting. This threshold is an implementation choice for supervised binary segmentation on this refined dataset; it should be reviewed against the original dataset documentation before scientific claims.

Empty masks exist and are treated as valid background/no-spill segmentation samples for `deep_sar_sos`.

## Loader Behavior

`dataset_type=deep_sar_sos`:

- uses the author-provided train/val split
- does not derive a random split
- pairs images and masks deterministically by relative path
- rejects missing masks and mismatched dimensions
- allows empty masks as valid background samples
- resizes images with bilinear interpolation
- resizes masks with nearest-neighbour interpolation
- supports RGB input with `input_channels=3`

`synthetic_dev` remains separate and keeps its controlled mask-alignment policy for development-only mismatched synthetic pairs.

## Training

Tiny smoke-training command:

```powershell
cd backend
python scripts\train_detection.py --dataset-root ..\data\deep_sar_sos\extracted --dataset-type deep_sar_sos --epochs 1 --batch-size 2 --image-size 128 --learning-rate 0.0001 --output-path models\unet-deep-sar-sos-smoke.pth --max-train-samples 8 --max-val-samples 4
```

Recommended full-training command:

```powershell
cd backend
python scripts\train_detection.py --dataset-root ..\data\deep_sar_sos\extracted --dataset-type deep_sar_sos --epochs 20 --batch-size 4 --image-size 256 --learning-rate 0.0001 --output-path models\unet-deep-sar-sos.pth
```

The full checkpoint copied from Colab is now the preferred local production/demo checkpoint:

```text
backend/models/unet-deep-sar-sos.pth
```

Observed checkpoint metadata:

```text
architecture: small_unet
input_channels: 3
output_classes: 1
image_size: 256
dataset_type: deep_sar_sos
mask_threshold: 128
epoch: 17
val_loss: 0.6857113065105853
val_dice: 0.8047504318822728
val_iou: 0.6785275325326636
val_precision: 0.7755009290015343
val_recall: 0.8497777191719206
val_f1: 0.8047505510915623
```

Training uses:

- `small_unet`
- RGB input by default
- `BCEWithLogitsLoss + Dice loss`
- Dice
- IoU/Jaccard
- precision
- recall
- F1

Checkpoint metadata includes architecture, input channels, output classes, image size, dataset type, class mapping, mask threshold, normalization, epoch, and validation metrics.

## Inference

Set:

```env
DETECTION_MODEL_PATH=models/unet-deep-sar-sos.pth
```

or pass the checkpoint path directly in tests/scripts.

The checkpoint metadata controls model input channels and image size. The API still returns pixel/image-space statistics only:

- predicted mask summary
- pixel area
- pixel perimeter
- image-space centroid
- image-space polygon

If PNGs lack georeferencing, Module A must not fabricate latitude/longitude or square-kilometer area.

## Limitations

- No local `test` split was found.
- Intermediate mask values need confirmation from original dataset documentation.
- One tiny smoke checkpoint validates plumbing only.
- Dataset validation metrics are not operational real-world accuracy.
- Geospatial conversion still requires georeferenced source imagery and metadata.

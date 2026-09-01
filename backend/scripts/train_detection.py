import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "backend"))

from app.modules.detection.dataset import (
    DatasetType,
    SegmentationPair,
    SARSegmentationDataset,
    deterministic_split,
    infer_dataset_type,
    summarize_dataset,
    validate_segmentation_dataset,
)
from app.modules.detection.model import build_model


def dice_score_from_logits(logits, targets, threshold: float = 0.5, epsilon: float = 1e-6) -> float:
    import torch

    predictions = (torch.sigmoid(logits) >= threshold).float()
    intersection = (predictions * targets).sum()
    union = predictions.sum() + targets.sum()
    return float(((2 * intersection + epsilon) / (union + epsilon)).detach().cpu())


def iou_score_from_logits(logits, targets, threshold: float = 0.5, epsilon: float = 1e-6) -> float:
    import torch

    predictions = (torch.sigmoid(logits) >= threshold).float()
    intersection = (predictions * targets).sum()
    union = predictions.sum() + targets.sum() - intersection
    return float(((intersection + epsilon) / (union + epsilon)).detach().cpu())


def dice_loss_from_logits(logits, targets, epsilon: float = 1e-6):
    import torch

    probabilities = torch.sigmoid(logits)
    intersection = (probabilities * targets).sum(dim=(1, 2, 3))
    union = probabilities.sum(dim=(1, 2, 3)) + targets.sum(dim=(1, 2, 3))
    dice = (2 * intersection + epsilon) / (union + epsilon)
    return 1 - dice.mean()


def precision_recall_f1_from_logits(logits, targets, threshold: float = 0.5, epsilon: float = 1e-6) -> tuple[float, float, float]:
    import torch

    predictions = (torch.sigmoid(logits) >= threshold).float()
    true_positive = (predictions * targets).sum()
    false_positive = (predictions * (1 - targets)).sum()
    false_negative = ((1 - predictions) * targets).sum()
    precision = (true_positive + epsilon) / (true_positive + false_positive + epsilon)
    recall = (true_positive + epsilon) / (true_positive + false_negative + epsilon)
    f1 = (2 * precision * recall + epsilon) / (precision + recall + epsilon)
    return float(precision.detach().cpu()), float(recall.detach().cpu()), float(f1.detach().cpu())


def _display_paths(pairs, dataset_root: Path) -> list[str]:
    display = []
    for pair in pairs:
        image_path = pair.image_path
        mask_path = pair.mask_path
        try:
            image_text = str(image_path.relative_to(dataset_root))
            mask_text = str(mask_path.relative_to(dataset_root))
        except ValueError:
            image_text = image_path.name
            mask_text = mask_path.name
        display.append(f"{image_text} -> {mask_text}")
    return display


def _provided_split(pairs: list[SegmentationPair]) -> tuple[list[SegmentationPair], list[SegmentationPair], list[SegmentationPair]]:
    train_pairs = [pair for pair in pairs if "train" in pair.image_path.parts]
    val_pairs = [pair for pair in pairs if "val" in pair.image_path.parts or "validation" in pair.image_path.parts]
    test_pairs = [pair for pair in pairs if "test" in pair.image_path.parts]
    return train_pairs, val_pairs, test_pairs


def train(args: argparse.Namespace) -> None:
    summary = summarize_dataset(args.dataset_root)
    dataset_type = DatasetType(args.dataset_type)
    if dataset_type == DatasetType.AUTO:
        dataset_type = infer_dataset_type(args.dataset_root)

    if dataset_type == DatasetType.CLASSIFICATION:
        print("Dataset type is classification. Segmentation training skipped.")
        print(f"Dataset summary: {summary}")
        return

    synthetic_dev_mode = dataset_type == DatasetType.SYNTHETIC_DEV
    deep_sar_mode = dataset_type == DatasetType.DEEP_SAR_SOS
    validation_report = validate_segmentation_dataset(
        args.dataset_root,
        allow_synthetic_alignment=synthetic_dev_mode,
        allow_empty_masks=deep_sar_mode,
    )
    if validation_report.corrected_pairs:
        print("Synthetic development alignment report:")
        for item in validation_report.corrected_pairs:
            print(f"  {item}")
    print(f"Corrected pairs: {len(validation_report.corrected_pairs)}")
    if validation_report.missing_masks:
        print("Missing masks:")
        for item in validation_report.missing_masks:
            print(f"  {item}")
    if validation_report.orphan_masks:
        print("Orphan masks:")
        for item in validation_report.orphan_masks:
            print(f"  {item}")
    if validation_report.dimension_mismatches:
        print("Image/mask dimension mismatches:")
        for item in validation_report.dimension_mismatches:
            print(f"  {item}")
    if validation_report.empty_masks:
        print("Empty masks:")
        for item in validation_report.empty_masks:
            print(f"  {item}")
    rejected_count = (
        len(validation_report.missing_masks)
        + len(validation_report.orphan_masks)
        + len(validation_report.dimension_mismatches)
        + len(validation_report.empty_masks)
    )
    print(f"Rejected pairs: {rejected_count}")

    if not validation_report.is_trainable:
        print("Segmentation training rejected because the dataset failed strict validation.")
        print(f"Dataset summary: {summary}")
        return

    pairs = validation_report.valid_pairs
    if not pairs:
        print("No segmentation image/mask pairs found.")
        print(f"Dataset summary: {summary}")
        print("Training skipped because this dataset is not segmentation-ready.")
        return

    import torch
    from torch import nn
    from torch.utils.data import DataLoader

    test_pairs = []
    if deep_sar_mode:
        train_pairs, val_pairs, test_pairs = _provided_split(pairs)
        if not train_pairs or not val_pairs:
            print("Deep-SAR SOS training rejected because author-provided train/val splits were not found.")
            return
    else:
        train_pairs, val_pairs = deterministic_split(pairs, validation_fraction=args.validation_split, seed=args.seed)

    if args.max_train_samples:
        train_pairs = train_pairs[: args.max_train_samples]
    if args.max_val_samples:
        val_pairs = val_pairs[: args.max_val_samples]

    print(f"Dataset type: {dataset_type.value}")
    print(f"Input channels: {args.input_channels}")
    print(f"Mask threshold: {args.mask_threshold}")
    print(f"Train sample count: {len(train_pairs)}")
    print(f"Validation sample count: {len(val_pairs)}")
    print(f"Test sample count: {len(test_pairs)}")
    print("Train pairs:")
    for item in _display_paths(train_pairs, Path(args.dataset_root)):
        print(f"  {item}")
    print("Validation pairs:")
    for item in _display_paths(val_pairs, Path(args.dataset_root)):
        print(f"  {item}")

    train_dataset = SARSegmentationDataset(
        train_pairs,
        image_size=args.image_size,
        strict_dimensions=not synthetic_dev_mode,
        align_mask_to_image=synthetic_dev_mode,
        input_channels=args.input_channels,
        mask_threshold=args.mask_threshold,
    )
    val_dataset = SARSegmentationDataset(
        val_pairs,
        image_size=args.image_size,
        strict_dimensions=not synthetic_dev_mode,
        align_mask_to_image=synthetic_dev_mode,
        input_channels=args.input_channels,
        mask_threshold=args.mask_threshold,
    )

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(args.architecture, in_channels=args.input_channels, out_channels=1).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    positive_weight = torch.tensor([args.positive_class_weight], device=device) if args.positive_class_weight else None
    criterion = nn.BCEWithLogitsLoss(pos_weight=positive_weight)

    best_val_loss = float("inf")
    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        train_loss = 0.0
        for images, masks in train_loader:
            images = images.to(device)
            masks = masks.to(device)
            optimizer.zero_grad()
            logits = model(images)
            loss = criterion(logits, masks) + args.dice_loss_weight * dice_loss_from_logits(logits, masks)
            loss.backward()
            optimizer.step()
            train_loss += float(loss.detach().cpu())

        model.eval()
        val_loss = 0.0
        val_dice = 0.0
        val_iou = 0.0
        val_precision = 0.0
        val_recall = 0.0
        val_f1 = 0.0
        with torch.no_grad():
            for images, masks in val_loader:
                images = images.to(device)
                masks = masks.to(device)
                logits = model(images)
                loss = criterion(logits, masks) + args.dice_loss_weight * dice_loss_from_logits(logits, masks)
                val_loss += float(loss.detach().cpu())
                val_dice += dice_score_from_logits(logits, masks)
                val_iou += iou_score_from_logits(logits, masks)
                precision, recall, f1 = precision_recall_f1_from_logits(logits, masks)
                val_precision += precision
                val_recall += recall
                val_f1 += f1

        train_loss /= max(1, len(train_loader))
        val_loss /= max(1, len(val_loader))
        val_dice /= max(1, len(val_loader))
        val_iou /= max(1, len(val_loader))
        val_precision /= max(1, len(val_loader))
        val_recall /= max(1, len(val_loader))
        val_f1 /= max(1, len(val_loader))
        metric_label = "SYNTHETIC DEVELOPMENT METRICS" if synthetic_dev_mode else "DEEP-SAR SOS VALIDATION METRICS"
        print(
            f"{metric_label} "
            f"epoch={epoch} train_loss={train_loss:.4f} "
            f"val_loss={val_loss:.4f} val_dice={val_dice:.4f} val_iou={val_iou:.4f} "
            f"val_precision={val_precision:.4f} val_recall={val_recall:.4f} val_f1={val_f1:.4f}"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "architecture": args.architecture,
                    "input_channels": args.input_channels,
                    "output_classes": 1,
                    "image_size": args.image_size,
                    "mask_threshold": args.mask_threshold,
                    "val_loss": best_val_loss,
                    "val_dice": val_dice,
                    "val_iou": val_iou,
                    "val_precision": val_precision,
                    "val_recall": val_recall,
                    "val_f1": val_f1,
                    "dataset_type": dataset_type.value,
                    "class_mapping": {"0": "background", "1": "oil_spill_candidate"},
                    "normalization": "uint8 image values divided by 255.0",
                    "dataset_notice": (
                        "synthetic development data only; not scientific Sentinel-1 validation"
                        if synthetic_dev_mode
                        else "Refined Deep-SAR Oil Spill SOS dataset validation metrics; not operational real-world accuracy"
                    ),
                    "synthetic_dev_alignment": synthetic_dev_mode,
                    "epoch": epoch,
                },
                output_path,
            )
            print(f"saved best checkpoint: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train SAR oil-spill segmentation baseline.")
    parser.add_argument("--dataset-root", type=Path, default=REPO_ROOT / "data" / "kaggle")
    parser.add_argument("--dataset-type", choices=[item.value for item in DatasetType], default=DatasetType.AUTO.value)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--validation-split", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--architecture", type=str, default="small_unet")
    parser.add_argument("--input-channels", type=int, choices=[1, 3], default=3)
    parser.add_argument("--mask-threshold", type=int, default=128)
    parser.add_argument("--dice-loss-weight", type=float, default=1.0)
    parser.add_argument("--positive-class-weight", type=float, default=None)
    parser.add_argument("--max-train-samples", type=int, default=None)
    parser.add_argument("--max-val-samples", type=int, default=None)
    parser.add_argument("--output-path", type=Path, default=REPO_ROOT / "backend" / "models" / "unet-synthetic-dev.pth")
    return parser.parse_args()


if __name__ == "__main__":
    train(parse_args())

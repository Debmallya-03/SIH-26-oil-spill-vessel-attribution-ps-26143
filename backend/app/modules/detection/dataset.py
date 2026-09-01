from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import random
from typing import TypeVar

import numpy as np
from PIL import Image

from app.modules.detection.preprocess import normalize_image, resize_image, resize_mask, to_chw_tensor_array

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
MASK_DIR_NAMES = {"mask", "masks", "label", "labels", "annotation", "annotations"}
T = TypeVar("T")


class DatasetType(str, Enum):
    AUTO = "auto"
    CLASSIFICATION = "classification"
    SEGMENTATION = "segmentation"
    SYNTHETIC_DEV = "synthetic_dev"
    DEEP_SAR_SOS = "deep_sar_sos"


@dataclass(frozen=True)
class DatasetSummary:
    root: Path
    image_count: int
    mask_count: int
    class_folders: dict[str, int]
    image_extensions: dict[str, int]
    mask_extensions: dict[str, int]
    train_validation_exists: bool
    segmentation_ready: bool
    dataset_type: str


@dataclass(frozen=True)
class SegmentationPair:
    image_path: Path
    mask_path: Path
    image_size: tuple[int, int]
    mask_size: tuple[int, int]
    image_mode: str
    mask_mode: str
    mask_unique_values: list[int]
    foreground_pixels: int
    aligned_mask_size: tuple[int, int] | None = None
    aligned_foreground_pixels: int | None = None
    alignment_applied: bool = False


@dataclass(frozen=True)
class SegmentationValidationReport:
    root: Path
    image_count: int
    mask_count: int
    valid_pairs: list[SegmentationPair]
    missing_masks: list[str]
    orphan_masks: list[str]
    dimension_mismatches: list[str]
    empty_masks: list[str]
    corrected_pairs: list[str]

    @property
    def is_trainable(self) -> bool:
        return (
            bool(self.valid_pairs)
            and not self.missing_masks
            and not self.orphan_masks
            and not self.dimension_mismatches
            and not self.empty_masks
        )


def list_image_files(root: str | Path) -> list[Path]:
    root_path = Path(root)
    return sorted(
        path
        for path in root_path.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def list_segmentation_images(root: str | Path) -> list[Path]:
    root_path = Path(root)
    image_dir = root_path / "images"
    if image_dir.exists():
        return sorted(path for path in image_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)
    return [
        path
        for path in list_image_files(root_path)
        if not any(part.lower() in MASK_DIR_NAMES for part in path.parts)
    ]


def list_mask_files(root: str | Path) -> list[Path]:
    root_path = Path(root)
    return sorted(
        path
        for path in root_path.rglob("*")
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTENSIONS
        and any(part.lower() in MASK_DIR_NAMES for part in path.parts)
    )


def infer_dataset_type(root: str | Path) -> DatasetType:
    root_path = Path(root)
    if (
        (root_path / "images" / "train").is_dir()
        and (root_path / "images" / "val").is_dir()
        and (root_path / "masks" / "train").is_dir()
        and (root_path / "masks" / "val").is_dir()
    ):
        return DatasetType.DEEP_SAR_SOS
    if (root_path / "images").is_dir() and (root_path / "masks").is_dir():
        return DatasetType.SEGMENTATION
    if any(root_path.glob("data/Class_*")):
        return DatasetType.CLASSIFICATION
    return DatasetType.SEGMENTATION if list_mask_files(root_path) else DatasetType.CLASSIFICATION


def find_segmentation_pairs(root: str | Path) -> list[tuple[Path, Path]]:
    root_path = Path(root)
    masks = list_mask_files(root_path)
    if not masks:
        return []

    images = list_segmentation_images(root_path)
    if (root_path / "images").exists() and (root_path / "masks").exists():
        images_by_relative_stem = {
            path.relative_to(root_path / "images").with_suffix("").as_posix(): path
            for path in images
        }
        pairs = []
        for mask_path in masks:
            relative_stem = mask_path.relative_to(root_path / "masks").with_suffix("").as_posix()
            image_path = images_by_relative_stem.get(relative_stem)
            if image_path is not None:
                pairs.append((image_path, mask_path))
        if pairs:
            return sorted(pairs)

    images_by_stem = {path.stem: path for path in images}
    pairs: list[tuple[Path, Path]] = []
    for mask_path in masks:
        stem = mask_path.stem
        normalized_stems = [
            stem,
            stem.replace("_mask", ""),
            stem.replace("-mask", ""),
            stem.replace("_label", ""),
            stem.replace("-label", ""),
        ]
        image_path = next((images_by_stem.get(candidate) for candidate in normalized_stems if candidate in images_by_stem), None)
        if image_path is not None:
            pairs.append((image_path, mask_path))
    return sorted(pairs)


def align_mask_to_image_size(mask_array: np.ndarray, image_size: tuple[int, int]) -> np.ndarray:
    return np.asarray(Image.fromarray(mask_array).resize(image_size, Image.Resampling.NEAREST))


def validate_segmentation_dataset(
    root: str | Path,
    allow_synthetic_alignment: bool = False,
    allow_empty_masks: bool = False,
) -> SegmentationValidationReport:
    root_path = Path(root)
    images = list_segmentation_images(root_path)
    masks = list_mask_files(root_path)
    masks_by_name = {path.name: path for path in masks}
    images_by_name = {path.name: path for path in images}
    masks_by_relative_stem = {}
    images_by_relative_stem = {}
    if (root_path / "images").exists() and (root_path / "masks").exists():
        masks_by_relative_stem = {
            path.relative_to(root_path / "masks").with_suffix("").as_posix(): path
            for path in masks
        }
        images_by_relative_stem = {
            path.relative_to(root_path / "images").with_suffix("").as_posix(): path
            for path in images
        }

    valid_pairs: list[SegmentationPair] = []
    missing_masks: list[str] = []
    orphan_masks: list[str] = []
    dimension_mismatches: list[str] = []
    empty_masks: list[str] = []
    corrected_pairs: list[str] = []

    for image_path in images:
        expected_mask_name = f"{image_path.stem}_mask{image_path.suffix}"
        relative_stem = (
            image_path.relative_to(root_path / "images").with_suffix("").as_posix()
            if (root_path / "images") in image_path.parents
            else None
        )
        mask_path = masks_by_relative_stem.get(relative_stem) if relative_stem else None
        if mask_path is None:
            mask_path = masks_by_name.get(expected_mask_name) or masks_by_name.get(image_path.name)
        if mask_path is None:
            missing_masks.append(f"{image_path.name} -> {expected_mask_name}")
            continue

        with Image.open(image_path) as image, Image.open(mask_path) as raw_mask:
            mask = raw_mask.convert("L")
            mask_array = np.asarray(mask)
            binary_mask = (mask_array > 0).astype(np.uint8)
            foreground_pixels = int(binary_mask.sum())
            unique_values = [int(value) for value in np.unique(mask_array)]
            image_size = image.size
            mask_size = mask.size
            image_mode = image.mode
            mask_mode = mask.mode
            aligned_mask_size = None
            aligned_foreground_pixels = None
            alignment_applied = False

            if image_size != mask_size and allow_synthetic_alignment:
                aligned_mask = align_mask_to_image_size(binary_mask, image_size)
                aligned_mask_size = image_size
                aligned_foreground_pixels = int((aligned_mask > 0).sum())
                alignment_applied = True
                corrected_pairs.append(
                    f"{image_path.name}: image={image_size}, mask={mask_size}, "
                    f"aligned_mask={aligned_mask_size}, foreground_pixels={aligned_foreground_pixels}"
                )

        pair = SegmentationPair(
            image_path=image_path,
            mask_path=mask_path,
            image_size=image_size,
            mask_size=mask_size,
            image_mode=image_mode,
            mask_mode=mask_mode,
            mask_unique_values=unique_values,
            foreground_pixels=foreground_pixels,
            aligned_mask_size=aligned_mask_size,
            aligned_foreground_pixels=aligned_foreground_pixels,
            alignment_applied=alignment_applied,
        )

        effective_foreground_pixels = aligned_foreground_pixels if aligned_foreground_pixels is not None else foreground_pixels

        if image_size != mask_size and not allow_synthetic_alignment:
            dimension_mismatches.append(f"{image_path.name}: image={image_size}, mask={mask_size}")
        elif effective_foreground_pixels == 0 and not allow_empty_masks:
            empty_masks.append(mask_path.name)
        else:
            valid_pairs.append(pair)

    for mask_path in masks:
        expected_image_name = f"{mask_path.stem.removesuffix('_mask')}{mask_path.suffix}"
        relative_stem = (
            mask_path.relative_to(root_path / "masks").with_suffix("").as_posix()
            if (root_path / "masks") in mask_path.parents
            else None
        )
        if relative_stem and relative_stem in images_by_relative_stem:
            continue
        if expected_image_name not in images_by_name:
            orphan_masks.append(f"{mask_path.name} -> {expected_image_name}")

    return SegmentationValidationReport(
        root=root_path,
        image_count=len(images),
        mask_count=len(masks),
        valid_pairs=valid_pairs,
        missing_masks=missing_masks,
        orphan_masks=orphan_masks,
        dimension_mismatches=dimension_mismatches,
        empty_masks=empty_masks,
        corrected_pairs=corrected_pairs,
    )


def summarize_dataset(root: str | Path) -> DatasetSummary:
    root_path = Path(root)
    dataset_type = infer_dataset_type(root_path)
    images = (
        list_segmentation_images(root_path)
        if dataset_type in {DatasetType.SEGMENTATION, DatasetType.SYNTHETIC_DEV, DatasetType.DEEP_SAR_SOS}
        else list_image_files(root_path)
    )
    masks = list_mask_files(root_path)
    class_folders = {
        child.name: len([p for p in child.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS])
        for child in root_path.glob("data/Class_*")
        if child.is_dir()
    }
    image_extensions: dict[str, int] = {}
    for path in images:
        image_extensions[path.suffix.lower()] = image_extensions.get(path.suffix.lower(), 0) + 1

    mask_extensions: dict[str, int] = {}
    for path in masks:
        mask_extensions[path.suffix.lower()] = mask_extensions.get(path.suffix.lower(), 0) + 1

    split_names = {child.name.lower() for child in root_path.rglob("*") if child.is_dir()}
    train_validation_exists = {"train", "val"}.issubset(split_names) or {"train", "validation"}.issubset(split_names)

    segmentation_ready = (
        validate_segmentation_dataset(
            root_path,
            allow_synthetic_alignment=dataset_type == DatasetType.SYNTHETIC_DEV,
            allow_empty_masks=dataset_type == DatasetType.DEEP_SAR_SOS,
        ).is_trainable
        if dataset_type in {DatasetType.SEGMENTATION, DatasetType.SYNTHETIC_DEV, DatasetType.DEEP_SAR_SOS}
        else bool(find_segmentation_pairs(root_path))
    )

    return DatasetSummary(
        root=root_path,
        image_count=len(images),
        mask_count=len(masks),
        class_folders=class_folders,
        image_extensions=image_extensions,
        mask_extensions=mask_extensions,
        train_validation_exists=train_validation_exists,
        segmentation_ready=segmentation_ready,
        dataset_type=dataset_type.value,
    )


def inspect_image(path: str | Path) -> dict[str, object]:
    with Image.open(path) as image:
        array = np.asarray(image)
        return {
            "path": str(path),
            "mode": image.mode,
            "size": image.size,
            "shape": array.shape,
            "dtype": str(array.dtype),
            "min": int(array.min()),
            "max": int(array.max()),
        }


def deterministic_split(items: list[T], validation_fraction: float = 0.2, seed: int = 42) -> tuple[list[T], list[T]]:
    shuffled = list(items)
    random.Random(seed).shuffle(shuffled)
    validation_count = max(1, int(len(shuffled) * validation_fraction)) if len(shuffled) > 1 else 0
    return shuffled[validation_count:], shuffled[:validation_count]


class SARSegmentationDataset:
    def __init__(
        self,
        pairs: list[tuple[Path, Path]] | list[SegmentationPair],
        image_size: int = 256,
        strict_dimensions: bool = True,
        align_mask_to_image: bool = False,
        input_channels: int = 3,
        mask_threshold: int = 128,
    ) -> None:
        if not pairs:
            raise ValueError("No image/mask pairs were provided.")
        self.pairs = pairs
        self.image_size = image_size
        self.strict_dimensions = strict_dimensions
        self.align_mask_to_image = align_mask_to_image
        self.input_channels = input_channels
        self.mask_threshold = mask_threshold

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, index: int):
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("torch is required to use SARSegmentationDataset") from exc

        pair = self.pairs[index]
        if isinstance(pair, SegmentationPair):
            image_path, mask_path = pair.image_path, pair.mask_path
        else:
            image_path, mask_path = pair

        with Image.open(image_path) as raw_image, Image.open(mask_path) as raw_mask:
            image = raw_image.convert("L" if self.input_channels == 1 else "RGB")
            mask = raw_mask.convert("L")

            if self.strict_dimensions and image.size != mask.size:
                raise ValueError(f"Image/mask dimensions differ for {image_path.name}: image={image.size}, mask={mask.size}")

            image_array = resize_image(np.asarray(image), self.image_size)
            binary_mask = (np.asarray(mask) >= self.mask_threshold).astype(np.uint8)
            if self.align_mask_to_image and image.size != mask.size:
                binary_mask = align_mask_to_image_size(binary_mask, image.size)
            mask_array = resize_mask(binary_mask, self.image_size)
        mask_array = (mask_array > 0).astype(np.float32)

        image_tensor = torch.from_numpy(to_chw_tensor_array(normalize_image(image_array)))
        mask_tensor = torch.from_numpy(mask_array[None, ...])
        return image_tensor, mask_tensor

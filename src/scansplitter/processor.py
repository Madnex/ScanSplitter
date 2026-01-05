"""Main processing pipeline for scan splitting."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image

from .detector import crop_regions, detect_photos_u2net, detect_photos_v1, detect_photos_v2
from .pdf_handler import extract_images_from_pdf, is_pdf
from .rotator import auto_rotate


@dataclass
class ProcessedImage:
    """Result of processing a single detected photo."""

    image: Image.Image
    source_file: str
    source_page: int | None  # Page number if from PDF
    index: int  # Index within the source page/image
    rotation_applied: int  # Degrees rotated (0, 90, 180, or 270)


@dataclass
class ProcessingResult:
    """Result of processing one or more source files."""

    images: list[ProcessedImage]
    source_files: list[str]
    total_detected: int


def load_image(file_path: str | Path) -> Image.Image:
    """Load an image file and convert to RGB."""
    img = Image.open(file_path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def process_image(
    image: Image.Image,
    source_file: str = "unknown",
    source_page: int | None = None,
    auto_rotate_enabled: bool = True,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    # Phase 1 improvements
    enhance_contrast: bool = True,
    border_mode: Literal["minAreaRect", "convexHull"] = "minAreaRect",
    # Detection algorithms
    detection_mode: Literal["scansplitterv1", "scansplitterv2", "u2net"] = "scansplitterv2",
    u2net_lite: bool = True,
) -> list[ProcessedImage]:
    """
    Process a single image: detect photos and optionally auto-rotate.

    Args:
        image: PIL Image to process
        source_file: Name of the source file for reference
        source_page: Page number if from PDF
        auto_rotate_enabled: Whether to auto-rotate detected photos
        min_area_ratio: Minimum photo area as fraction of scan
        max_area_ratio: Maximum photo area as fraction of scan
        enhance_contrast: Apply CLAHE for better low-contrast detection
        border_mode: "minAreaRect" (tight) or "convexHull" (preserves irregular borders)
        detection_mode: "scansplitterv1" (legacy), "scansplitterv2" (default), or "u2net" (deep learning)
        u2net_lite: Use lightweight U2-Net model (faster) vs full (more accurate)

    Returns:
        List of ProcessedImage objects
    """
    # Detect photos based on selected mode (accept older aliases for compatibility)
    if detection_mode in ("u2net",):
        regions = detect_photos_u2net(
            image,
            min_area_ratio=min_area_ratio,
            max_area_ratio=max_area_ratio,
            lite=u2net_lite,
        )
    else:
        normalized_mode = detection_mode
        if normalized_mode in ("classic", "ScanSplitterv2", "v2"):  # type: ignore[comparison-overlap]
            normalized_mode = "scansplitterv2"  # type: ignore[assignment]
        if normalized_mode in ("ScanSplitterv1", "v1", "legacy"):  # type: ignore[comparison-overlap]
            normalized_mode = "scansplitterv1"  # type: ignore[assignment]

        if normalized_mode == "scansplitterv1":
            regions = detect_photos_v1(
                image,
                min_area_ratio=min_area_ratio,
                max_area_ratio=max_area_ratio,
            )
        else:
            regions = detect_photos_v2(
                image,
                min_area_ratio=min_area_ratio,
                max_area_ratio=max_area_ratio,
                enhance_contrast=enhance_contrast,
                border_mode=border_mode,
            )

    # If no regions detected, return the original image
    if not regions:
        cropped_images = [image]
    else:
        cropped_images = crop_regions(image, regions)

    results = []
    for idx, cropped in enumerate(cropped_images):
        rotation = 0

        if auto_rotate_enabled:
            cropped, rotation = auto_rotate(cropped)

        results.append(
            ProcessedImage(
                image=cropped,
                source_file=source_file,
                source_page=source_page,
                index=idx,
                rotation_applied=rotation,
            )
        )

    return results


def process_file(
    file_path: str | Path,
    auto_rotate_enabled: bool = True,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    pdf_dpi: int = 300,
    # Phase 1 improvements
    enhance_contrast: bool = True,
    border_mode: Literal["minAreaRect", "convexHull"] = "minAreaRect",
    # Detection algorithms
    detection_mode: Literal["scansplitterv1", "scansplitterv2", "u2net"] = "scansplitterv2",
    u2net_lite: bool = True,
) -> list[ProcessedImage]:
    """
    Process a single file (image or PDF).

    Args:
        file_path: Path to the file
        auto_rotate_enabled: Whether to auto-rotate detected photos
        min_area_ratio: Minimum photo area as fraction of scan
        max_area_ratio: Maximum photo area as fraction of scan
        pdf_dpi: DPI for PDF rendering
        enhance_contrast: Apply CLAHE for better low-contrast detection
        border_mode: "minAreaRect" (tight) or "convexHull" (preserves irregular borders)
        detection_mode: "scansplitterv1" (legacy), "scansplitterv2" (default), or "u2net" (deep learning)
        u2net_lite: Use lightweight U2-Net model (faster) vs full (more accurate)

    Returns:
        List of ProcessedImage objects
    """
    file_path = Path(file_path)
    file_name = file_path.name

    results = []

    if is_pdf(file_path):
        # Extract pages from PDF
        pages = extract_images_from_pdf(file_path, dpi=pdf_dpi)
        for page_num, page_image in enumerate(pages):
            page_results = process_image(
                page_image,
                source_file=file_name,
                source_page=page_num + 1,  # 1-indexed
                auto_rotate_enabled=auto_rotate_enabled,
                min_area_ratio=min_area_ratio,
                max_area_ratio=max_area_ratio,
                enhance_contrast=enhance_contrast,
                border_mode=border_mode,
                detection_mode=detection_mode,
                u2net_lite=u2net_lite,
            )
            results.extend(page_results)
    else:
        # Load as image
        image = load_image(file_path)
        results = process_image(
            image,
            source_file=file_name,
            auto_rotate_enabled=auto_rotate_enabled,
            min_area_ratio=min_area_ratio,
            max_area_ratio=max_area_ratio,
            enhance_contrast=enhance_contrast,
            border_mode=border_mode,
            detection_mode=detection_mode,
            u2net_lite=u2net_lite,
        )

    return results


def process_files(
    file_paths: list[str | Path],
    auto_rotate_enabled: bool = True,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    pdf_dpi: int = 300,
) -> ProcessingResult:
    """
    Process multiple files.

    Args:
        file_paths: List of file paths to process
        auto_rotate_enabled: Whether to auto-rotate detected photos
        min_area_ratio: Minimum photo area as fraction of scan
        max_area_ratio: Maximum photo area as fraction of scan
        pdf_dpi: DPI for PDF rendering

    Returns:
        ProcessingResult with all detected images
    """
    all_results = []
    source_files = []

    for file_path in file_paths:
        file_path = Path(file_path)
        source_files.append(str(file_path))

        results = process_file(
            file_path,
            auto_rotate_enabled=auto_rotate_enabled,
            min_area_ratio=min_area_ratio,
            max_area_ratio=max_area_ratio,
            pdf_dpi=pdf_dpi,
        )
        all_results.extend(results)

    return ProcessingResult(
        images=all_results,
        source_files=source_files,
        total_detected=len(all_results),
    )

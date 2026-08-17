"""Main processing pipeline for scan splitting."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image

from .album_detector import AlbumLayout, detect_album_pages
from .detector import (
    crop_regions,
    detect_photos_v3,
    detect_photos_v4,
)
from .edge_cleanup import EdgeCleanupMode, cleanup_photo_edges
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
    edge_cleanup_mode: EdgeCleanupMode = "tight",
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    # Detection algorithms
    detection_mode: Literal[
        "scansplitterv3",
        "scansplitterv4",
        "album-splitter",
    ] = "scansplitterv4",
    album_layout: AlbumLayout = "auto",
) -> list[ProcessedImage]:
    """
    Process a single image: detect photos and optionally auto-rotate.

    Args:
        image: PIL Image to process
        source_file: Name of the source file for reference
        source_page: Page number if from PDF
        auto_rotate_enabled: Whether to auto-rotate detected photos
        edge_cleanup_mode: Off, conservative scan-background trim, or tight margin trim
        min_area_ratio: Minimum photo area as fraction of scan
        max_area_ratio: Maximum photo area as fraction of scan
        detection_mode: "scansplitterv4" (default), "scansplitterv3", or "album-splitter"

    Returns:
        List of ProcessedImage objects
    """
    # Detect photos based on selected mode.
    if detection_mode == "album-splitter":
        regions = detect_album_pages(image, layout=album_layout)
    elif detection_mode == "scansplitterv4":
        regions = detect_photos_v4(
            image,
            min_area_ratio=min_area_ratio,
            max_area_ratio=max_area_ratio,
        )
    elif detection_mode == "scansplitterv3":
        regions = detect_photos_v3(
            image,
            min_area_ratio=min_area_ratio,
            max_area_ratio=max_area_ratio,
        )
    else:
        raise ValueError(f"Unsupported detection mode: {detection_mode}")

    # If no regions detected, return the original image
    if not regions:
        cropped_images = [image]
    else:
        cropped_images = crop_regions(image, regions)

    results = []
    for idx, cropped in enumerate(cropped_images):
        rotation = 0

        effective_cleanup = "off" if detection_mode == "album-splitter" else edge_cleanup_mode
        cropped, _ = cleanup_photo_edges(cropped, effective_cleanup)

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
    edge_cleanup_mode: EdgeCleanupMode = "tight",
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    pdf_dpi: int = 300,
    # Detection algorithms
    detection_mode: Literal[
        "scansplitterv3",
        "scansplitterv4",
        "album-splitter",
    ] = "scansplitterv4",
    album_layout: AlbumLayout = "auto",
) -> list[ProcessedImage]:
    """
    Process a single file (image or PDF).

    Args:
        file_path: Path to the file
        auto_rotate_enabled: Whether to auto-rotate detected photos
        edge_cleanup_mode: Off, conservative scan-background trim, or tight margin trim
        min_area_ratio: Minimum photo area as fraction of scan
        max_area_ratio: Maximum photo area as fraction of scan
        pdf_dpi: DPI for PDF rendering
        detection_mode: "scansplitterv4" (default), "scansplitterv3", or "album-splitter"

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
                edge_cleanup_mode=edge_cleanup_mode,
                min_area_ratio=min_area_ratio,
                max_area_ratio=max_area_ratio,
                detection_mode=detection_mode,
                album_layout=album_layout,
            )
            results.extend(page_results)
    else:
        # Load as image
        image = load_image(file_path)
        results = process_image(
            image,
            source_file=file_name,
            auto_rotate_enabled=auto_rotate_enabled,
            edge_cleanup_mode=edge_cleanup_mode,
            min_area_ratio=min_area_ratio,
            max_area_ratio=max_area_ratio,
            detection_mode=detection_mode,
            album_layout=album_layout,
        )

    return results


def process_files(
    file_paths: list[str | Path],
    auto_rotate_enabled: bool = True,
    edge_cleanup_mode: EdgeCleanupMode = "tight",
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    pdf_dpi: int = 300,
) -> ProcessingResult:
    """
    Process multiple files.

    Args:
        file_paths: List of file paths to process
        auto_rotate_enabled: Whether to auto-rotate detected photos
        edge_cleanup_mode: Off, conservative scan-background trim, or tight margin trim
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
            edge_cleanup_mode=edge_cleanup_mode,
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

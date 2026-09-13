"""Bounded decoding of retained originals, independent of display proxies."""
import io
from pathlib import Path

from PIL import Image, ImageCms

MAX_DECODED_PIXELS = 100_000_000


def validate_image(image: Image.Image) -> None:
    if image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_DECODED_PIXELS:
        raise ValueError(f"Image exceeds the {MAX_DECODED_PIXELS:,}-pixel processing limit")


def load_source(path: Path, page: int = 1, dpi: int = 300) -> Image.Image:
    if path.suffix.lower() == ".pdf":
        from .pdf_handler import extract_pdf_page
        return extract_pdf_page(path, page, dpi=dpi)
    with Image.open(path) as image:
        validate_image(image)
        profile = image.info.get("icc_profile")
        if profile:
            return ImageCms.profileToProfile(image, io.BytesIO(profile), ImageCms.createProfile("sRGB"), outputMode="RGB")
        return image.convert("RGB")

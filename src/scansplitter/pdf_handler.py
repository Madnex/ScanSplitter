"""PDF to image extraction using PyMuPDF."""

from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image


def get_pdf_page_count(pdf_path: str | Path) -> int:
    """Return the number of pages in a PDF without rendering any of them."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    try:
        return len(doc)
    finally:
        doc.close()


def extract_pdf_page(pdf_path: str | Path, page: int, dpi: int = 300) -> Image.Image:
    """
    Render a single PDF page (1-indexed) as a PIL Image.

    Much cheaper than extract_images_from_pdf when only one page is needed.

    Args:
        pdf_path: Path to the PDF file
        page: 1-indexed page number
        dpi: Resolution for rendering

    Raises:
        ValueError: If the page number is out of range.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    try:
        if page < 1 or page > len(doc):
            raise ValueError(f"Invalid page number: {page} (PDF has {len(doc)} pages)")
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        pix = doc[page - 1].get_pixmap(matrix=matrix)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    finally:
        doc.close()


def extract_images_from_pdf(pdf_path: str | Path, dpi: int = 300) -> list[Image.Image]:
    """
    Extract all pages from a PDF as PIL Images.

    Args:
        pdf_path: Path to the PDF file
        dpi: Resolution for rendering (default 300 for good quality)

    Returns:
        List of PIL Images, one per page
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    images = []
    doc = fitz.open(pdf_path)

    try:
        # Calculate zoom factor for desired DPI (default PDF is 72 DPI)
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)

        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=matrix)

            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
    finally:
        doc.close()

    return images


def is_pdf(file_path: str | Path) -> bool:
    """Check if a file is a PDF based on extension."""
    return Path(file_path).suffix.lower() == ".pdf"

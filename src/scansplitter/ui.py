"""Gradio web interface for ScanSplitter."""

import io
import tempfile
import zipfile
from pathlib import Path

import gradio as gr
from PIL import Image

from .processor import process_file


def process_uploads(
    files: list[str],
    auto_rotate: bool,
    min_area: float,
    max_area: float,
    output_format: str,
    quality: int,
) -> tuple[list[Image.Image], str | None]:
    """
    Process uploaded files and return detected images.

    Args:
        files: List of uploaded file paths
        auto_rotate: Whether to auto-rotate images
        min_area: Minimum area ratio (percentage)
        max_area: Maximum area ratio (percentage)
        output_format: Output format ("JPEG" or "PNG")
        quality: JPEG quality (1-100), ignored for PNG

    Returns:
        Tuple of (list of PIL Images, path to ZIP file or None)
    """
    if not files:
        return [], None

    all_images = []

    for file_path in files:
        results = process_file(
            file_path,
            auto_rotate_enabled=auto_rotate,
            min_area_ratio=min_area / 100,  # Convert from percentage
            max_area_ratio=max_area / 100,
        )
        for result in results:
            all_images.append(result.image)

    if not all_images:
        return [], None

    # Create ZIP file with results
    zip_path = create_zip(all_images, output_format, quality)

    return all_images, zip_path


def create_zip(
    images: list[Image.Image],
    output_format: str = "JPEG",
    quality: int = 85,
) -> str:
    """Create a ZIP file containing all images with compression.

    Args:
        images: List of PIL Images to save
        output_format: "JPEG" or "PNG"
        quality: JPEG quality (1-100), ignored for PNG
    """
    temp_dir = tempfile.mkdtemp()
    zip_path = Path(temp_dir) / "scansplitter_results.zip"

    ext = "jpg" if output_format == "JPEG" else "png"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, img in enumerate(images):
            img_bytes = io.BytesIO()

            if output_format == "JPEG":
                # Convert to RGB if necessary (JPEG doesn't support alpha)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(img_bytes, format="JPEG", quality=quality, optimize=True)
            else:
                img.save(img_bytes, format="PNG", optimize=True)

            img_bytes.seek(0)
            zf.writestr(f"photo_{idx + 1:03d}.{ext}", img_bytes.read())

    return str(zip_path)


def create_ui() -> gr.Blocks:
    """Create and return the Gradio interface."""
    with gr.Blocks(
        title="ScanSplitter",
        theme=gr.themes.Soft(),
    ) as app:
        gr.Markdown(
            """
            # ScanSplitter

            Automatically detect, split, and rotate multiple photos from scanned images.

            **How to use:**
            1. Upload one or more scanned images or PDFs
            2. Adjust settings if needed
            3. Click "Process" to detect and split photos
            4. Download results as a ZIP file
            """
        )

        with gr.Row():
            with gr.Column(scale=1):
                # Input section
                file_input = gr.File(
                    label="Upload Scans",
                    file_count="multiple",
                    file_types=["image", ".pdf"],
                )

                with gr.Accordion("Settings", open=False):
                    auto_rotate_checkbox = gr.Checkbox(
                        label="Auto-rotate photos",
                        value=True,
                        info="Detect and correct 90/180/270 degree rotations",
                    )
                    min_area_slider = gr.Slider(
                        minimum=1,
                        maximum=50,
                        value=2,
                        step=1,
                        label="Minimum photo size (%)",
                        info="Ignore regions smaller than this percentage of the scan",
                    )
                    max_area_slider = gr.Slider(
                        minimum=50,
                        maximum=100,
                        value=80,
                        step=1,
                        label="Maximum photo size (%)",
                        info="Ignore regions larger than this percentage of the scan",
                    )
                    format_dropdown = gr.Dropdown(
                        choices=["JPEG", "PNG"],
                        value="JPEG",
                        label="Output format",
                        info="JPEG: smaller files, PNG: lossless quality",
                    )
                    quality_slider = gr.Slider(
                        minimum=60,
                        maximum=100,
                        value=85,
                        step=5,
                        label="JPEG quality",
                        info="Higher = better quality but larger files (ignored for PNG)",
                    )

                process_btn = gr.Button("Process", variant="primary", size="lg")

            with gr.Column(scale=2):
                # Output section
                gallery = gr.Gallery(
                    label="Detected Photos",
                    show_label=True,
                    columns=3,
                    height="auto",
                    object_fit="contain",
                )
                download_btn = gr.File(
                    label="Download Results (ZIP)",
                    interactive=False,
                )

        # Wire up the processing
        process_btn.click(
            fn=process_uploads,
            inputs=[
                file_input,
                auto_rotate_checkbox,
                min_area_slider,
                max_area_slider,
                format_dropdown,
                quality_slider,
            ],
            outputs=[gallery, download_btn],
        )

    return app


def main():
    """Launch the Gradio app."""
    app = create_ui()
    app.launch()


if __name__ == "__main__":
    main()

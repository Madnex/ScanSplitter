"""Detector dispatch shared by Quick, Projects and command-line processing."""
from PIL import Image

from .album_detector import detect_album_pages
from .detector import detect_photos_v3, detect_photos_v4, detect_photos_v5
from .llm_detector import detect_photos_openrouter


def detect_regions(image: Image.Image, mode: str, min_ratio: float = .02,
                   max_ratio: float = .8, album_layout: str = "auto", overrides: dict | None = None):
    detectors = {"scansplitterv3": detect_photos_v3, "scansplitterv4": detect_photos_v4,
                 "scansplitterv5": detect_photos_v5, "album-splitter": detect_album_pages,
                 "openrouter": detect_photos_openrouter}
    detectors.update(overrides or {})
    if mode not in detectors:
        raise ValueError("detection_mode must be one of: " + ", ".join(detectors))
    if mode == "album-splitter":
        return detectors[mode](image, layout=album_layout)
    return detectors[mode](image, min_area_ratio=min_ratio, max_area_ratio=max_ratio)

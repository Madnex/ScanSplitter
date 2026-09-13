"""Canonical pixel processing; encoding and preview sizing happen afterwards."""
import cv2
import numpy as np
from PIL import Image

from .detector import DetectedRegion, crop_rotated_region
from .edge_cleanup import cleanup_photo_edges
from .restoration import apply_restorations
from .rotator import auto_rotate


def render_crop(image: Image.Image, region: DetectedRegion, settings: dict) -> Image.Image:
    pixels = crop_rotated_region(cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR), region)
    if not pixels.size:
        raise ValueError("Photo box produced an empty crop")
    result = Image.fromarray(cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB))
    mode = "off" if settings.get("detection_mode") == "album-splitter" else settings.get("edge_cleanup_mode", "tight")
    result, _ = cleanup_photo_edges(result, mode)
    if settings.get("auto_rotate", True):
        result, _ = auto_rotate(result)
    result, _ = apply_restorations(result, settings)
    operation = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}.get(settings.get("manual_rotation", 0))
    return result.transpose(operation) if operation is not None else result

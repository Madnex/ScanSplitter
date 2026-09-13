"""Shared strict validation at both HTTP and persistent-store boundaries."""
import math
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ProcessingSettings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)
    detection_mode: Literal["scansplitterv3", "scansplitterv4", "scansplitterv5", "album-splitter", "openrouter"] = "scansplitterv5"
    album_layout: Literal["auto", "single", "spread"] = "auto"
    min_area_ratio: float = Field(default=2, gt=0, lt=100)
    max_area_ratio: float = Field(default=80, gt=0, le=100)
    auto_rotate: bool = True
    edge_cleanup_mode: Literal["off", "conservative", "tight"] = "tight"
    auto_deskew: bool = False
    restore_color: bool = False
    upscale_2x: bool = False
    format: Literal["jpeg", "jpg", "png"] = "jpeg"
    quality: int = Field(default=85, ge=1, le=100)
    include_gps: bool = False
    master_format: Literal["png", "tiff"] | None = None
    organize_folders: bool = False
    manifest_format: Literal["json", "csv", "both"] | None = None

    @model_validator(mode="after")
    def area_range(self):
        if self.min_area_ratio >= self.max_area_ratio:
            raise ValueError("Minimum photo area must be less than maximum photo area")
        return self


def validate_settings(settings: dict) -> dict:
    try:
        return ProcessingSettings.model_validate(settings).model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def validate_boxes(boxes: list[dict], width: int, height: int) -> None:
    seen = set()
    for box in boxes:
        try:
            if not isinstance(box["id"], str) or not box["id"] or box["id"] in seen:
                raise ValueError("Photo IDs must be nonempty and unique")
            seen.add(box["id"])
            values = [box[k] for k in ("x", "y", "width", "height", "angle")]
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
                raise ValueError("Photo geometry must contain finite numbers")
            if not (0 <= box["x"] <= width and 0 <= box["y"] <= height):
                raise ValueError("Photo center must be inside the scan")
            # Rotated boxes can extend a little past an edge, but must stay bounded.
            if not (0 < box["width"] <= math.hypot(width, height) and 0 < box["height"] <= math.hypot(width, height)):
                raise ValueError("Photo dimensions must be positive and fit the scan diagonal")
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

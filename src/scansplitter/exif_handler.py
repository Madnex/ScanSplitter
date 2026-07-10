"""EXIF metadata handling for ScanSplitter."""

import io
from typing import Any

import piexif


def extract_exif(image_bytes: bytes) -> dict[str, Any] | None:
    """Extract EXIF data from image bytes.

    Returns a dict with parsed EXIF fields and raw bytes for later use,
    or None if no EXIF data found.
    """
    try:
        exif_dict = piexif.load(image_bytes)

        if not exif_dict or all(not v for v in exif_dict.values() if isinstance(v, dict)):
            return None

        result: dict[str, Any] = {}

        # Extract key fields we care about
        if "0th" in exif_dict and exif_dict["0th"]:
            zeroth = exif_dict["0th"]
            if piexif.ImageIFD.Make in zeroth:
                make = zeroth[piexif.ImageIFD.Make]
                result["make"] = make.decode("utf-8", errors="ignore") if isinstance(make, bytes) else str(make)
            if piexif.ImageIFD.Model in zeroth:
                model = zeroth[piexif.ImageIFD.Model]
                result["model"] = model.decode("utf-8", errors="ignore") if isinstance(model, bytes) else str(model)

        if "Exif" in exif_dict and exif_dict["Exif"]:
            exif = exif_dict["Exif"]
            if piexif.ExifIFD.DateTimeOriginal in exif:
                dt = exif[piexif.ExifIFD.DateTimeOriginal]
                result["date_taken"] = dt.decode("utf-8") if isinstance(dt, bytes) else str(dt)
            elif piexif.ExifIFD.DateTimeDigitized in exif:
                dt = exif[piexif.ExifIFD.DateTimeDigitized]
                result["date_taken"] = dt.decode("utf-8") if isinstance(dt, bytes) else str(dt)

        if "GPS" in exif_dict and exif_dict["GPS"]:
            result["has_gps"] = True

        # Store raw exif bytes for later use
        try:
            result["_raw"] = piexif.dump(exif_dict)
        except Exception:
            pass

        return result if result else None

    except Exception:
        return None


def _strip_gps(exif_dict: dict[str, Any]) -> None:
    """Remove all GPS metadata from a parsed piexif dict, in place.

    Clears the dedicated GPS IFD as well as the GPSTag pointer in the 0th IFD
    (the offset that references the GPS IFD). The Exif IFD itself has no
    standard GPS-location tags, so nothing there needs removing.
    """
    exif_dict["GPS"] = {}
    zeroth = exif_dict.get("0th")
    if isinstance(zeroth, dict):
        zeroth.pop(piexif.ImageIFD.GPSTag, None)


def create_exif_bytes(
    date_taken: str | None = None,
    original_exif: bytes | None = None,
    include_gps: bool = True,
    clear_date: bool = False,
) -> bytes | None:
    """Create EXIF bytes with optionally modified date.

    Args:
        date_taken: Date string in format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS"
        original_exif: Raw EXIF bytes from original image to preserve
        include_gps: When False, strip the GPS IFD from the output (privacy).
        clear_date: When True, remove DateTimeOriginal/DateTimeDigitized even
            if they were present in ``original_exif``. An explicit clear wins
            over any copied original date; ignored when ``date_taken`` is set.

    Returns:
        EXIF bytes ready to be inserted into an image, or None on error.
    """
    try:
        if original_exif:
            exif_dict = piexif.load(original_exif)
        else:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

        if "Exif" not in exif_dict or exif_dict["Exif"] is None:
            exif_dict["Exif"] = {}

        if date_taken:
            # Parse and format date
            # Accept formats: "2024-01-15", "2024-01-15 14:30:00", "2024:01:15 14:30:00"
            date_taken = date_taken.replace("-", ":")
            if len(date_taken) == 10:  # Just date
                date_taken += " 00:00:00"

            date_bytes = date_taken.encode("utf-8")
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_bytes
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_bytes
        elif clear_date:
            # Explicit clear beats any date copied from the original EXIF.
            exif_dict["Exif"].pop(piexif.ExifIFD.DateTimeOriginal, None)
            exif_dict["Exif"].pop(piexif.ExifIFD.DateTimeDigitized, None)

        if not include_gps:
            _strip_gps(exif_dict)

        return piexif.dump(exif_dict)
    except Exception:
        return None


def apply_exif_to_jpeg(jpeg_bytes: bytes, exif_bytes: bytes) -> bytes:
    """Apply EXIF data to a JPEG image.

    Args:
        jpeg_bytes: Original JPEG image bytes
        exif_bytes: EXIF bytes from create_exif_bytes

    Returns:
        JPEG bytes with EXIF data inserted.
    """
    try:
        output = io.BytesIO()
        piexif.insert(exif_bytes, jpeg_bytes, output)
        return output.getvalue()
    except Exception:
        return jpeg_bytes  # Return original if EXIF insertion fails

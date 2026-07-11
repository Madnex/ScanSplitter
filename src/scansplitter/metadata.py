"""Validation and portable JPEG metadata for persistent projects."""

from __future__ import annotations

import struct
from datetime import date
from typing import Any
from xml.etree import ElementTree as ET

import piexif

METADATA_DEFAULTS: dict[str, Any] = {
    "date": None,
    "date_label": None,
    "date_precision": None,
    "place_name": None,
    "latitude": None,
    "longitude": None,
    "caption": None,
    "people": [],
    "event": None,
    "album": None,
}

_TEXT_FIELDS = {"date_label", "place_name", "event", "album"}
_PRECISIONS = {"day", "month", "year", "season", "circa"}


def metadata_defaults() -> dict[str, Any]:
    """Return fresh defaults (the people list must not be shared)."""
    return {**METADATA_DEFAULTS, "people": []}


def normalize_metadata_patch(patch: dict[str, Any], current: dict[str, Any] | None = None) -> dict:
    """Validate a partial patch and merge it with current/default metadata."""
    unknown = set(patch) - set(METADATA_DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown metadata field: {sorted(unknown)[0]}")

    result = metadata_defaults()
    if current:
        result.update({key: current.get(key) for key in METADATA_DEFAULTS if key in current})
        result["people"] = list(current.get("people") or [])

    for key, value in patch.items():
        if key == "people":
            if value is None:
                raise ValueError("people must be a list")
            if not isinstance(value, list):
                raise ValueError("people must be a list")
            if len(value) > 100:
                raise ValueError("people may contain at most 100 names")
            people: list[str] = []
            seen: set[str] = set()
            for raw in value:
                if not isinstance(raw, str):
                    raise ValueError("each person must be text")
                name = raw.strip()
                if len(name) > 200:
                    raise ValueError("person names may contain at most 200 characters")
                folded = name.casefold()
                if name and folded not in seen:
                    seen.add(folded)
                    people.append(name)
            result[key] = people
        elif key == "date":
            value = _nullable_text(value, 10, "date")
            if value:
                try:
                    parsed = date.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError("date must use YYYY-MM-DD") from exc
                if parsed.isoformat() != value:
                    raise ValueError("date must use YYYY-MM-DD")
            result[key] = value
        elif key == "date_precision":
            value = _nullable_text(value, 20, "date_precision")
            if value is not None and value not in _PRECISIONS:
                raise ValueError("invalid date precision")
            result[key] = value
        elif key == "caption":
            result[key] = _nullable_text(value, 2000, "caption")
        elif key in _TEXT_FIELDS:
            result[key] = _nullable_text(value, 200, key)
        elif key in {"latitude", "longitude"}:
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise ValueError(f"{key} must be a number or null")
            result[key] = float(value) if value is not None else None

    lat, lon = result["latitude"], result["longitude"]
    if (lat is None) != (lon is None):
        raise ValueError("latitude and longitude must be set or cleared together")
    if lat is not None and not -90 <= lat <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if lon is not None and not -180 <= lon <= 180:
        raise ValueError("longitude must be between -180 and 180")
    return result


def _nullable_text(value: Any, limit: int, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text or null")
    value = value.strip()
    if len(value) > limit:
        raise ValueError(f"{field} may contain at most {limit} characters")
    return value or None


def has_metadata(metadata: dict[str, Any]) -> bool:
    return any(metadata.get(key) for key in METADATA_DEFAULTS)


def create_metadata_exif(metadata: dict[str, Any], include_gps: bool) -> bytes | None:
    """Create EXIF for the representative date and optional coordinates."""
    exif: dict[str, Any] = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    if metadata.get("date"):
        stamp = metadata["date"].replace("-", ":") + " 00:00:00"
        encoded = stamp.encode("ascii")
        exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = encoded
        exif["Exif"][piexif.ExifIFD.DateTimeDigitized] = encoded
    if include_gps and metadata.get("latitude") is not None:
        lat = float(metadata["latitude"])
        lon = float(metadata["longitude"])
        exif["GPS"] = {
            piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S",
            piexif.GPSIFD.GPSLatitude: _gps_rationals(abs(lat)),
            piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W",
            piexif.GPSIFD.GPSLongitude: _gps_rationals(abs(lon)),
        }
    return piexif.dump(exif) if exif["Exif"] or exif["GPS"] else None


def _gps_rationals(value: float) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    degrees = int(value)
    minutes_full = (value - degrees) * 60
    minutes = int(minutes_full)
    seconds_million = round((minutes_full - minutes) * 60 * 1_000_000)
    return ((degrees, 1), (minutes, 1), (seconds_million, 1_000_000))


def create_xmp_packet(metadata: dict[str, Any]) -> bytes | None:
    """Build a compact standards-based XMP packet, or None when empty."""
    if not has_metadata(metadata):
        return None
    namespaces = {
        "x": "adobe:ns:meta/",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "dc": "http://purl.org/dc/elements/1.1/",
        "photoshop": "http://ns.adobe.com/photoshop/1.0/",
        "ss": "https://scansplitter.app/ns/1.0/",
    }
    for prefix, uri in namespaces.items():
        ET.register_namespace(prefix, uri)
    root = ET.Element(f"{{{namespaces['x']}}}xmpmeta")
    rdf = ET.SubElement(root, f"{{{namespaces['rdf']}}}RDF")
    desc = ET.SubElement(rdf, f"{{{namespaces['rdf']}}}Description")
    if metadata.get("date"):
        desc.set(f"{{{namespaces['ss']}}}representativeDate", metadata["date"])
    if metadata.get("date_label"):
        desc.set(f"{{{namespaces['ss']}}}dateLabel", metadata["date_label"])
    if metadata.get("date_precision"):
        desc.set(f"{{{namespaces['ss']}}}datePrecision", metadata["date_precision"])
    if metadata.get("place_name"):
        desc.set(f"{{{namespaces['photoshop']}}}Location", metadata["place_name"])
    if metadata.get("caption"):
        description = ET.SubElement(desc, f"{{{namespaces['dc']}}}description")
        alt = ET.SubElement(description, f"{{{namespaces['rdf']}}}Alt")
        li = ET.SubElement(alt, f"{{{namespaces['rdf']}}}li")
        li.set("{http://www.w3.org/XML/1998/namespace}lang", "x-default")
        li.text = metadata["caption"]
    keywords = [f"Person: {name}" for name in metadata.get("people", [])]
    keywords += [f"Event: {metadata['event']}"] if metadata.get("event") else []
    keywords += [f"Album: {metadata['album']}"] if metadata.get("album") else []
    if keywords:
        subject = ET.SubElement(desc, f"{{{namespaces['dc']}}}subject")
        bag = ET.SubElement(subject, f"{{{namespaces['rdf']}}}Bag")
        for keyword in keywords:
            ET.SubElement(bag, f"{{{namespaces['rdf']}}}li").text = keyword
    return ET.tostring(root, encoding="utf-8", xml_declaration=False)


def insert_xmp(jpeg_bytes: bytes, packet: bytes) -> bytes:
    """Insert an Adobe XMP APP1 segment immediately after JPEG SOI."""
    if not jpeg_bytes.startswith(b"\xff\xd8"):
        return jpeg_bytes
    payload = b"http://ns.adobe.com/xap/1.0/\x00" + packet
    if len(payload) + 2 > 65535:
        raise ValueError("XMP packet is too large")
    segment = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    return jpeg_bytes[:2] + segment + jpeg_bytes[2:]

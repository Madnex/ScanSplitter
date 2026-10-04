"""Portable, consumer-independent digitization bundles for persistent projects."""

import hashlib
import json
import mimetypes
import uuid
import zipfile

from fastapi import HTTPException

from . import __version__
from .jobs import JobCancelled


def build_archive_bundle(
    store,
    pid,
    fmt,
    quality,
    include_gps,
    master_format,
    include_originals,
    progress,
    cancelled,
    artifact_path,
):
    # Snapshot the catalog once; all references and output geometry use this snapshot.
    from .projects import _EXPORTABLE_STATUSES, _encode_image

    data = store._read(pid)
    scans = [s for s in data["scans"] if s["status"] in _EXPORTABLE_STATUSES]
    if not scans:
        raise HTTPException(400, "No reviewed scans to export")
    manifest = {
        "schema": "scansplitter.archive-bundle",
        "version": 1,
        "producer": {"name": "ScanSplitter", "version": __version__},
        "project": {"id": pid, "name": data["name"]},
        "ordering": "project_scan_order",
        "files": [],
        "scans": [],
        "photos": [],
    }
    source_ids = {}
    included_scan_ids = {s["id"] for s in scans}
    with zipfile.ZipFile(artifact_path, "w", zipfile.ZIP_DEFLATED) as archive:

        def add(fid, path, payload, role):
            archive.writestr(path, payload)
            manifest["files"].append(
                {
                    "id": fid,
                    "path": path,
                    "role": role,
                    "media_type": mimetypes.guess_type(path)[0] or "application/octet-stream",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
            return fid

        for index, scan in enumerate(scans):
            if cancelled():
                raise JobCancelled
            progress(int(index * 90 / len(scans)), "Building archive bundle")
            sid = scan["id"]
            metadata = dict(scan.get("metadata") or {})
            if not include_gps:
                metadata.pop("latitude", None)
                metadata.pop("longitude", None)
            source_id = None
            if include_originals:
                if scan.get("source_integrity") != "original" or not scan.get("source_file"):
                    raise HTTPException(
                        400,
                        "Original source unavailable for a legacy scan; re-import it or omit originals",
                    )
                source = store._project_dir(pid) / scan["source_file"]
                payload = source.read_bytes()
                digest = hashlib.sha256(payload).hexdigest()
                if digest != scan.get("source_sha256"):
                    raise HTTPException(400, "Original source checksum mismatch")
                if scan["source_file"] not in source_ids:
                    fid = f"source-{sid}"
                    source_ids[scan["source_file"]] = add(
                        fid, f"sources/{sid}{source.suffix.lower()}", payload, "source_original"
                    )
                source_id = source_ids[scan["source_file"]]
            image = store._source_image(pid, scan)
            page_id = add(
                f"scan-{sid}",
                f"scans/{sid}.png",
                _encode_image(image.convert("RGB"), "png", quality, metadata, include_gps),
                "scan_image",
            )
            manifest["scans"].append(
                {
                    "id": sid,
                    "file_id": page_id,
                    "source_file_id": source_id,
                    "source_name": scan["original_name"],
                    "source_sha256": scan.get("source_sha256"),
                    "source_integrity": scan.get("source_integrity", "legacy_derivative"),
                    "source_page": scan.get("page"),
                    "sequence": index + 1,
                    "back_of": scan.get("back_of")
                    if scan.get("back_of") in included_scan_ids
                    else None,
                    "review_status": scan["status"],
                    "coordinate_size": [scan["width"], scan["height"]],
                    "image_size": [image.width, image.height],
                    "metadata": metadata,
                }
            )
            for position, box in enumerate(scan["boxes"], 1):
                if cancelled():
                    raise JobCancelled
                bid = box["id"]
                identity = f"{sid}-{hashlib.sha256(bid.encode()).hexdigest()[:24]}"
                crop = store._render_crop(pid, scan, box, data["settings"], image)
                crop_meta = {
                    **metadata,
                    **({"caption": box["caption"]} if box.get("caption") else {}),
                }
                ext = "png" if fmt == "png" else "jpg"
                access = add(
                    f"access-{identity}",
                    f"photos/{identity}.{ext}",
                    _encode_image(crop, ext, quality, crop_meta, include_gps),
                    "access",
                )
                processed = None
                if master_format:
                    ext = "png" if master_format == "png" else "tif"
                    processed = add(
                        f"processed-{identity}",
                        f"processed/{identity}.{ext}",
                        _encode_image(crop, ext, quality, crop_meta, include_gps),
                        "processed_derivative",
                    )
                manifest["photos"].append(
                    {
                        "id": identity,
                        "scan_id": sid,
                        "box_id": bid,
                        "sequence": position,
                        "access_file_id": access,
                        "processed_file_id": processed,
                        "geometry": {
                            "type": "rotated_rect",
                            "units": "normalized",
                            "center": [box["x"] / scan["width"], box["y"] / scan["height"]],
                            "size": [box["width"] / scan["width"], box["height"] / scan["height"]],
                            "angle": (box["angle"] + 180) % 360 - 180,
                        },
                        "metadata": crop_meta,
                        "transformations": {**data["settings"], **box.get("restoration", {})},
                    }
                )
        # Stable identity for identical exports, independent of ZIP timestamps.
        identity = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        manifest["package_id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, identity))
        archive.writestr("archive-manifest.json", json.dumps(manifest, sort_keys=True, indent=2))
    return artifact_path

"""Explicit Phase 4 delivery targets for completed export artifacts."""

import base64
import io
import json
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException


def _http_root(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Delivery URL must use http or https")
    return value.rstrip("/")


def archive_files(payload: bytes) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return [(name, archive.read(name)) for name in archive.namelist() if not name.endswith("/")]


def write_watched_folder(payload: bytes, destination: Path) -> int:
    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    for name, data in archive_files(payload):
        target = (destination / name).resolve()
        if not target.is_relative_to(destination):
            raise HTTPException(status_code=400, detail="Invalid export path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        count += 1
    return count


def upload_nextcloud(payload: bytes, base_url: str, username: str, password: str, folder: str) -> int:
    root = _http_root(base_url)
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    count = 0
    for name, data in archive_files(payload):
        remote = "/".join(part for part in (folder.strip("/"), name) if part)
        request = urllib.request.Request(
            f"{root}/{urllib.parse.quote(remote, safe='/')}", data=data, method="PUT",
            headers={"Authorization": f"Basic {auth}", "X-NC-WebDAV-AutoMkcol": "1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status not in {200, 201, 204}:
                    raise HTTPException(status_code=502, detail=f"Nextcloud returned {response.status}")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Nextcloud upload failed: {exc}") from exc
        count += 1
    return count


def _multipart(fields: dict[str, str], filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = f"scansplitter-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"assetData\"; filename=\"{Path(filename).name}\"\r\nContent-Type: image/jpeg\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def upload_immich(payload: bytes, server_url: str, api_key: str) -> int:
    root = _http_root(server_url)
    endpoint = f"{root}/assets" if root.endswith("/api") else f"{root}/api/assets"
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for name, data in archive_files(payload):
        if not name.lower().endswith((".jpg", ".jpeg", ".png")) or name.startswith("masters/"):
            continue
        body, content_type = _multipart(
            {"deviceAssetId": f"scansplitter-{uuid.uuid5(uuid.NAMESPACE_URL, name)}", "deviceId": "scansplitter", "fileCreatedAt": now, "fileModifiedAt": now, "filename": Path(name).name, "metadata": json.dumps([])}, name, data,
        )
        request = urllib.request.Request(endpoint, data=body, method="POST", headers={"x-api-key": api_key, "Content-Type": content_type})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                if response.status not in {200, 201}:
                    raise HTTPException(status_code=502, detail=f"Immich returned {response.status}")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Immich upload failed: {exc}") from exc
        count += 1
    return count

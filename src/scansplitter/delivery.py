"""Explicit Phase 4 delivery targets for completed export artifacts."""

import base64
import io
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

DELIVERY_REQUIRED_FIELDS = {
    "folder": {"destination"},
    "immich": {"server_url", "api_key"},
    "nextcloud": {"base_url", "username", "password"},
}


def _http_root(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Delivery URL must use http or https")
    return value.rstrip("/")


def archive_files(
    payload: bytes, include: Callable[[str], bool] | None = None
) -> Iterator[tuple[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in archive.namelist():
            if not name.endswith("/") and (include is None or include(name)):
                yield name, archive.read(name)


def write_watched_folder(payload: bytes, destination: Path, overwrite: bool = False) -> int:
    destination = destination.expanduser().resolve()
    if not destination.is_dir():
        raise HTTPException(status_code=400, detail="Destination must be an existing directory")
    conflicts: list[str] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
    for name in names:
        target = _folder_target(destination, name)
        if not overwrite and target.exists():
            conflicts.append(name)
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail=f"Files already exist: {', '.join(sorted(conflicts))}",
        )
    count = 0
    for name, data in archive_files(payload):
        target = _folder_target(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        count += 1
    return count


def _folder_target(destination: Path, name: str) -> Path:
    target = (destination / name).resolve()
    if not target.is_relative_to(destination):
        raise HTTPException(status_code=400, detail="Invalid export path")
    return target


def upload_nextcloud(payload: bytes, base_url: str, username: str, password: str, folder: str) -> int:
    root = _http_root(base_url)
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    count = 0
    for name, data in archive_files(payload):
        remote = "/".join(part for part in (folder.strip("/"), name) if part)
        url = f"{root}/{urllib.parse.quote(remote, safe='/')}"
        headers = {
            "Authorization": f"Basic {auth}",
            "X-NC-WebDAV-Auto-Mkcol": "1",
            "X-NC-WebDAV-AutoMkcol": "1",
        }
        request = urllib.request.Request(url, data=data, method="PUT", headers=headers)
        try:
            try:
                _open_nextcloud(request, {200, 201, 204})
            except urllib.error.HTTPError as exc:
                if exc.code != 409:
                    raise
                parts = remote.split("/")[:-1]
                for index in range(1, len(parts) + 1):
                    collection = "/".join(parts[:index])
                    mkcol = urllib.request.Request(
                        f"{root}/{urllib.parse.quote(collection, safe='/')}",
                        method="MKCOL",
                        headers={"Authorization": f"Basic {auth}"},
                    )
                    try:
                        _open_nextcloud(mkcol, {200, 201, 204, 405})
                    except urllib.error.HTTPError as mkcol_exc:
                        if mkcol_exc.code != 405:
                            raise
                _open_nextcloud(request, {200, 201, 204})
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Nextcloud upload failed: {exc}") from exc
        count += 1
    return count


def _open_nextcloud(request: urllib.request.Request, expected: set[int]) -> None:
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status not in expected:
            raise HTTPException(status_code=502, detail=f"Nextcloud returned {response.status}")


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
    def is_access_image(name: str) -> bool:
        return name.lower().endswith((".jpg", ".jpeg", ".png")) and not name.startswith("masters/")

    for name, data in archive_files(payload, is_access_image):
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

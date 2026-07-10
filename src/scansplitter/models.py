"""Model download and management for face detection and orientation detection."""

import hashlib
import logging
import threading
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Per-read network timeout for model downloads (seconds)
DOWNLOAD_TIMEOUT = 30
_DOWNLOAD_CHUNK_SIZE = 256 * 1024

# Model URLs from OpenCV's GitHub (face detection)
PROTOTXT_URL = "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt"
CAFFEMODEL_URL = "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel"
# The prototxt tracks opencv master and may legitimately change, so it is not
# hash-pinned. Binary models are pinned to known-good SHA-256 hashes.
CAFFEMODEL_SHA256 = "2a56a11a57a4a295956b0660b4a3d76bbdca2206c4961cea8efe7d95c7cb2f2d"

# Orientation detection model (EfficientNetV2 ONNX)
# Primary: original source, Fallback: our own backup
ORIENTATION_MODEL_URLS = [
    "https://github.com/duartebarbosadev/deep-image-orientation-detection/releases/download/v2/orientation_model_v2_0.9882.onnx",
    "https://github.com/Madnex/ScanSplitter/releases/download/models-v1/orientation_model_v2.onnx",
]
ORIENTATION_MODEL_FILENAME = "orientation_model_v2.onnx"

# U2-Net salient object detection models (ONNX)
# u2netp is the lightweight version (~4.7MB), u2net is the full version (~176MB)
U2NETP_MODEL_URLS = [
    "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx",
    "https://github.com/Madnex/ScanSplitter/releases/download/models-v1/u2netp.onnx",
]
U2NETP_MODEL_FILENAME = "u2netp.onnx"

U2NET_MODEL_URLS = [
    "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
    "https://github.com/Madnex/ScanSplitter/releases/download/models-v1/u2net.onnx",
]
U2NET_MODEL_FILENAME = "u2net.onnx"

# Cache directory for models
MODELS_DIR = Path(__file__).parent / "model_cache"


_MODEL_SPECS: dict[str, dict[str, Any]] = {
    "orientation": {
        "filename": ORIENTATION_MODEL_FILENAME,
        "urls": ORIENTATION_MODEL_URLS,
        "size_desc": "~80MB",
        "label": "Orientation model",
        "sha256": "cffe911c1dff47fbfbbd90110aaab9c07134645c460d35b3ae8832079bea91ba",
    },
    "u2net_lite": {
        "filename": U2NETP_MODEL_FILENAME,
        "urls": U2NETP_MODEL_URLS,
        "size_desc": "~5MB",
        "label": "U2-Net lite model",
        "sha256": "309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8",
    },
    "u2net_full": {
        "filename": U2NET_MODEL_FILENAME,
        "urls": U2NET_MODEL_URLS,
        "size_desc": "~176MB",
        "label": "U2-Net full model",
        "sha256": "8d10d2f3bb75ae3b6d527c77944fc5e7dcd94b29809d47a739a7a728a912b491",
    },
}

_MODEL_STATUS_LOCK = threading.Lock()
_MODEL_STATUS: dict[str, dict[str, Any]] = {}
_MODEL_DOWNLOAD_THREADS: dict[str, threading.Thread] = {}


def _model_path(key: str) -> Path:
    MODELS_DIR.mkdir(exist_ok=True)
    spec = _MODEL_SPECS.get(key)
    if not spec:
        raise KeyError(f"Unknown model key: {key}")
    return MODELS_DIR / str(spec["filename"])


def _set_model_status(key: str, **updates: Any) -> None:
    spec = _MODEL_SPECS.get(key, {})
    with _MODEL_STATUS_LOCK:
        current = _MODEL_STATUS.get(key, {})
        merged = {
            "key": key,
            "status": current.get("status", "missing"),
            "progress": current.get("progress", 0),
            "downloaded_bytes": current.get("downloaded_bytes", 0),
            "total_bytes": current.get("total_bytes", 0),
            "error": current.get("error"),
            "size_desc": spec.get("size_desc", ""),
            "filename": spec.get("filename", ""),
            "label": spec.get("label", key),
        }
        merged.update(updates)
        _MODEL_STATUS[key] = merged


def get_model_statuses() -> dict[str, dict[str, Any]]:
    """Return current download status for known models."""
    MODELS_DIR.mkdir(exist_ok=True)
    for key in _MODEL_SPECS:
        path = _model_path(key)
        with _MODEL_STATUS_LOCK:
            current = _MODEL_STATUS.get(key)
        if path.exists():
            if not current or current.get("status") != "downloading":
                _set_model_status(key, status="ready", progress=100, error=None)
        else:
            if not current:
                _set_model_status(key, status="missing", progress=0, error=None)
    with _MODEL_STATUS_LOCK:
        return {k: dict(v) for k, v in _MODEL_STATUS.items()}


def _fetch_url(
    url: str,
    dest: Path,
    sha256: str | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> None:
    """Download a URL to dest with timeout, optional hash check, atomic rename.

    Downloads to a temporary ".part" file first so a failed or tampered
    download never leaves a partial/bad file at the final path.

    Args:
        url: Source URL.
        dest: Final destination path.
        sha256: Expected SHA-256 hex digest; verified before rename if given.
        progress_cb: Optional callback(downloaded_bytes, total_bytes).

    Raises:
        RuntimeError: If the checksum does not match.
    """
    tmp_path = dest.with_suffix(dest.suffix + ".part")
    hasher = hashlib.sha256()
    downloaded = 0

    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response:
            total = int(response.headers.get("Content-Length") or 0)
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    if progress_cb is not None:
                        progress_cb(downloaded, total)

        if sha256 is not None and hasher.hexdigest() != sha256:
            raise RuntimeError(
                f"Checksum mismatch for {url}: expected {sha256}, got {hasher.hexdigest()}"
            )

        tmp_path.replace(dest)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def get_model_paths() -> tuple[Path, Path]:
    """Get paths to the face detection model files, downloading if needed.

    Returns:
        Tuple of (prototxt_path, caffemodel_path)
    """
    MODELS_DIR.mkdir(exist_ok=True)

    prototxt_path = MODELS_DIR / "deploy.prototxt"
    caffemodel_path = MODELS_DIR / "res10_300x300_ssd_iter_140000.caffemodel"

    if not prototxt_path.exists():
        logger.info("Downloading face detection prototxt...")
        _fetch_url(PROTOTXT_URL, prototxt_path)

    if not caffemodel_path.exists():
        logger.info("Downloading face detection model (10MB)...")
        _fetch_url(CAFFEMODEL_URL, caffemodel_path, sha256=CAFFEMODEL_SHA256)

    return prototxt_path, caffemodel_path


def _download_model_blocking(key: str) -> Path:
    """Download a model (if missing), updating global status as it progresses."""
    spec = _MODEL_SPECS.get(key)
    if not spec:
        raise KeyError(f"Unknown model key: {key}")

    dest = _model_path(key)
    if dest.exists():
        _set_model_status(key, status="ready", progress=100, error=None)
        return dest

    urls: list[str] = list(spec["urls"])
    label: str = str(spec["label"])
    size_desc: str = str(spec["size_desc"])

    _set_model_status(
        key,
        status="downloading",
        progress=0,
        downloaded_bytes=0,
        total_bytes=0,
        error=None,
    )

    def report_progress(downloaded: int, total_size: int) -> None:
        percent = 0
        if total_size > 0:
            percent = int(min(100, downloaded * 100 // total_size))
        _set_model_status(
            key,
            status="downloading",
            progress=percent,
            downloaded_bytes=int(downloaded),
            total_bytes=int(total_size),
        )

    expected_sha256 = spec.get("sha256")

    last_error: Exception | None = None
    for i, url in enumerate(urls):
        try:
            logger.info("Downloading %s from %s", label, url)
            _fetch_url(url, dest, sha256=expected_sha256, progress_cb=report_progress)
            _set_model_status(key, status="ready", progress=100, error=None)
            return dest
        except Exception as e:
            last_error = e
            if i < len(urls) - 1:
                logger.warning("Download of %s failed (%s), trying backup URL...", label, e)
            continue

    message = f"Failed to download {label} ({size_desc}): {last_error}"
    _set_model_status(key, status="error", error=message)
    raise RuntimeError(message) from last_error


def start_model_download(key: str) -> dict[str, Any]:
    """Start downloading a model in the background (if needed)."""
    statuses = get_model_statuses()
    current = statuses.get(key)
    if not current:
        raise KeyError(f"Unknown model key: {key}")
    if current.get("status") == "ready":
        return current

    with _MODEL_STATUS_LOCK:
        existing = _MODEL_DOWNLOAD_THREADS.get(key)
        if existing and existing.is_alive():
            return dict(_MODEL_STATUS.get(key, current))

        thread = threading.Thread(target=_download_model_blocking, args=(key,), daemon=True)
        _MODEL_DOWNLOAD_THREADS[key] = thread
        thread.start()

        return dict(_MODEL_STATUS.get(key, current))


def get_orientation_model_path() -> Path:
    """Get path to the orientation detection ONNX model, downloading if needed.

    Tries multiple URLs in order (primary source, then backup).

    Returns:
        Path to the ONNX model file
    """
    return _download_model_blocking("orientation")


def get_u2net_model_path(lite: bool = True) -> Path:
    """Get path to the U2-Net salient object detection ONNX model.

    Downloads the model on first use if not already cached.

    Args:
        lite: If True, use u2netp (4.7MB, faster). If False, use u2net (176MB, more accurate).

    Returns:
        Path to the ONNX model file
    """
    return _download_model_blocking("u2net_lite" if lite else "u2net_full")

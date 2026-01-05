"""Model download and management for face detection and orientation detection."""

import sys
import threading
import urllib.request
from pathlib import Path
from typing import Any

# Model URLs from OpenCV's GitHub (face detection)
PROTOTXT_URL = "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt"
CAFFEMODEL_URL = "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel"

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
    },
    "u2net_lite": {
        "filename": U2NETP_MODEL_FILENAME,
        "urls": U2NETP_MODEL_URLS,
        "size_desc": "~5MB",
        "label": "U2-Net lite model",
    },
    "u2net_full": {
        "filename": U2NET_MODEL_FILENAME,
        "urls": U2NET_MODEL_URLS,
        "size_desc": "~176MB",
        "label": "U2-Net full model",
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


def get_model_paths() -> tuple[Path, Path]:
    """Get paths to the face detection model files, downloading if needed.

    Returns:
        Tuple of (prototxt_path, caffemodel_path)
    """
    MODELS_DIR.mkdir(exist_ok=True)

    prototxt_path = MODELS_DIR / "deploy.prototxt"
    caffemodel_path = MODELS_DIR / "res10_300x300_ssd_iter_140000.caffemodel"

    if not prototxt_path.exists():
        print("Downloading face detection prototxt...")
        urllib.request.urlretrieve(PROTOTXT_URL, prototxt_path)

    if not caffemodel_path.exists():
        print("Downloading face detection model (10MB)...")
        urllib.request.urlretrieve(CAFFEMODEL_URL, caffemodel_path)

    return prototxt_path, caffemodel_path


def _download_with_progress(url: str, dest: Path, description: str) -> None:
    """Download a file with progress reporting."""

    def report_progress(block_num: int, block_size: int, total_size: int) -> None:
        if total_size > 0:
            downloaded = block_num * block_size
            percent = min(100, downloaded * 100 // total_size)
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            sys.stdout.write(f"\r{description}: {mb_downloaded:.1f}/{mb_total:.1f} MB ({percent}%)")
            sys.stdout.flush()

    urllib.request.urlretrieve(url, dest, reporthook=report_progress)
    print()  # Newline after progress


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

    def report_progress(block_num: int, block_size: int, total_size: int) -> None:
        downloaded = block_num * block_size
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
        if total_size > 0:
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            sys.stdout.write(f"\rDownloading {label}: {mb_downloaded:.1f}/{mb_total:.1f} MB ({percent}%)")
            sys.stdout.flush()

    last_error: Exception | None = None
    for i, url in enumerate(urls):
        try:
            urllib.request.urlretrieve(url, dest, reporthook=report_progress)
            print()
            _set_model_status(key, status="ready", progress=100, error=None)
            return dest
        except Exception as e:
            last_error = e
            dest.unlink(missing_ok=True)
            if i < len(urls) - 1:
                print(f"\nPrimary URL failed, trying backup...")
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

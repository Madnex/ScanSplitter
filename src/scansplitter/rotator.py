"""Automatic rotation detection and correction for photos."""

import threading

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image

# Lazy-loaded models.
# _face_net_lock also guards inference: cv2.dnn.Net is not thread-safe.
# _orientation_lock only guards lazy creation (ORT session.run is thread-safe).
_face_net = None
_face_net_lock = threading.Lock()
_orientation_session = None
_orientation_lock = threading.Lock()

# Orientation model configuration
_ORIENTATION_IMAGE_SIZE = 384
_ORIENTATION_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_ORIENTATION_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_ORIENTATION_CLASS_TO_ANGLE = {0: 0, 1: 90, 2: 180, 3: 270}


def _get_face_net():
    """Lazy-load the face detection neural network.

    Caller must hold _face_net_lock.
    """
    global _face_net
    if _face_net is None:
        from .models import get_model_paths

        prototxt_path, caffemodel_path = get_model_paths()
        _face_net = cv2.dnn.readNetFromCaffe(str(prototxt_path), str(caffemodel_path))
    return _face_net


def detect_face(cv_image: np.ndarray, min_confidence: float = 0.7) -> bool:
    """
    Detect if there's a face in the image using DNN.

    Args:
        cv_image: OpenCV image (BGR format)
        min_confidence: Minimum confidence threshold (0-1)

    Returns:
        True if a face is detected with sufficient confidence
    """
    # Create blob from image (resize to 300x300 as expected by the model)
    blob = cv2.dnn.blobFromImage(
        cv2.resize(cv_image, (300, 300)),
        1.0,
        (300, 300),
        (104.0, 177.0, 123.0),
    )

    # cv2.dnn.Net is stateful (setInput/forward) and not thread-safe:
    # serialize inference across worker threads.
    with _face_net_lock:
        net = _get_face_net()
        net.setInput(blob)
        detections = net.forward()

    # Check if any face detected with sufficient confidence
    for i in range(detections.shape[2]):
        confidence = detections[0, 0, i, 2]
        if confidence >= min_confidence:
            return True

    return False


def detect_rotation_by_face(image: Image.Image) -> int | None:
    """
    Detect the correct rotation using face detection.

    Tries each 90-degree rotation and returns the one where a face is detected.

    Args:
        image: PIL Image to analyze

    Returns:
        Rotation angle (0, 90, 180, 270) if face found, None otherwise
    """
    cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    # Try original orientation first
    if detect_face(cv_image):
        return 0

    h, w = cv_image.shape[:2]
    center = (w / 2, h / 2)

    # Try 90, 180, 270 degree rotations
    for angle in [90, 180, 270]:
        rotation_matrix = cv2.getRotationMatrix2D(center, -angle, 1.0)

        # Calculate new dimensions after rotation
        cos_a = abs(rotation_matrix[0, 0])
        sin_a = abs(rotation_matrix[0, 1])
        new_w = int(h * sin_a + w * cos_a)
        new_h = int(h * cos_a + w * sin_a)

        # Adjust rotation matrix for new dimensions
        rotation_matrix[0, 2] += (new_w - w) / 2
        rotation_matrix[1, 2] += (new_h - h) / 2

        rotated = cv2.warpAffine(cv_image, rotation_matrix, (new_w, new_h))

        if detect_face(rotated):
            return angle

    return None  # No face detected in any orientation


def _get_orientation_session() -> ort.InferenceSession:
    """Lazy-load the orientation detection ONNX model (thread-safe)."""
    global _orientation_session
    with _orientation_lock:
        if _orientation_session is None:
            from .models import get_orientation_model_path

            model_path = get_orientation_model_path()
            _orientation_session = ort.InferenceSession(
                str(model_path),
                providers=["CPUExecutionProvider"],
            )
        return _orientation_session


def _preprocess_for_orientation(image: Image.Image) -> np.ndarray:
    """Preprocess image for orientation model inference.

    Args:
        image: PIL Image to preprocess

    Returns:
        Preprocessed numpy array in NCHW format (1, 3, 384, 384)
    """
    # Convert to RGB if needed
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Resize to IMAGE_SIZE + 32 = 416
    resize_size = _ORIENTATION_IMAGE_SIZE + 32
    image = image.resize((resize_size, resize_size), Image.Resampling.BILINEAR)

    # Center crop to IMAGE_SIZE = 384
    left = (resize_size - _ORIENTATION_IMAGE_SIZE) // 2
    top = (resize_size - _ORIENTATION_IMAGE_SIZE) // 2
    image = image.crop((left, top, left + _ORIENTATION_IMAGE_SIZE, top + _ORIENTATION_IMAGE_SIZE))

    # Convert to numpy and normalize
    img_array = np.array(image, dtype=np.float32) / 255.0
    img_array = (img_array - _ORIENTATION_MEAN) / _ORIENTATION_STD

    # Transpose from HWC to CHW and add batch dimension
    img_array = img_array.transpose(2, 0, 1)
    img_array = np.expand_dims(img_array, axis=0)

    return img_array


def detect_rotation_by_deep_learning(image: Image.Image) -> int | None:
    """
    Detect the correct rotation using a deep learning model (EfficientNetV2).

    This is the most accurate method, trained on a large dataset with 98.82% accuracy.

    Args:
        image: PIL Image to analyze

    Returns:
        Rotation angle (0, 90, 180, 270) needed to correct orientation, or None on error
    """
    try:
        session = _get_orientation_session()

        # Preprocess image
        input_tensor = _preprocess_for_orientation(image)

        # Run inference
        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: input_tensor})

        # Get predicted class
        logits = outputs[0]
        predicted_class = int(np.argmax(logits, axis=1)[0])

        return _ORIENTATION_CLASS_TO_ANGLE.get(predicted_class, 0)
    except Exception:
        # If anything fails, return None to trigger fallback
        return None


def score_rotation(image: Image.Image) -> float:
    """
    Score an image orientation based on edge alignment.

    Higher scores indicate better alignment (more horizontal/vertical edges).
    Uses Hough line detection to find dominant line angles.

    Args:
        image: PIL Image to analyze

    Returns:
        Score where higher = better orientation
    """
    cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

    # Apply edge detection
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    # Detect lines using probabilistic Hough transform
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=50,
        minLineLength=30,
        maxLineGap=10,
    )

    if lines is None:
        return 0.0

    # Score based on how many lines are near horizontal (0) or vertical (90)
    score = 0.0
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        angle = abs(angle) % 90

        # Lines at 0 or 90 get high scores, lines at 45 get low scores
        if angle < 10 or angle > 80:
            line_length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            score += line_length

    return score


def detect_rotation_by_edges(image: Image.Image) -> int:
    """
    Detect the best rotation angle based on edge alignment (Hough lines).

    Tests 0, 90, 180, and 270 rotations and returns the best one.

    Args:
        image: PIL Image to analyze

    Returns:
        Best rotation angle in degrees (0, 90, 180, or 270)
    """
    best_angle = 0
    best_score = -1.0

    for angle in [0, 90, 180, 270]:
        if angle == 0:
            rotated = image
        else:
            rotated = image.rotate(-angle, expand=True)

        score = score_rotation(rotated)

        if score > best_score:
            best_score = score
            best_angle = angle

    return best_angle


def detect_rotation(image: Image.Image) -> int:
    """
    Detect the best rotation angle for an image.

    Uses a fallback chain:
    1. Deep learning model (most accurate, 98.82% accuracy)
    2. Face detection (reliable for photos with people)
    3. Edge-based detection (fallback for landscapes, objects)

    Args:
        image: PIL Image to analyze

    Returns:
        Best rotation angle in degrees (0, 90, 180, or 270)
    """
    # Try deep learning model first - most accurate
    dl_angle = detect_rotation_by_deep_learning(image)
    if dl_angle is not None:
        return dl_angle

    # Fall back to face detection for photos with people
    face_angle = detect_rotation_by_face(image)
    if face_angle is not None:
        return face_angle

    # Fall back to edge-based detection for landscapes, objects, etc.
    return detect_rotation_by_edges(image)


def auto_rotate(image: Image.Image) -> tuple[Image.Image, int]:
    """
    Automatically rotate an image to the correct orientation.

    Args:
        image: PIL Image to rotate

    Returns:
        Tuple of (rotated image, angle applied)
    """
    angle = detect_rotation(image)

    if angle == 0:
        return image, 0

    rotated = image.rotate(-angle, expand=True)
    return rotated, angle


def rotate_images(images: list[Image.Image]) -> list[tuple[Image.Image, int]]:
    """
    Auto-rotate a list of images.

    Args:
        images: List of PIL Images

    Returns:
        List of tuples (rotated image, angle applied)
    """
    return [auto_rotate(img) for img in images]

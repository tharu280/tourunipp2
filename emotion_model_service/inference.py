from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

import cv2
import numpy as np
from PIL import Image

try:
    from tflite_runtime.interpreter import Interpreter
except ImportError:
    try:
        from tensorflow.lite.python.interpreter import Interpreter
    except ImportError:
        try:
            import tensorflow as tf

            Interpreter = tf.lite.Interpreter
        except ImportError:
            Interpreter = None


IMAGE_SIZE = (100, 100)
CLASS_NAMES = ["anger", "happy", "neutral", "sad", "surprise"]
ROTATION_ANGLES = (0.0, -15.0, 15.0)
CROP_SCALES = (0.95, 1.0, 1.05)
CROP_CENTER_Y = 0.5
MODEL_VERSION = "rafdb5_hf_three_crop_tflite"
MODEL_PATH = Path(__file__).resolve().parent / "models" / "emotion_rafdb5.tflite"

_interpreter: Any | None = None
_interpreter_lock = Lock()


def get_interpreter() -> Any:
    global _interpreter
    if _interpreter is not None:
        return _interpreter

    if Interpreter is None:
        raise RuntimeError("Install tflite-runtime or tensorflow to run inference.")
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model file not found: {MODEL_PATH}")

    _interpreter = Interpreter(model_path=str(MODEL_PATH))
    _interpreter.allocate_tensors()
    return _interpreter


def rotate_image(rgb_image: np.ndarray, angle: float) -> np.ndarray:
    height, width = rgb_image.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos_value = abs(matrix[0, 0])
    sin_value = abs(matrix[0, 1])
    new_width = int((height * sin_value) + (width * cos_value))
    new_height = int((height * cos_value) + (width * sin_value))
    matrix[0, 2] += (new_width / 2.0) - center[0]
    matrix[1, 2] += (new_height / 2.0) - center[1]
    return cv2.warpAffine(
        rgb_image,
        matrix,
        (new_width, new_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )


def detect_haar_boxes(rgb_image: np.ndarray) -> list[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    classifier = cv2.CascadeClassifier(cascade_path)
    if classifier.empty():
        raise RuntimeError(f"Could not load Haar cascade: {cascade_path}")

    faces = classifier.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(40, 40),
    )
    return [(x, y, x + width, y + height) for x, y, width, height in faces]


def find_face_with_rotation(rgb_image: np.ndarray) -> tuple[np.ndarray, list[tuple[int, int, int, int]], float]:
    for angle in ROTATION_ANGLES:
        rotated = rotate_image(rgb_image, angle)
        boxes = detect_haar_boxes(rotated)
        if boxes:
            return rotated, boxes, angle
    raise ValueError("No face detected after rotation retries.")


def crop_largest_face(
    rgb_image: np.ndarray,
    boxes: list[tuple[int, int, int, int]],
    crop_scale: float,
) -> Image.Image:
    image_height, image_width = rgb_image.shape[:2]
    x_min, y_min, x_max, y_max = max(
        boxes,
        key=lambda box: float((box[2] - box[0]) * (box[3] - box[1])),
    )
    box_width = x_max - x_min
    box_height = y_max - y_min
    crop_size = int(max(box_width, box_height) * crop_scale)
    center_x = (x_min + x_max) / 2.0
    center_y = y_min + (box_height * CROP_CENTER_Y)

    crop_x_min = int(round(center_x - crop_size / 2.0))
    crop_y_min = int(round(center_y - crop_size / 2.0))
    crop_x_max = crop_x_min + crop_size
    crop_y_max = crop_y_min + crop_size

    if crop_x_min < 0:
        crop_x_max -= crop_x_min
        crop_x_min = 0
    if crop_y_min < 0:
        crop_y_max -= crop_y_min
        crop_y_min = 0
    if crop_x_max > image_width:
        shift = crop_x_max - image_width
        crop_x_min = max(0, crop_x_min - shift)
        crop_x_max = image_width
    if crop_y_max > image_height:
        shift = crop_y_max - image_height
        crop_y_min = max(0, crop_y_min - shift)
        crop_y_max = image_height

    crop = rgb_image[crop_y_min:crop_y_max, crop_x_min:crop_x_max]
    if crop.size == 0:
        raise ValueError("Face crop was empty.")
    return Image.fromarray(crop)


def prepare_input(crop: Image.Image, dtype: np.dtype) -> np.ndarray:
    resized = crop.convert("RGB").resize(IMAGE_SIZE)
    image_array = np.asarray(resized, dtype=np.float32) / 255.0
    return np.expand_dims(image_array.astype(dtype), axis=0)


def predict_probabilities(interpreter: Any, crop: Image.Image) -> np.ndarray:
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    image_batch = prepare_input(crop, input_detail["dtype"])

    # TFLite interpreters are not safe for concurrent invoke calls.
    with _interpreter_lock:
        interpreter.set_tensor(input_detail["index"], image_batch)
        interpreter.invoke()
        return interpreter.get_tensor(output_detail["index"])[0].copy()


def build_prediction(probabilities: np.ndarray, top_k: int = 3) -> dict[str, Any]:
    top_indices = np.argsort(probabilities)[::-1][:top_k]
    return {
        "emotion_label": CLASS_NAMES[int(np.argmax(probabilities))],
        "emotion_confidence": float(np.max(probabilities)),
        "top_predictions": [
            {
                "class_name": CLASS_NAMES[int(index)],
                "probability": float(probabilities[int(index)]),
            }
            for index in top_indices
        ],
        "all_scores": {
            class_name: float(probabilities[index])
            for index, class_name in enumerate(CLASS_NAMES)
        },
        "model_version": MODEL_VERSION,
    }


def classify_rgb_array(rgb_image: np.ndarray, top_k: int = 3) -> dict[str, Any]:
    if rgb_image is None:
        raise ValueError("An image is required.")
    if rgb_image.ndim != 3 or rgb_image.shape[2] not in (3, 4):
        raise ValueError("Expected an RGB or RGBA image.")

    normalized_rgb = np.asarray(rgb_image[:, :, :3], dtype=np.uint8)
    rotated_rgb, boxes, rotation_used = find_face_with_rotation(normalized_rgb)
    interpreter = get_interpreter()

    probability_rows = []
    for crop_scale in CROP_SCALES:
        crop = crop_largest_face(rotated_rgb, boxes, crop_scale)
        probability_rows.append(predict_probabilities(interpreter, crop))

    averaged_probabilities = np.mean(np.stack(probability_rows, axis=0), axis=0)
    result = build_prediction(averaged_probabilities, top_k=top_k)
    result["preprocessing"] = {
        "detector": "haar_frontalface_default",
        "rotation_used_degrees": rotation_used,
        "crop_scales": list(CROP_SCALES),
        "crop_center_y": CROP_CENTER_Y,
        "input_size": list(IMAGE_SIZE),
    }
    return result


def classify_image_bytes(image_bytes: bytes, top_k: int = 3) -> dict[str, Any]:
    encoded = np.frombuffer(image_bytes, np.uint8)
    bgr_image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if bgr_image is None:
        raise ValueError("Could not decode the uploaded image.")
    rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
    return classify_rgb_array(rgb_image, top_k=top_k)

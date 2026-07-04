import os
from pathlib import Path

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

# Use the absolute path if available, or relative to the workspace root
MODEL_PATH = (
    Path(__file__).resolve().parents[2]
    / "clean_run"
    / "new cnn"
    / "five_class"
    / "outputs"
    / "scratch_cnn_rafdb5_e40"
    / "emotion_rafdb5.tflite"
)

# Global interpreter cache
_interpreter = None

def get_interpreter() -> Interpreter:
    global _interpreter
    if _interpreter is not None:
        return _interpreter

    if Interpreter is None:
        raise RuntimeError("tflite-runtime or tensorflow is not installed.")

    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model file not found at {MODEL_PATH}")

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
        raise RuntimeError(f"Could not load Haar cascade from {cascade_path}")
    faces = classifier.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
    return [(x, y, x + w, y + h) for x, y, w, h in faces]


def load_rgb_with_rotation(
    bgr_image: np.ndarray,
    rotation_angles: list[float],
) -> tuple[np.ndarray, list[tuple[int, int, int, int]], float]:
    rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)

    for angle in rotation_angles:
        rotated = rotate_image(rgb_image, angle)
        boxes = detect_haar_boxes(rotated)
        if boxes:
            return rotated, boxes, angle

    raise ValueError("No face detected after trying rotation retries.")


def crop_largest_face(
    rgb_image: np.ndarray,
    boxes: list[tuple[int, int, int, int]],
    crop_scale: float,
    crop_center_y: float,
) -> Image.Image:
    height, width, _ = rgb_image.shape
    x_min, y_min, x_max, y_max = max(
        boxes,
        key=lambda box: float((box[2] - box[0]) * (box[3] - box[1])),
    )
    box_width = x_max - x_min
    box_height = y_max - y_min

    crop_size = int(max(box_width, box_height) * crop_scale)
    center_x = (x_min + x_max) / 2.0
    center_y = y_min + (box_height * crop_center_y)

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
    if crop_x_max > width:
        shift = crop_x_max - width
        crop_x_min = max(0, crop_x_min - shift)
        crop_x_max = width
    if crop_y_max > height:
        shift = crop_y_max - height
        crop_y_min = max(0, crop_y_min - shift)
        crop_y_max = height

    return Image.fromarray(rgb_image[crop_y_min:crop_y_max, crop_x_min:crop_x_max])


def prepare_input(crop: Image.Image, dtype: np.dtype) -> np.ndarray:
    resized = crop.convert("RGB").resize(IMAGE_SIZE)
    array = np.asarray(resized, dtype=np.float32) / 255.0
    return np.expand_dims(array.astype(dtype), axis=0)


def predict_probabilities(interpreter: Interpreter, crop: Image.Image) -> np.ndarray:
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    image_batch = prepare_input(crop, input_detail["dtype"])
    interpreter.set_tensor(input_detail["index"], image_batch)
    interpreter.invoke()
    return interpreter.get_tensor(output_detail["index"])[0]


def build_prediction(probabilities: np.ndarray, top_k: int) -> dict:
    top_indices = np.argsort(probabilities)[::-1][:top_k]
    top_predictions = [
        {
            "class_name": CLASS_NAMES[int(index)],
            "probability": float(probabilities[int(index)]),
        }
        for index in top_indices
    ]
    return {
        "predicted_class": CLASS_NAMES[int(np.argmax(probabilities))],
        "confidence": float(np.max(probabilities)),
        "top_predictions": top_predictions,
        "all_scores": {
            class_name: float(probabilities[index])
            for index, class_name in enumerate(CLASS_NAMES)
        },
    }


def classify_image_bytes(
    image_bytes: bytes,
    rotation_angles: list[float] = [0.0, -15.0, 15.0],
    crop_scales: list[float] = [0.95, 1.0, 1.05],
    crop_center_y: float = 0.5,
    top_k: int = 3,
) -> dict:
    nparr = np.frombuffer(image_bytes, np.uint8)
    bgr_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if bgr_image is None:
        raise ValueError("Could not decode image bytes.")

    interpreter = get_interpreter()

    rotated_rgb, boxes, _ = load_rgb_with_rotation(
        bgr_image=bgr_image,
        rotation_angles=rotation_angles,
    )

    probability_rows = []
    for crop_scale in crop_scales:
        crop = crop_largest_face(
            rotated_rgb,
            boxes,
            crop_scale=crop_scale,
            crop_center_y=crop_center_y,
        )
        probabilities = predict_probabilities(interpreter, crop)
        probability_rows.append(probabilities)

    averaged_probabilities = np.mean(np.stack(probability_rows, axis=0), axis=0)
    ensemble_prediction = build_prediction(averaged_probabilities, top_k)

    return {
        "emotion_label": ensemble_prediction["predicted_class"],
        "emotion_confidence": ensemble_prediction["confidence"],
        "top_predictions": ensemble_prediction["top_predictions"],
        "model_version": "rafdb5_server_tflite",
    }

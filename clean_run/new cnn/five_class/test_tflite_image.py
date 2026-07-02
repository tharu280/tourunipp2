from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import tensorflow as tf


IMAGE_SIZE = (100, 100)
CLASS_NAMES = ["anger", "happy", "neutral", "sad", "surprise"]
DEFAULT_MODEL = (
    Path(__file__).resolve().parent
    / "outputs"
    / "scratch_cnn_rafdb5_e40"
    / "emotion_rafdb5.tflite"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test the exported emotion TFLite model on one or more images."
    )
    parser.add_argument("image_paths", type=Path, nargs="+", help="Image files or folders of images.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output-dir", type=Path, default=Path("emotion_test_outputs"))
    parser.add_argument("--crop-scale", type=float, default=1.00)
    parser.add_argument(
        "--crop-scales",
        type=float,
        nargs="*",
        default=None,
        help="Optional list of crop scales to test/ensemble, e.g. --crop-scales 0.95 1.00 1.05.",
    )
    parser.add_argument("--crop-center-y", type=float, default=0.50)
    parser.add_argument("--rotation-angles", type=float, nargs="*", default=[0.0, -15.0, 15.0])
    parser.add_argument("--top-k", type=int, default=3)
    return parser.parse_args()


def expand_image_paths(paths: list[Path]) -> list[Path]:
    image_paths: list[Path] = []
    allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp"}
    for path in paths:
        if path.is_dir():
            image_paths.extend(
                sorted(
                    child
                    for child in path.iterdir()
                    if child.is_file() and child.suffix.lower() in allowed_suffixes
                )
            )
        else:
            image_paths.append(path)
    return image_paths


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

    # This mirrors the original FER-style crop from five_class/infer.py.
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
    image_path: Path,
    rotation_angles: list[float],
) -> tuple[np.ndarray, list[tuple[int, int, int, int]], float]:
    bgr_image = cv2.imread(str(image_path))
    if bgr_image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)

    for angle in rotation_angles:
        rotated = rotate_image(rgb_image, angle)
        boxes = detect_haar_boxes(rotated)
        if boxes:
            return rotated, boxes, angle

    raise ValueError("No face detected after trying rotation retries.")


def prepare_input(crop: Image.Image, dtype: np.dtype) -> np.ndarray:
    resized = crop.convert("RGB").resize(IMAGE_SIZE)
    array = np.asarray(resized, dtype=np.float32) / 255.0
    return np.expand_dims(array.astype(dtype), axis=0)


def predict_probabilities(interpreter: tf.lite.Interpreter, crop: Image.Image) -> np.ndarray:
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


def safe_scale_label(scale: float) -> str:
    return f"{scale:.2f}".replace(".", "_")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    interpreter = tf.lite.Interpreter(model_path=str(args.model))
    interpreter.allocate_tensors()

    crop_scales = args.crop_scales if args.crop_scales else [args.crop_scale]
    results = []
    for image_path in expand_image_paths(args.image_paths):
        try:
            rotated_rgb, boxes, rotation_used = load_rgb_with_rotation(
                image_path=image_path,
                rotation_angles=args.rotation_angles,
            )
            scale_results = []
            probability_rows = []
            for crop_scale in crop_scales:
                crop = crop_largest_face(
                    rotated_rgb,
                    boxes,
                    crop_scale=crop_scale,
                    crop_center_y=args.crop_center_y,
                )
                crop_path = (
                    args.output_dir
                    / f"{image_path.stem}_crop_scale_{safe_scale_label(crop_scale)}.jpg"
                )
                crop.save(crop_path)
                probabilities = predict_probabilities(interpreter, crop)
                probability_rows.append(probabilities)
                scale_results.append(
                    {
                        "crop_scale": crop_scale,
                        "saved_crop_path": str(crop_path.resolve()),
                        **build_prediction(probabilities, args.top_k),
                    }
                )

            averaged_probabilities = np.mean(np.stack(probability_rows, axis=0), axis=0)
            ensemble_prediction = build_prediction(averaged_probabilities, args.top_k)
            results.append(
                {
                    "image_path": str(image_path.resolve()),
                    "status": "ok",
                    "rotation_used_degrees": rotation_used,
                    "crop_center_y": args.crop_center_y,
                    "crop_scales_used": crop_scales,
                    "scale_results": scale_results,
                    "predicted_class": ensemble_prediction["predicted_class"],
                    "confidence": ensemble_prediction["confidence"],
                    "top_predictions": ensemble_prediction["top_predictions"],
                    "all_scores": ensemble_prediction["all_scores"],
                }
            )
        except Exception as exc:
            results.append(
                {
                    "image_path": str(image_path.resolve()),
                    "status": "error",
                    "error": str(exc),
                }
            )

    results_path = args.output_dir / "predictions.json"
    results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"results_path": str(results_path.resolve()), "results": results}, indent=2))


if __name__ == "__main__":
    main()

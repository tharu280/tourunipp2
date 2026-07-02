from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from tensorflow import keras

from config import CLASS_NAMES, IMAGE_SIZE, OUTPUT_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run single-image inference with the 5-class scratch CNN.")
    parser.add_argument("image_path", type=Path)
    parser.add_argument(
        "--model",
        type=Path,
        default=OUTPUT_ROOT / "scratch_cnn_rafdb5_e40" / "best_model.keras",
    )
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--no-face-detect", action="store_true")
    parser.add_argument("--detector", choices=["auto", "mediapipe", "haar"], default="auto")
    parser.add_argument("--rotation-angles", type=float, nargs="*", default=[0.0, -15.0, 15.0])
    parser.add_argument("--save-crop", type=Path, default=None)
    parser.add_argument("--single-label-threshold", type=float, default=0.6)
    parser.add_argument("--pair-gap-threshold", type=float, default=0.12)
    parser.add_argument("--uncertain-threshold", type=float, default=0.35)
    parser.add_argument("--use-tta", action="store_true")
    parser.add_argument("--crop-scale", type=float, default=1.20)
    parser.add_argument("--crop-center-y", type=float, default=0.50)
    return parser.parse_args()


def _crop_largest_box(
    rgb_image: np.ndarray,
    boxes: list[tuple[int, int, int, int]],
    crop_scale: float,
    crop_center_y: float,
) -> Image.Image:
    height, width, _ = rgb_image.shape
    best_box = None
    best_area = -1.0
    for x_min, y_min, x_max, y_max in boxes:
        box_width = x_max - x_min
        box_height = y_max - y_min
        area = float(box_width * box_height)
        if area > best_area:
            best_area = area
            best_box = (x_min, y_min, x_max, y_max)
    if best_box is None:
        raise ValueError("Face detection did not return a usable bounding box.")
    x_min, y_min, x_max, y_max = best_box
    box_width = x_max - x_min
    box_height = y_max - y_min

    # Build a tighter square FER-style crop that keeps forehead, eyes, and mouth visible.
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


def _rotate_image(rgb_image: np.ndarray, angle: float) -> tuple[np.ndarray, np.ndarray]:
    height, width = rgb_image.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos_value = abs(matrix[0, 0])
    sin_value = abs(matrix[0, 1])
    new_width = int((height * sin_value) + (width * cos_value))
    new_height = int((height * cos_value) + (width * sin_value))
    matrix[0, 2] += (new_width / 2.0) - center[0]
    matrix[1, 2] += (new_height / 2.0) - center[1]
    rotated = cv2.warpAffine(
        rgb_image,
        matrix,
        (new_width, new_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated, matrix


def _detect_boxes_mediapipe(rgb_image: np.ndarray) -> list[tuple[int, int, int, int]]:
    try:
        import mediapipe as mp
    except ImportError as exc:
        raise ImportError("MediaPipe is not installed.") from exc
    height, width, _ = rgb_image.shape
    face_detection_cls = None
    if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_detection"):
        face_detection_cls = mp.solutions.face_detection.FaceDetection
    else:
        try:
            from mediapipe.python.solutions.face_detection import FaceDetection
            face_detection_cls = FaceDetection
        except ImportError as exc:
            raise ImportError("Could not import MediaPipe face detection.") from exc
    detector = face_detection_cls(model_selection=1, min_detection_confidence=0.5)
    results = detector.process(rgb_image)
    detector.close()
    if not results.detections:
        return []
    boxes: list[tuple[int, int, int, int]] = []
    for detection in results.detections:
        bbox = detection.location_data.relative_bounding_box
        x_min = max(0, int(bbox.xmin * width))
        y_min = max(0, int(bbox.ymin * height))
        box_width = int(bbox.width * width)
        box_height = int(bbox.height * height)
        x_max = min(width, x_min + box_width)
        y_max = min(height, y_min + box_height)
        boxes.append((x_min, y_min, x_max, y_max))
    return boxes


def _detect_boxes_haar(rgb_image: np.ndarray) -> list[tuple[int, int, int, int]]:
    bgr_image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    classifier = cv2.CascadeClassifier(cascade_path)
    if classifier.empty():
        raise RuntimeError(f"Could not load Haarcascade from {cascade_path}")
    faces = classifier.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
    if len(faces) == 0:
        return []
    return [(x, y, x + w, y + h) for x, y, w, h in faces]


def _detect_boxes(rgb_image: np.ndarray, detector_name: str) -> tuple[list[tuple[int, int, int, int]], str]:
    if detector_name == "haar":
        return _detect_boxes_haar(rgb_image), "haar"
    if detector_name == "mediapipe":
        return _detect_boxes_mediapipe(rgb_image), "mediapipe"
    try:
        boxes = _detect_boxes_mediapipe(rgb_image)
        if boxes:
            return boxes, "mediapipe"
    except Exception:
        pass
    return _detect_boxes_haar(rgb_image), "haar"


def detect_main_face(
    image_path: Path,
    detector_name: str,
    rotation_angles: list[float],
    crop_scale: float,
    crop_center_y: float,
) -> tuple[Image.Image, str, float]:
    bgr_image = cv2.imread(str(image_path))
    if bgr_image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
    attempted_errors: list[str] = []
    for angle in rotation_angles:
        rotated_image, _ = _rotate_image(rgb_image, angle)
        try:
            boxes, detector_used = _detect_boxes(rotated_image, detector_name)
        except Exception as exc:
            attempted_errors.append(f"angle={angle}: {exc}")
            continue
        if boxes:
            return _crop_largest_box(rotated_image, boxes, crop_scale, crop_center_y), detector_used, angle
    error_message = "No face detected in the image after trying rotation retries."
    if attempted_errors:
        error_message += " Detector errors: " + " | ".join(attempted_errors)
    raise ValueError(error_message)


def save_crop_image(image: Image.Image, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def _resize_for_model(image: Image.Image) -> np.ndarray:
    image_for_model = image.resize(IMAGE_SIZE)
    return np.asarray(image_for_model, dtype=np.float32) / 255.0


def build_tta_views(face_image: Image.Image) -> list[Image.Image]:
    base = face_image.convert("RGB")
    width, height = base.size
    views = [base]

    for crop_ratio in [0.9, 0.8]:
        crop_w = int(width * crop_ratio)
        crop_h = int(height * crop_ratio)
        left = max(0, (width - crop_w) // 2)
        top = max(0, (height - crop_h) // 2)
        right = left + crop_w
        bottom = top + crop_h
        views.append(base.crop((left, top, right, bottom)))

    crop_ratio = 0.9
    crop_w = int(width * crop_ratio)
    crop_h = int(height * crop_ratio)
    left = max(0, (width - crop_w) // 2)
    top = max(0, int((height - crop_h) * 0.25))
    right = min(width, left + crop_w)
    bottom = min(height, top + crop_h)
    views.append(base.crop((left, top, right, bottom)))

    views.append(base.transpose(Image.FLIP_LEFT_RIGHT))
    return views


def build_display_label(
    top_predictions: list[dict[str, float | str]],
    single_label_threshold: float,
    pair_gap_threshold: float,
    uncertain_threshold: float,
) -> str:
    top1 = top_predictions[0]
    top1_label = str(top1["class_name"])
    top1_prob = float(top1["probability"])
    if top1_prob >= single_label_threshold:
        return top1_label
    if len(top_predictions) >= 2:
        top2 = top_predictions[1]
        top2_label = str(top2["class_name"])
        top2_prob = float(top2["probability"])
        if (top1_prob - top2_prob) <= pair_gap_threshold:
            return f"likely {top1_label} / {top2_label}"
    if top1_prob < uncertain_threshold:
        return "uncertain"
    return f"likely {top1_label}"


def predict_probabilities(model: keras.Model, image_batch: np.ndarray) -> np.ndarray:
    return model.predict(image_batch, verbose=0)[0]


def predict_probabilities_tta(model: keras.Model, face_image: Image.Image) -> tuple[np.ndarray, int]:
    views = build_tta_views(face_image)
    batch = np.stack([_resize_for_model(view) for view in views], axis=0)
    probabilities = model.predict(batch, verbose=0)
    return probabilities.mean(axis=0), len(views)


def build_prediction_payload(
    image_path: Path,
    model_path: Path,
    face_detection_used: bool,
    detector_used: str | None,
    rotation_used: float,
    save_crop_path: Path | None,
    probabilities: np.ndarray,
    top_k: int,
    single_label_threshold: float,
    pair_gap_threshold: float,
    uncertain_threshold: float,
    tta_used: bool,
    tta_num_views: int,
) -> dict:
    top_indices = np.argsort(probabilities)[::-1][:top_k]
    top_predictions = [
        {"class_name": CLASS_NAMES[int(index)], "probability": float(probabilities[int(index)])}
        for index in top_indices
    ]
    display_label = build_display_label(
        top_predictions=top_predictions,
        single_label_threshold=single_label_threshold,
        pair_gap_threshold=pair_gap_threshold,
        uncertain_threshold=uncertain_threshold,
    )
    return {
        "image_path": str(image_path.resolve()),
        "model_path": str(model_path.resolve()),
        "face_detection_used": face_detection_used,
        "detector_used": detector_used,
        "rotation_used_degrees": rotation_used,
        "saved_crop_path": str(save_crop_path.resolve()) if save_crop_path is not None else None,
        "tta_used": tta_used,
        "tta_num_views": tta_num_views,
        "predicted_class": CLASS_NAMES[int(np.argmax(probabilities))],
        "confidence": float(np.max(probabilities)),
        "display_label": display_label,
        "top_predictions": top_predictions,
    }


def load_image(
    image_path: Path,
    use_face_detection: bool,
    detector_name: str,
    rotation_angles: list[float],
    crop_scale: float,
    crop_center_y: float,
) -> tuple[np.ndarray, str | None, float, Image.Image]:
    detector_used = None
    rotation_used = 0.0
    if use_face_detection:
        image, detector_used, rotation_used = detect_main_face(
            image_path,
            detector_name,
            rotation_angles,
            crop_scale,
            crop_center_y,
        )
    else:
        image = Image.open(image_path).convert("RGB")
    image_array = _resize_for_model(image)
    return np.expand_dims(image_array, axis=0), detector_used, rotation_used, image


def main() -> None:
    args = parse_args()
    model = keras.models.load_model(args.model)
    image_batch, detector_used, rotation_used, crop_image = load_image(
        args.image_path,
        use_face_detection=not args.no_face_detect,
        detector_name=args.detector,
        rotation_angles=args.rotation_angles,
        crop_scale=args.crop_scale,
        crop_center_y=args.crop_center_y,
    )
    if args.save_crop is not None:
        save_crop_image(crop_image, args.save_crop)
    if args.use_tta:
        probabilities, tta_num_views = predict_probabilities_tta(model, crop_image)
    else:
        probabilities = predict_probabilities(model, image_batch)
        tta_num_views = 1
    prediction = build_prediction_payload(
        image_path=args.image_path,
        model_path=args.model,
        face_detection_used=not args.no_face_detect,
        detector_used=detector_used,
        rotation_used=rotation_used,
        save_crop_path=args.save_crop,
        probabilities=probabilities,
        top_k=args.top_k,
        single_label_threshold=args.single_label_threshold,
        pair_gap_threshold=args.pair_gap_threshold,
        uncertain_threshold=args.uncertain_threshold,
        tta_used=args.use_tta,
        tta_num_views=tta_num_views,
    )
    print(json.dumps(prediction, indent=2))


if __name__ == "__main__":
    main()

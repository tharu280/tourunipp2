from __future__ import annotations

import argparse
import json
from pathlib import Path

import tensorflow as tf

from config import CLASS_NAMES, IMAGE_SIZE, OUTPUT_ROOT


DEFAULT_MODEL_PATH = OUTPUT_ROOT / "scratch_cnn_rafdb5_e40" / "best_model.keras"
DEFAULT_EXPORT_PATH = OUTPUT_ROOT / "scratch_cnn_rafdb5_e40" / "emotion_rafdb5.tflite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the RAF-DB 5-class Keras model to TensorFlow Lite.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_EXPORT_PATH)
    parser.add_argument("--float16", action="store_true", help="Enable float16 weight quantization.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = tf.keras.models.load_model(args.model)
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    if args.float16:
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.target_spec.supported_types = [tf.float16]

    tflite_model = converter.convert()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(tflite_model)

    metadata = {
        "model_source": str(args.model),
        "tflite_path": str(args.output),
        "input_shape": [1, IMAGE_SIZE[1], IMAGE_SIZE[0], 3],
        "input_dtype": "float32",
        "input_scale": "pixel values normalized to 0..1",
        "preprocessing": {
            "face_detector": "Haar cascade or mobile face detector",
            "face_selection": "largest detected face",
            "crop_type": "tight square face crop",
            "recommended_crop_scale": 1.0,
            "recommended_crop_center_y": 0.5,
            "optional_stability_crop_scales": [0.95, 1.0, 1.05],
            "resize": [IMAGE_SIZE[0], IMAGE_SIZE[1]],
            "color_order": "RGB",
            "normalization": "float32 pixels divided by 255.0",
        },
        "class_names": CLASS_NAMES,
        "float16_quantized": bool(args.float16),
        "privacy_contract": {
            "run_inference_on_device": True,
            "upload_raw_image_to_backend": False,
            "store_raw_image": False,
            "identity_recognition": False,
        },
    }
    args.output.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()

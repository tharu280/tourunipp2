from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_DATA_ROOT = PROJECT_ROOT.parent / "seven_class" / "prepared"
PREPARED_DATA_ROOT = PROJECT_ROOT / "prepared"
OUTPUT_ROOT = PROJECT_ROOT / "outputs"

IMAGE_SIZE = (100, 100)
AUTOTUNE = -1

CLASS_NAMES = [
    "anger",
    "happy",
    "neutral",
    "sad",
    "surprise",
]

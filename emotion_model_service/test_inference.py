from __future__ import annotations

import argparse
import json
from pathlib import Path

from inference import classify_image_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description="Test the standalone TourUni emotion model.")
    parser.add_argument("images", nargs="+", type=Path)
    args = parser.parse_args()

    results = {}
    for image_path in args.images:
        results[str(image_path)] = classify_image_bytes(image_path.read_bytes())
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

import os
import sys

# Add root project dir to path so absolute imports work
sys.path.insert(0, os.path.abspath("."))

from clean_run.emotion.inference import classify_image_bytes

def main():
    image_path = "/Users/dilshantharushika/Desktop/routemvp/tourunipp2/reactui/public/sri_lanka_hero.jpg"
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    
    try:
        result = classify_image_bytes(image_bytes)
        print("Classification result:")
        print(result)
    except Exception as exc:
        print(f"Error during classification: {exc}")

if __name__ == "__main__":
    main()

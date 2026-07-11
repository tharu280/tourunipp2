---
title: TourUni Mood Place Finder
emoji: 🙂
colorFrom: green
colorTo: blue
sdk: gradio
app_file: app.py
pinned: false
python_version: "3.10"
---

# TourUni Mood Place Finder

This standalone service classifies a face photo, combines the result with
user-selected hobbies, and recommends nearby places using live OpenStreetMap
Overpass data. Kandy is the fixed MVP location. It has no dependency on the
trip-planning backend, MongoDB, Gemini, or the frontend.

## Model contract

- Model: five-class RAF-DB CNN exported to TensorFlow Lite
- Classes: `anger`, `happy`, `neutral`, `sad`, `surprise`
- Input: RGB face image resized to `100 x 100` and normalized to `0..1`
- Detector: OpenCV Haar frontal-face cascade
- Rotation retries: `0`, `-15`, `15` degrees
- Crop ensemble: `0.95`, `1.0`, `1.05` square crops around the largest face
- Final prediction: arithmetic mean of the three crop probability vectors

## Local test

```bash
python test_inference.py /path/to/face.jpg
```

## Local Gradio app

```bash
python -m pip install -r requirements.txt
python app.py
```

## Hugging Face deployment

Create a new **Gradio Space** and place the contents of this folder at the root
of the Space repository. Hugging Face reads this README metadata and launches
`app.py`. The combined function is exposed through Gradio's generated
`/analyze` API.

In Python, clients can call it with `gradio_client`:

```python
from gradio_client import Client, handle_file

client = Client("YOUR_USERNAME/YOUR_SPACE")
result = client.predict(
    image=handle_file("face.jpg"),
    hobbies=["Photography", "Nature"],
    api_name="/analyze",
)
print(result)
```

Uploaded images are processed in memory. This service does not deliberately
save images or predictions. Hugging Face may temporarily process uploaded files
as part of handling the request.

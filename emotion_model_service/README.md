---
title: TourUni Emotion Classifier
emoji: 🙂
colorFrom: green
colorTo: blue
sdk: gradio
app_file: app.py
pinned: false
python_version: "3.10"
---

# TourUni Emotion Model Service

This folder is a standalone copy of the emotion classifier previously used by
the hosted TourUni backend. It has no dependency on the trip-planning backend,
MongoDB, Gemini, or the frontend.

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
`app.py`. The `classify` function is also exposed through Gradio's generated API.

In Python, clients can call it with `gradio_client`:

```python
from gradio_client import Client, handle_file

client = Client("YOUR_USERNAME/YOUR_SPACE")
result = client.predict(image=handle_file("face.jpg"), api_name="/classify")
print(result)
```

Uploaded images are processed in memory. This service does not save images or
predictions.

# Emotion Check-In Contract

This module is designed for opt-in, on-device emotion check-ins.

The mobile app should:

- run the RAF-DB 5-class model locally,
- send only structured inference metadata to the backend,
- never upload the raw face image,
- never perform identity recognition.

Backend endpoint:

```http
GET /sessions/{session_id}/emotion-targets
```

Use this after a trip is planned. It returns the planned attraction targets the mobile app should watch locally:

```json
{
  "session_id": "session-id",
  "target_count": 2,
  "targets": [
    {
      "attraction_id": "temple-tooth",
      "attraction_name": "Temple of the Sacred Tooth Relic",
      "day": 1,
      "day_label": "Day 1",
      "order": 1,
      "latitude": 7.2936,
      "longitude": 80.6413,
      "checkin_radius_meters": 200
    }
  ],
  "mobile_flow": {
    "geofence_on_device": true,
    "raw_image_upload_required": false,
    "local_tflite_inference_required": true,
    "recommended_crop_scale": 1.0,
    "optional_stability_crop_scales": [0.95, 1.0, 1.05]
  }
}
```

The mobile app should use these targets to trigger:

```text
You have reached {attraction}. Want to do a quick mood check?
```

Then run the image model locally and post the result:

```http
POST /sessions/{session_id}/emotion-checkins
```

Request shape:

```json
{
  "attraction_id": "lk_kandy_tooth_relic",
  "attraction_name": "Temple of the Sacred Tooth Relic",
  "timestamp": "2026-07-20T09:30:00+05:30",
  "user_location": {
    "latitude": 7.2937,
    "longitude": 80.6414,
    "accuracy_meters": 15
  },
  "emotion_label": "happy",
  "emotion_confidence": 0.82,
  "top_predictions": [
    {"class_name": "happy", "probability": 0.82},
    {"class_name": "neutral", "probability": 0.12}
  ],
  "model_version": "rafdb5_local_tflite",
  "local_inference": true
}
```

Response shape:

```json
{
  "session_id": "session-id",
  "checkin": {},
  "recommendation": {
    "current_emotion": "happy",
    "confidence": 0.82,
    "next_experience_prediction": "low emotional friction expected for the next stop",
    "risk_level": "low",
    "score": 24,
    "components": {
      "emotion": 12,
      "crowd": 30,
      "weather": 10,
      "travel_fatigue": 25
    },
    "explanation": [],
    "recommendation": "Continue as planned."
  },
  "emotion_summary": {
    "trend": "improving",
    "recovery_status": "recovered",
    "raw_images_stored": false
  },
  "privacy": {
    "raw_image_received_by_backend": false,
    "raw_image_stored": false,
    "identity_recognition": false,
    "local_inference_required": true
  }
}
```

TFLite export:

```bash
python3 "clean_run/new cnn/five_class/export_tflite.py" --float16
```

The generated `.metadata.json` contains input shape, class order, and privacy contract.

## Runtime Flow

```text
1. Backend creates Mongo session after route planning.
2. App calls GET /sessions/{session_id}/emotion-targets.
3. App watches user location locally.
4. When user enters a target radius, app asks for optional check-in.
5. App detects/crops face locally.
6. App runs emotion_rafdb5.tflite locally.
7. App sends only emotion metadata and current location.
8. Backend validates the target, saves check-in, refreshes emotion_summary.
9. Chatbot/dashboard reloads session context and sees recovery/trend.
```

## Mobile Crop Contract

Use the model file:

```text
clean_run/new cnn/five_class/outputs/scratch_cnn_rafdb5_e40/emotion_rafdb5.tflite
```

Preprocess:

```text
largest detected face
tight square crop, crop_scale = 1.00
resize 100x100
RGB float32
divide pixels by 255.0
```

If the phone can afford three inferences, use:

```text
crop scales 0.95, 1.00, 1.05
average probabilities
```

# Emotion Model Runtime

This folder keeps the cleaned app/runtime version of the RAF-DB 5-class emotion model.

The training datasets and prepared image folders were removed from `clean_run` because they are not needed for the backend or mobile app.

Use this folder for:

- the exported mobile model
- the exact crop/inference reference
- local image testing before wiring React Native

Main files:

- `five_class/outputs/scratch_cnn_rafdb5_e40/emotion_rafdb5.tflite`
- `five_class/outputs/scratch_cnn_rafdb5_e40/emotion_rafdb5.metadata.json`
- `five_class/outputs/scratch_cnn_rafdb5_e40/best_model.keras`
- `five_class/infer.py`
- `five_class/test_tflite_image.py`


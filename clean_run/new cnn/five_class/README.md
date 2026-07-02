# RAF-DB Emotion Classifier 5-Class Runtime

Classes:

- `anger`
- `happy`
- `neutral`
- `sad`
- `surprise`

## Mobile Model

Use this in the mobile app:

```text
outputs/scratch_cnn_rafdb5_e40/emotion_rafdb5.tflite
```

Input:

```text
100x100 RGB float32 image
pixel values normalized to 0..1
shape: [1, 100, 100, 3]
```

Output:

```text
[1, 5] probabilities
class order: anger, happy, neutral, sad, surprise
```

## Crop Logic

The important part is keeping the crop face-focused. This model became unstable when too much hair, shirt, background, or watermark context was included.

1. Detect face using Haar Cascade.
2. Pick the largest detected face.
3. Create a square face crop using:
   `crop_size = max(face_width, face_height) * 1.00`
4. Center the crop on the face box.
5. Resize the crop to `100x100`.
6. Normalize with `/ 255.0`.
7. Run the TFLite model.

Optional stability mode:

```text
Run crops at 0.95, 1.00, and 1.05, then average the probabilities.
```

`infer.py` is kept as the older Keras/crop reference, but the runtime tester now defaults to the tighter `1.00` crop because it performed better on external images.

## Test Your Own Images

From the `tourunipp2` folder:

```bash
conda run -n touruni python "clean_run/new cnn/five_class/test_tflite_image.py" "/absolute/path/to/image.jpg"
```

For multiple images:

```bash
conda run -n touruni python "clean_run/new cnn/five_class/test_tflite_image.py" "/path/img1.jpg" "/path/img2.jpg" "/path/img3.jpg"
```

For a folder of images:

```bash
conda run -n touruni python "clean_run/new cnn/five_class/test_tflite_image.py" "/absolute/path/to/test-images-folder"
```

To test the optional tight ensemble:

```bash
conda run -n touruni python "clean_run/new cnn/five_class/test_tflite_image.py" "/absolute/path/to/image.jpg" --crop-scales 0.95 1.00 1.05
```

Outputs are written to:

```text
emotion_test_outputs/
```

That folder contains:

- one saved `_crop.jpg` per image
- one saved crop per tested crop scale
- `predictions.json`

Check the saved crops visually. If the crops look right, the mobile preprocessing should copy this logic.

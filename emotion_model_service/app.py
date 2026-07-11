from __future__ import annotations

import gradio as gr
import numpy as np

from inference import classify_rgb_array


def classify_photo(image: np.ndarray | None) -> dict:
    if image is None:
        raise gr.Error("Please upload or take a face photo.")
    try:
        return classify_rgb_array(image)
    except ValueError as exc:
        raise gr.Error(str(exc)) from exc


with gr.Blocks(title="TourUni Emotion Classifier") as demo:
    gr.Markdown(
        "# TourUni Emotion Classifier\n"
        "Upload a clear, front-facing photo. The image is processed in memory and is not stored."
    )
    with gr.Row():
        image_input = gr.Image(
            type="numpy",
            image_mode="RGB",
            sources=["upload", "webcam"],
            label="Face photo",
        )
        result_output = gr.JSON(label="Prediction")
    classify_button = gr.Button("Classify emotion", variant="primary")
    classify_button.click(
        fn=classify_photo,
        inputs=image_input,
        outputs=result_output,
        api_name="classify",
    )


if __name__ == "__main__":
    demo.launch()

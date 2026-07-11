from __future__ import annotations

import gradio as gr
import numpy as np

from inference import classify_rgb_array
from mood_place_finder import (
    HOBBY_PROFILES,
    KANDY_LATITUDE,
    KANDY_LONGITUDE,
    MOOD_PROFILES,
    fetch_overpass_places,
    normalize_hobbies,
    rank_places,
)


def classify_photo(image: np.ndarray | None) -> dict:
    if image is None:
        raise gr.Error("Please upload or take a face photo.")
    try:
        return classify_rgb_array(image)
    except ValueError as exc:
        raise gr.Error(str(exc)) from exc


def analyze_photo(image: np.ndarray | None, hobbies: list[str] | None) -> dict:
    """Classify locally, then return deterministic OSM recommendations."""
    prediction = classify_photo(image)
    selected_hobbies = normalize_hobbies(hobbies)
    emotion = prediction["emotion_label"]

    try:
        elements = fetch_overpass_places(emotion, hobbies=selected_hobbies)
        recommendations = rank_places(
            elements,
            emotion,
            hobbies=selected_hobbies,
            limit=5,
        )
    except RuntimeError as exc:
        raise gr.Error(
            "The emotion was classified, but nearby places are temporarily unavailable. "
            "Please try again shortly."
        ) from exc

    return {
        "emotion": emotion,
        "confidence": prediction["emotion_confidence"],
        "top_predictions": prediction["top_predictions"],
        "hobbies": selected_hobbies,
        "location": {
            "name": "Kandy",
            "latitude": KANDY_LATITUDE,
            "longitude": KANDY_LONGITUDE,
        },
        "summary": MOOD_PROFILES.get(emotion, MOOD_PROFILES["neutral"])["intro"],
        "recommendations": recommendations,
        "disclaimer": (
            "These are general wellbeing suggestions, not a mental-health "
            "diagnosis or treatment."
        ),
        "model_version": prediction["model_version"],
    }


with gr.Blocks(title="TourUni Mood Place Finder") as demo:
    gr.Markdown(
        "# TourUni Mood Place Finder\n"
        "Upload a clear, front-facing photo and select your hobbies. The image is "
        "processed in memory and is not stored. Recommendations use live "
        "OpenStreetMap data near Kandy."
    )
    with gr.Row():
        with gr.Column():
            image_input = gr.Image(
                type="numpy",
                image_mode="RGB",
                sources=["upload", "webcam"],
                label="Face photo",
            )
            hobbies_input = gr.CheckboxGroup(
                choices=list(HOBBY_PROFILES),
                label="Hobbies",
            )
        result_output = gr.JSON(label="Analysis and recommendations")
    analyze_button = gr.Button("Analyze and recommend", variant="primary")
    analyze_button.click(
        fn=analyze_photo,
        inputs=[image_input, hobbies_input],
        outputs=result_output,
        api_name="analyze",
    )


if __name__ == "__main__":
    demo.launch()

// TODO: Replace this mock with the actual local TFLite/TensorFlow.js model in the future.
// This is currently a mock classifier for the MVP "Start-of-day mood check" feature.

export async function mockClassifyEmotion(imageFile) {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        emotion_label: "neutral",
        emotion_confidence: 0.74,
        top_predictions: [
          { class_name: "neutral", probability: 0.74 },
          { class_name: "happy", probability: 0.18 },
          { class_name: "sad", probability: 0.08 }
        ]
      });
    }, 1500); // Simulate processing delay
  });
}

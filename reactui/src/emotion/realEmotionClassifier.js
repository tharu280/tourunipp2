const CLASS_NAMES = ["anger", "happy", "neutral", "sad", "surprise"];
const IMAGE_SIZE = 100;
const CROP_CENTER_Y = 0.5;
const STABILITY_CROP_SCALES = [0.95, 1.0, 1.05];
const MODEL_URL = "/models/emotion/tflite/emotion_rafdb5.tflite";
const TFLITE_BUNDLE_URL = "/tflite/tf-tflite.es2017.min.js";
const WASM_PATH = "/tflite/";

let runtimePromise = null;
let tfliteBundlePromise = null;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function loadImageFromFile(imageFile) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const objectUrl = URL.createObjectURL(imageFile);

    image.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error("Could not read the selected image."));
    };

    image.decoding = "async";
    image.src = objectUrl;
  });
}

async function loadRuntime() {
  if (!runtimePromise) {
    runtimePromise = (async () => {
      const tf = await import("@tensorflow/tfjs");
      await import("@tensorflow/tfjs-backend-webgl");
      await import("@tensorflow/tfjs-backend-cpu");

      try {
        await tf.setBackend("webgl");
      } catch {
        await tf.setBackend("cpu");
      }
      await tf.ready();

      const [blazeface, tflite] = await Promise.all([
        import("@tensorflow-models/blazeface"),
        loadTfliteBundle(tf),
      ]);

      tflite.setWasmPath(WASM_PATH);

      const [faceDetector, emotionModel] = await Promise.all([
        blazeface.load({
          maxFaces: 1,
          scoreThreshold: 0.75,
        }),
        tflite.loadTFLiteModel(MODEL_URL, {
          numThreads: Math.max(1, Math.min(2, navigator.hardwareConcurrency || 1)),
        }),
      ]);

      return { tf, faceDetector, emotionModel };
    })();
  }

  return runtimePromise;
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      existing.addEventListener("load", resolve, { once: true });
      existing.addEventListener("error", reject, { once: true });
      if (window.tflite) resolve();
      return;
    }

    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`Could not load ${src}`));
    document.head.appendChild(script);
  });
}

async function loadTfliteBundle(tf) {
  if (!tfliteBundlePromise) {
    tfliteBundlePromise = (async () => {
      window.tf = tf;
      await loadScript(TFLITE_BUNDLE_URL);
      if (!window.tflite?.loadTFLiteModel) {
        throw new Error("TFLite browser runtime did not initialize.");
      }
      return window.tflite;
    })();
  }

  return tfliteBundlePromise;
}

function largestFaceBox(predictions, image) {
  if (!predictions?.length) {
    return {
      source: "center_crop_fallback",
      xMin: image.naturalWidth * 0.25,
      yMin: image.naturalHeight * 0.14,
      xMax: image.naturalWidth * 0.75,
      yMax: image.naturalHeight * 0.72,
    };
  }

  const largest = predictions
    .map((prediction) => {
      const [xMin, yMin] = prediction.topLeft;
      const [xMax, yMax] = prediction.bottomRight;
      return {
        source: "blazeface",
        xMin,
        yMin,
        xMax,
        yMax,
        area: Math.max(0, xMax - xMin) * Math.max(0, yMax - yMin),
      };
    })
    .sort((a, b) => b.area - a.area)[0];

  return largest;
}

function drawFaceCrop(image, faceBox, cropScale) {
  const width = image.naturalWidth;
  const height = image.naturalHeight;
  const boxWidth = faceBox.xMax - faceBox.xMin;
  const boxHeight = faceBox.yMax - faceBox.yMin;
  const cropSize = Math.max(boxWidth, boxHeight) * cropScale;
  const centerX = (faceBox.xMin + faceBox.xMax) / 2;
  const centerY = faceBox.yMin + boxHeight * CROP_CENTER_Y;

  let sx = Math.round(centerX - cropSize / 2);
  let sy = Math.round(centerY - cropSize / 2);
  let sWidth = Math.round(cropSize);
  let sHeight = Math.round(cropSize);

  if (sx < 0) sx = 0;
  if (sy < 0) sy = 0;
  if (sx + sWidth > width) sx = Math.max(0, width - sWidth);
  if (sy + sHeight > height) sy = Math.max(0, height - sHeight);
  sWidth = clamp(sWidth, 1, width - sx);
  sHeight = clamp(sHeight, 1, height - sy);

  const canvas = document.createElement("canvas");
  canvas.width = IMAGE_SIZE;
  canvas.height = IMAGE_SIZE;

  const context = canvas.getContext("2d", {
    alpha: false,
    colorSpace: "srgb",
    willReadFrequently: false,
  });

  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(image, sx, sy, sWidth, sHeight, 0, 0, IMAGE_SIZE, IMAGE_SIZE);

  return {
    canvas,
    crop: { sx, sy, sWidth, sHeight, cropScale },
  };
}

async function predictForCrop({ tf, emotionModel }, canvas) {
  const outputTensor = tf.tidy(() => {
    const pixels = tf.browser.fromPixels(canvas, 3).toFloat().div(255);
    const input = pixels.expandDims(0);
    return emotionModel.predict(input);
  });

  const probabilities = Array.from(await outputTensor.data());
  outputTensor.dispose();
  return probabilities;
}

function averageProbabilityRows(rows) {
  const totals = Array(CLASS_NAMES.length).fill(0);
  rows.forEach((row) => {
    row.forEach((value, index) => {
      totals[index] += value;
    });
  });
  return totals.map((total) => total / rows.length);
}

function buildClassification(probabilities, debug) {
  const sorted = probabilities
    .map((probability, index) => ({
      class_name: CLASS_NAMES[index],
      probability,
    }))
    .sort((a, b) => b.probability - a.probability);

  return {
    emotion_label: sorted[0].class_name,
    emotion_confidence: sorted[0].probability,
    top_predictions: sorted.slice(0, 3),
    model_version: "rafdb5_browser_tflite",
    local_inference: true,
    inference_debug: debug,
  };
}

export async function classifyEmotion(imageFile) {
  const image = await loadImageFromFile(imageFile);
  const runtime = await loadRuntime();

  const predictions = await runtime.faceDetector.estimateFaces(
    image,
    false,
    false,
    true
  );
  const faceBox = largestFaceBox(predictions, image);

  const probabilityRows = [];
  const cropDebug = [];

  for (const cropScale of STABILITY_CROP_SCALES) {
    const { canvas, crop } = drawFaceCrop(image, faceBox, cropScale);
    probabilityRows.push(await predictForCrop(runtime, canvas));
    cropDebug.push(crop);
  }

  const probabilities = averageProbabilityRows(probabilityRows);

  return buildClassification(probabilities, {
    face_detection_source: faceBox.source,
    crop_center_y: CROP_CENTER_Y,
    crop_scales_used: STABILITY_CROP_SCALES,
    image_size: [IMAGE_SIZE, IMAGE_SIZE],
    crops: cropDebug,
  });
}

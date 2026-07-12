import { useRef, useState } from "react";
import { startOfDayMoodCheckinApi, startOfDayMoodCheckinImageApi } from "../api";

const EMOTIONS = [
  { id: "happy", emoji: "😊", label: "Happy" },
  { id: "neutral", emoji: "😐", label: "Neutral" },
  { id: "sad", emoji: "😔", label: "Sad" },
  { id: "anger", emoji: "😠", label: "Angry" },
  { id: "surprise", emoji: "😲", label: "Surprised" },
];

const HOBBIES = ["History", "Photography", "Music", "Nature", "Art & culture", "Food & cafes", "Walking"];

function emotionEmoji(value) {
  return EMOTIONS.find((item) => item.id === value)?.emoji || "😐";
}

function titleCase(value) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : "Mood";
}

export default function StartOfDayCheckin({ plan, session }) {
  const [inputMode, setInputMode] = useState("photo");
  const [selectedEmotion, setSelectedEmotion] = useState("happy");
  const [selectedHobbies, setSelectedHobbies] = useState([]);
  const [selectedDay, setSelectedDay] = useState(1);
  const [status, setStatus] = useState("idle");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);

  const sessionId = session?.session_id || plan?.session_id || plan?.session_storage?.session_id;
  const storageState = plan?.session_storage || plan?.plan_overview?.session_storage;
  const sessionReady = Boolean(sessionId) && storageState?.saved !== false;
  const tripDates = plan?.trip_dates || plan?.plan_overview?.trip_dates || [];
  const totalDays = tripDates.length || plan?.plan_overview?.trip_days || plan?.trip_requirements?.duration_days || 1;
  const days = Array.from({ length: totalDays }, (_, index) => index + 1);
  const startLocation = plan?.origin_resolved?.name || plan?.trip_requirements?.origin || "your trip start";

  function toggleHobby(hobby) {
    setSelectedHobbies((current) =>
      current.includes(hobby) ? current.filter((item) => item !== hobby) : [...current, hobby]
    );
  }

  function storeResponse(response) {
    setResult({
      recommendation: response.recommendation,
      nearbyTips: response.nearby_tips,
      checkin: response.checkin,
    });
    setStatus("success");
  }

  async function handlePhotoSelect(event) {
    const file = event.target.files?.[0];
    if (!file || !sessionReady) return;
    setStatus("loading");
    setError("");
    setResult(null);
    const formData = new FormData();
    formData.append("image", file);
    formData.append("day", selectedDay);
    formData.append("hobbies", JSON.stringify(selectedHobbies));
    try {
      storeResponse(await startOfDayMoodCheckinImageApi(sessionId, formData));
    } catch (requestError) {
      const message = String(requestError?.message || "");
      setError(message.toLowerCase().includes("face")
        ? "I couldn’t find a face clearly. Try a brighter, front-facing photo."
        : "The mood check could not be completed. Please try again.");
      setStatus("error");
    }
  }

  async function submitManualEmotion() {
    if (!sessionReady) return;
    setStatus("loading");
    setError("");
    setResult(null);
    try {
      storeResponse(await startOfDayMoodCheckinApi(sessionId, {
        day: selectedDay,
        emotion_label: selectedEmotion,
        emotion_confidence: 1,
        top_predictions: [{ class_name: selectedEmotion, probability: 1 }],
        model_version: "manual_user_selection",
        local_inference: false,
        hobbies: selectedHobbies,
      }));
    } catch {
      setError("The mood check could not be completed. Please try again.");
      setStatus("error");
    }
  }

  function reset() {
    setStatus("idle");
    setResult(null);
    setError("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  const recommendation = result?.recommendation;
  const nearbyTips = result?.nearbyTips;

  return (
    <section className="tips-panel" aria-labelledby="tips-title">
      <header className="tips-heading">
        <div>
          <span className="tips-kicker">Personalized nearby ideas</span>
          <h2 id="tips-title">What would feel good today?</h2>
          <p>Suggestions are centered around <strong>{startLocation}</strong>, your trip start.</p>
        </div>
        <label className="tips-day-select">
          <span>Plan for</span>
          <select value={selectedDay} onChange={(event) => setSelectedDay(Number(event.target.value))}>
            {days.map((day) => <option key={day} value={day}>Day {day}</option>)}
          </select>
        </label>
      </header>

      {!sessionReady && (
        <div className="mood-checkin-unavailable" role="status">
          <p className="mood-checkin-unavailable-title">Tips are temporarily unavailable</p>
          <p>This trip has not been saved to a session. Generate a new saved plan to attach mood check-ins safely.</p>
        </div>
      )}

      {sessionReady && status !== "success" && (
        <>
          <div className="tips-input-tabs" role="tablist" aria-label="Mood input method">
            <button type="button" className={inputMode === "photo" ? "active" : ""} onClick={() => setInputMode("photo")}>Use a photo</button>
            <button type="button" className={inputMode === "manual" ? "active" : ""} onClick={() => setInputMode("manual")}>Choose a mood</button>
          </div>

          {inputMode === "photo" ? (
            <div className="tips-photo-panel">
              <div className="tips-photo-icon" aria-hidden="true">⌁</div>
              <div>
                <h3>Quick mood check</h3>
                <p>Your photo is analyzed by the deployed emotion model and is never stored.</p>
              </div>
              <input ref={fileInputRef} type="file" accept="image/*" capture="user" onChange={handlePhotoSelect} hidden />
              <button type="button" className="tips-primary-button" onClick={() => fileInputRef.current?.click()} disabled={status === "loading"}>
                Take or choose photo
              </button>
            </div>
          ) : (
            <div className="emotion-grid" aria-label="Choose your current mood">
              {EMOTIONS.map((emotion) => (
                <button
                  type="button"
                  key={emotion.id}
                  className={selectedEmotion === emotion.id ? "selected" : ""}
                  onClick={() => setSelectedEmotion(emotion.id)}
                  aria-pressed={selectedEmotion === emotion.id}
                >
                  <span>{emotion.emoji}</span>
                  <small>{emotion.label}</small>
                </button>
              ))}
            </div>
          )}

          <div className="tips-hobbies">
            <div className="tips-section-label">What are you into?</div>
            <div className="hobby-chips">
              {HOBBIES.map((hobby) => (
                <button type="button" key={hobby} className={selectedHobbies.includes(hobby) ? "selected" : ""} onClick={() => toggleHobby(hobby)} aria-pressed={selectedHobbies.includes(hobby)}>
                  {hobby}
                </button>
              ))}
            </div>
          </div>

          {inputMode === "manual" && (
            <button type="button" className="tips-primary-button tips-submit" onClick={submitManualEmotion} disabled={status === "loading"}>
              Find ideas near {startLocation}
            </button>
          )}
        </>
      )}

      {status === "loading" && (
        <div className="mood-checkin-loading" role="status">
          <div className="spinner" />
          <p>Reading the day ahead and finding nearby matches…</p>
        </div>
      )}

      {status === "error" && (
        <div className="mood-checkin-error" role="alert">
          <p>{error}</p>
          <button type="button" className="btn-secondary" onClick={reset}>Try again</button>
        </div>
      )}

      {status === "success" && recommendation && (
        <div className="tips-results">
          <div className="tips-result-hero">
            <div className="mood-badge">
              <span className="mood-icon">{emotionEmoji(recommendation.current_emotion)}</span>
              <span className="mood-label">
                {titleCase(recommendation.current_emotion)}
                {result?.checkin?.model_version !== "manual_user_selection" && ` · ${Math.round((recommendation.confidence || 0) * 100)}%`}
              </span>
            </div>
            <span className={`mood-risk-badge risk-${recommendation.risk_level}`}>{titleCase(recommendation.risk_level)} risk</span>
            <h3>{recommendation.summary}</h3>
            <p>{recommendation.day_ahead_prediction}</p>
          </div>

          <div className="tips-advice-grid">
            <article><span>Recommended plan</span><p>{recommendation.recommendation}</p></article>
            <article><span>Best timing</span><p>{recommendation.timing_adjustment}</p></article>
            <article><span>Comfort actions</span><p>{(recommendation.comfort_actions || []).join(" · ") || "Keep a comfortable pace."}</p></article>
            <article><span>Fallback</span><p>{recommendation.fallback_plan}</p></article>
          </div>

          <div className="nearby-tips-section">
            <div className="nearby-tips-heading">
              <div>
                <span className="tips-kicker">OpenStreetMap matches</span>
                <h3>Nearby around {nearbyTips?.location?.name || startLocation}</h3>
              </div>
              <span>{nearbyTips?.recommendations?.length || 0} places</span>
            </div>
            {nearbyTips?.summary && <p className="nearby-summary">{nearbyTips.summary}</p>}
            {nearbyTips?.status === "available" && nearbyTips.recommendations?.length > 0 ? (
              <div className="nearby-tip-list">
                {nearbyTips.recommendations.map((place, index) => (
                  <a className="nearby-tip-card" href={place.map_url} target="_blank" rel="noreferrer" key={`${place.name}-${index}`}>
                    <span className="nearby-tip-index">{index + 1}</span>
                    <span className="nearby-tip-copy">
                      <strong>{place.name}</strong>
                      <small>{place.category} · {place.distance_km} km</small>
                      <p>{place.reason}</p>
                    </span>
                    <span className="nearby-tip-arrow" aria-hidden="true">↗</span>
                  </a>
                ))}
              </div>
            ) : (
              <div className="nearby-unavailable">{nearbyTips?.message || "No nearby matches were found this time."}</div>
            )}
          </div>

          <button type="button" className="tips-reset-button" onClick={reset}>Try another mood</button>
        </div>
      )}
    </section>
  );
}

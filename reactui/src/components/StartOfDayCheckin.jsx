import { useRef, useState } from "react";
import { startOfDayMoodCheckinApi, startOfDayMoodCheckinImageApi } from "../api";

const EMOTIONS = [
  { id: "happy", emoji: "😊", label: "Happy" },
  { id: "surprise", emoji: "😲", label: "Surprise" },
  { id: "neutral", emoji: "😐", label: "Neutral" },
  { id: "sad", emoji: "😢", label: "Sad" },
  { id: "anger", emoji: "😠", label: "Anger" },
];

const HOBBIES = [
  { id: "Nature", icon: "🌿", label: "Nature" },
  { id: "Culture", icon: "🏛️", label: "Culture" },
  { id: "Food", icon: "🍜", label: "Food" },
  { id: "Photography", icon: "📸", label: "Photography" },
  { id: "Sports", icon: "⚽", label: "Sports" },
  { id: "Wellness", icon: "🧘", label: "Wellness" },
  { id: "Arts", icon: "🎨", label: "Arts" },
  { id: "Shopping", icon: "🛍️", label: "Shopping" },
];

function emotionEmoji(value) {
  return EMOTIONS.find((item) => item.id === value)?.emoji || "😐";
}

function titleCase(value) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : "Mood";
}

export default function StartOfDayCheckin({ plan, session }) {
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
    setResult({ recommendation: response.recommendation, nearbyTips: response.nearby_tips, checkin: response.checkin });
    setStatus("success");
  }

  function beginRequest() {
    setStatus("loading");
    setError("");
    setResult(null);
  }

  async function handlePhotoSelect(event) {
    const file = event.target.files?.[0];
    if (!file || !sessionReady) return;
    beginRequest();
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
    beginRequest();
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
  const resultEmotion = recommendation?.current_emotion || selectedEmotion;

  return (
    <section className="tips-panel" aria-labelledby="tips-title">
      <header className="tips-heading">
        <div>
          <span className="tips-kicker">Personalized activity finder</span>
          <h2 id="tips-title">Tips for your day</h2>
          <p>Recommendations start near <strong>{startLocation}</strong>, your trip’s starting point.</p>
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

      {sessionReady && status === "idle" && (
        <div className="tips-preferences">
          <section className="tips-choice-section">
            <div className="tips-choice-heading">
              <h3>Your interests <small>(select all that apply)</small></h3>
            </div>
            <div className="interest-grid">
              {HOBBIES.map((hobby) => (
                <button
                  type="button"
                  key={hobby.id}
                  className={selectedHobbies.includes(hobby.id) ? "selected" : ""}
                  onClick={() => toggleHobby(hobby.id)}
                  aria-pressed={selectedHobbies.includes(hobby.id)}
                >
                  <span>{hobby.icon}</span>
                  <small>{hobby.label}</small>
                </button>
              ))}
            </div>
          </section>

          <section className="tips-choice-section mood-choice-section">
            <div className="tips-choice-heading mood-heading-row">
              <h3>How are you feeling?</h3>
              <button type="button" className="photo-mood-button" onClick={() => fileInputRef.current?.click()}>
                <span aria-hidden="true">📷</span> Check with photo
              </button>
            </div>
            <input ref={fileInputRef} type="file" accept="image/*" capture="user" onChange={handlePhotoSelect} hidden />
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
          </section>

          <button type="button" className="tips-primary-button tips-submit" onClick={submitManualEmotion}>
            Get smart picks
            <span aria-hidden="true">→</span>
          </button>
          <p className="tips-privacy-note">Photos are analyzed securely for emotion only and are never stored.</p>
        </div>
      )}

      {status === "loading" && (
        <div className="mood-checkin-loading" role="status">
          <div className="spinner" />
          <p>Matching your mood, interests, and nearby places…</p>
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
          <section className="smart-picks-banner">
            <span className="smart-picks-emoji">{emotionEmoji(resultEmotion)}</span>
            <div>
              <h3>{nearbyTips?.headline || "Smart Picks For You"}</h3>
              <p>Based on your {titleCase(resultEmotion).toLowerCase()} mood{nearbyTips?.hobbies?.length ? ` and ${nearbyTips.hobbies.join(", ")}` : ""}</p>
            </div>
            <span className={`mood-risk-badge risk-${recommendation.risk_level}`}>{titleCase(recommendation.risk_level)} risk</span>
          </section>

          {nearbyTips?.status === "available" && nearbyTips.recommendations?.length > 0 ? (
            <div className="smart-pick-list">
              {nearbyTips.recommendations.map((place, index) => (
                <article className={`smart-pick-card${place.top_pick ? " top-pick" : ""}`} key={`${place.name}-${index}`}>
                  <div className="smart-pick-card-top">
                    <span className="smart-pick-label">💚 {place.recommendation_label || "Good Pick"}</span>
                    {place.top_pick && <span className="top-pick-label">🏆 Top Pick</span>}
                  </div>
                  <div className="smart-pick-title-row">
                    <span className="smart-pick-icon" aria-hidden="true">{place.icon || "✨"}</span>
                    <div>
                      <h4>{place.name}</h4>
                      <div className="smart-pick-meta">
                        <span>{place.activity_type || place.category}</span>
                        <span>◷ {place.duration || "1–2 hrs"}</span>
                        <span>⌖ {place.distance_km} km</span>
                        {place.hobby_matches?.length > 0 && (
                          <span className="interest-match-chip">Matches {place.hobby_matches.join(" + ")}</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <p className="smart-pick-description">{place.description || place.reason}</p>
                  <div className="smart-pick-why">
                    <span>Why this is for you</span>
                    <p>{place.why_for_you || place.reason}</p>
                  </div>
                  <footer className="smart-pick-footer">
                    <span>◷ Best time: {place.best_time || "Flexible"}</span>
                    {place.solo_friendly && <span>♙ Solo friendly</span>}
                    <a href={place.map_url} target="_blank" rel="noreferrer">Open map ↗</a>
                  </footer>
                </article>
              ))}
            </div>
          ) : (
            <div className="nearby-unavailable">{nearbyTips?.message || "No nearby matches were found this time."}</div>
          )}

          <details className="trip-readiness-details">
            <summary>See today’s travel-readiness advice</summary>
            <div className="trip-readiness-content">
              <h4>{recommendation.summary}</h4>
              <p>{recommendation.day_ahead_prediction}</p>
              <dl>
                <div><dt>Recommended plan</dt><dd>{recommendation.recommendation}</dd></div>
                <div><dt>Best timing</dt><dd>{recommendation.timing_adjustment}</dd></div>
                <div><dt>Comfort</dt><dd>{(recommendation.comfort_actions || []).join(" · ") || "Keep a comfortable pace."}</dd></div>
                <div><dt>Fallback</dt><dd>{recommendation.fallback_plan}</dd></div>
              </dl>
            </div>
          </details>

          <button type="button" className="tips-reset-button" onClick={reset}>Update mood or interests</button>
        </div>
      )}
    </section>
  );
}

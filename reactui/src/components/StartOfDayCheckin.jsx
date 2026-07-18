import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  emotionCheckinApi,
  emotionTargetsApi,
  startOfDayMoodCheckinImageApi,
} from "../api";
import useRepeatingDemoTask from "../hooks/useRepeatingDemoTask";
import MoodJourneyMap from "./MoodJourneyMap";

const EMOTIONS = [
  { id: "happy", emoji: "😊", label: "Happy", score: 90 },
  { id: "surprise", emoji: "😲", label: "Surprise", score: 70 },
  { id: "neutral", emoji: "😐", label: "Neutral", score: 50 },
  { id: "sad", emoji: "😢", label: "Sad", score: 30 },
  { id: "anger", emoji: "😠", label: "Anger", score: 15 },
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

function emotionScore(value) {
  return EMOTIONS.find((item) => item.id === value)?.score ?? 50;
}

function titleCase(value) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : "Mood";
}

function checkinMatchesTarget(checkin, target) {
  if (!checkin || !target) return false;
  if (checkin.attraction_id && target.attraction_id) {
    return String(checkin.attraction_id) === String(target.attraction_id);
  }
  return String(checkin.attraction_name || "").trim().toLowerCase()
    === String(target.attraction_name || "").trim().toLowerCase();
}

function MoodRecoveryGraph({ checkins }) {
  const points = checkins.map((checkin, index) => ({
    x: checkins.length === 1 ? 50 : 8 + (index / (checkins.length - 1)) * 84,
    y: 88 - emotionScore(checkin.emotion_label) * 0.72,
  }));
  const polyline = points.map((point) => `${point.x},${point.y}`).join(" ");
  const first = checkins[0];
  const latest = checkins[checkins.length - 1];
  const change = first && latest ? emotionScore(latest.emotion_label) - emotionScore(first.emotion_label) : 0;

  return (
    <section className="mood-recovery-card" aria-labelledby="mood-recovery-title">
      <div className="mood-recovery-heading">
        <div>
          <span>Demo wellbeing trend</span>
          <h3 id="mood-recovery-title">Mood history</h3>
        </div>
        <strong className={change > 0 ? "improved" : change < 0 ? "declined" : "steady"}>
          {checkins.length < 2 ? "First check-in" : change > 0 ? `+${change} recovery` : change < 0 ? `${change} change` : "Steady"}
        </strong>
      </div>
      {checkins.length ? (
        <>
          <svg viewBox="0 0 100 100" role="img" aria-label="Mood check-in trend">
            <defs>
              <linearGradient id="moodTrend" x1="0" x2="1">
                <stop offset="0" stopColor="#50e3b3" />
                <stop offset="1" stopColor="#b9ef73" />
              </linearGradient>
            </defs>
            {[20, 50, 80].map((y) => <line key={y} x1="5" y1={y} x2="95" y2={y} className="mood-graph-grid" />)}
            {points.length > 1 && <polyline points={polyline} className="mood-graph-line" />}
            {points.map((point, index) => (
              <g key={`${checkins[index].checkin_id || index}-${point.x}`}>
                <circle cx={point.x} cy={point.y} r="4" className="mood-graph-point" />
                <text x={point.x} y={point.y - 8} textAnchor="middle">{emotionEmoji(checkins[index].emotion_label)}</text>
              </g>
            ))}
          </svg>
          <div className="mood-history-list">
            {checkins.slice(-5).map((checkin) => (
              <span key={checkin.checkin_id || checkin.timestamp}>
                {emotionEmoji(checkin.emotion_label)} {checkin.attraction_name || `Day ${checkin.day || "?"}`}
              </span>
            ))}
          </div>
        </>
      ) : <p className="mood-history-empty">Your first checkpoint will appear here after you submit a mood.</p>}
      <small>This visual is a travel wellbeing aid, not a medical assessment.</small>
    </section>
  );
}

export default function StartOfDayCheckin({ plan, session }) {
  const [selectedEmotion, setSelectedEmotion] = useState("happy");
  const [selectedHobbies, setSelectedHobbies] = useState([]);
  const [journey, setJourney] = useState({ targets: [], emotion_checkins: [], emotion_summary: {} });
  const [activeIndex, setActiveIndex] = useState(0);
  const [journeyStatus, setJourneyStatus] = useState("loading");
  const [status, setStatus] = useState("idle");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [autoMoodPrompt, setAutoMoodPrompt] = useState(false);
  const [promptSequence, setPromptSequence] = useState(0);
  const fileInputRef = useRef(null);
  const preferencesRef = useRef(null);
  const statusRef = useRef(status);

  const sessionId = session?.session_id || plan?.session_id || plan?.session_storage?.session_id;
  const storageState = plan?.session_storage || plan?.plan_overview?.session_storage;
  const sessionReady = Boolean(sessionId) && storageState?.saved !== false;
  const targets = journey.targets || [];
  const history = useMemo(
    () => [...(journey.emotion_checkins || [])]
      .filter((checkin) => checkin?.checkin_type === "attraction" || checkin?.attraction_name)
      .sort((left, right) => new Date(left.timestamp || 0) - new Date(right.timestamp || 0)),
    [journey.emotion_checkins],
  );
  const activeTarget = targets[activeIndex] || null;

  useEffect(() => { statusRef.current = status; }, [status]);

  useEffect(() => {
    if (!sessionReady) {
      setJourneyStatus("unavailable");
      return undefined;
    }
    let cancelled = false;
    setJourneyStatus("loading");
    emotionTargetsApi(sessionId)
      .then((payload) => {
        if (cancelled) return;
        const orderedTargets = [...(payload.targets || [])].sort((a, b) => (a.day - b.day) || (a.order - b.order));
        const savedCheckins = payload.emotion_checkins || [];
        setJourney({ ...payload, targets: orderedTargets, emotion_checkins: savedCheckins });
        const firstUnchecked = orderedTargets.findIndex(
          (target) => !savedCheckins.some((checkin) => checkinMatchesTarget(checkin, target)),
        );
        setActiveIndex(firstUnchecked >= 0 ? firstUnchecked : Math.max(orderedTargets.length - 1, 0));
        setJourneyStatus("ready");
      })
      .catch(() => !cancelled && setJourneyStatus("error"));
    return () => { cancelled = true; };
  }, [sessionId, sessionReady]);

  function toggleHobby(hobby) {
    setSelectedHobbies((current) => current.includes(hobby)
      ? current.filter((item) => item !== hobby)
      : [...current, hobby]);
  }

  function beginRequest() {
    statusRef.current = "loading";
    setStatus("loading");
    setError("");
    setResult(null);
  }

  function storeResponse(response) {
    setResult({ recommendation: response.recommendation, nearbyTips: response.nearby_tips, checkin: response.checkin });
    setJourney((current) => ({
      ...current,
      emotion_checkins: [...(current.emotion_checkins || []), response.checkin],
      emotion_summary: response.emotion_summary || current.emotion_summary,
    }));
    statusRef.current = "success";
    setStatus("success");
  }

  function targetPayload() {
    return {
      checkin_type: "attraction",
      attraction_id: activeTarget?.attraction_id,
      attraction_name: activeTarget?.attraction_name,
      day: activeTarget?.day,
      user_location: {
        latitude: activeTarget?.latitude,
        longitude: activeTarget?.longitude,
        accuracy_meters: 0,
      },
    };
  }

  async function handlePhotoSelect(event) {
    const file = event.target.files?.[0];
    if (!file || !sessionReady || !activeTarget) return;
    beginRequest();
    const formData = new FormData();
    formData.append("image", file);
    formData.append("day", activeTarget.day);
    formData.append("checkin_type", "attraction");
    formData.append("attraction_id", activeTarget.attraction_id || "");
    formData.append("attraction_name", activeTarget.attraction_name || "");
    if (activeTarget.latitude != null) formData.append("latitude", activeTarget.latitude);
    if (activeTarget.longitude != null) formData.append("longitude", activeTarget.longitude);
    formData.append("hobbies", JSON.stringify(selectedHobbies));
    try {
      storeResponse(await startOfDayMoodCheckinImageApi(sessionId, formData));
    } catch (requestError) {
      const message = String(requestError?.message || "");
      setError(message.toLowerCase().includes("face")
        ? "I couldn’t find a face clearly. Try a brighter, front-facing photo."
        : "The mood check could not be completed. Please try again.");
      statusRef.current = "error";
      setStatus("error");
    }
  }

  async function submitManualEmotion() {
    if (!sessionReady || !activeTarget) return;
    beginRequest();
    try {
      storeResponse(await emotionCheckinApi(sessionId, {
        ...targetPayload(),
        emotion_label: selectedEmotion,
        emotion_confidence: 1,
        top_predictions: [{ class_name: selectedEmotion, probability: 1 }],
        model_version: "manual_user_selection",
        local_inference: false,
        hobbies: selectedHobbies,
      }));
    } catch {
      setError("The mood check could not be completed. Please try again.");
      statusRef.current = "error";
      setStatus("error");
    }
  }

  const resetForm = useCallback(() => {
    statusRef.current = "idle";
    setStatus("idle");
    setResult(null);
    setError("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  function selectCheckpoint(index) {
    setActiveIndex(Math.min(Math.max(index, 0), Math.max(targets.length - 1, 0)));
    resetForm();
  }

  const requestMoodInput = useCallback(() => {
    if (statusRef.current === "loading") return;
    resetForm();
    setPromptSequence((current) => current + 1);
    window.requestAnimationFrame(() => preferencesRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
  }, [resetForm]);

  const moodPromptCountdown = useRepeatingDemoTask({
    enabled: autoMoodPrompt && sessionReady && Boolean(activeTarget),
    onTick: requestMoodInput,
    runImmediately: false,
  });

  const recommendation = result?.recommendation;
  const nearbyTips = result?.nearbyTips;
  const resultEmotion = recommendation?.current_emotion || selectedEmotion;
  const hasNextCheckpoint = activeIndex < targets.length - 1;

  return (
    <section className="tips-panel mood-journey-panel" aria-labelledby="tips-title">
      <header className="tips-heading mood-journey-heading">
        <div>
          <span className="tips-kicker">Simulated attraction check-ins</span>
          <h2 id="tips-title">Mood journey</h2>
          <p>Move through the planned attractions to demonstrate mood-aware recommendations without GPS.</p>
        </div>
        <button
          type="button"
          className={`tips-demo-toggle${autoMoodPrompt ? " active" : ""}`}
          onClick={() => setAutoMoodPrompt((current) => !current)}
          disabled={!sessionReady || !activeTarget}
          aria-pressed={autoMoodPrompt}
        >
          <span className="tips-demo-toggle-dot" aria-hidden="true" />
          {autoMoodPrompt ? `Prompt in ${moodPromptCountdown}s` : "30-sec demo prompts"}
        </button>
      </header>

      {!sessionReady && (
        <div className="mood-checkin-unavailable" role="status">
          <p className="mood-checkin-unavailable-title">Mood journey is temporarily unavailable</p>
          <p>This trip must be saved before checkpoint results can be attached safely.</p>
        </div>
      )}

      {sessionReady && journeyStatus === "loading" && <div className="mood-checkin-loading"><div className="spinner" /><p>Loading planned checkpoints…</p></div>}
      {sessionReady && journeyStatus === "error" && <div className="mood-checkin-error">The planned checkpoint list could not be loaded.</div>}
      {sessionReady && journeyStatus === "ready" && !targets.length && <div className="mood-checkin-unavailable">No planned attractions with coordinates were found.</div>}

      {sessionReady && journeyStatus === "ready" && targets.length > 0 && (
        <>
          <div className="mood-journey-overview">
            <MoodJourneyMap targets={targets} activeIndex={activeIndex} checkins={history} emotionEmoji={emotionEmoji} />
            <MoodRecoveryGraph checkins={history} />
          </div>

          <nav className="mood-checkpoint-nav" aria-label="Simulated attraction checkpoint">
            <button type="button" onClick={() => selectCheckpoint(activeIndex - 1)} disabled={activeIndex === 0}>← Previous</button>
            <label>
              <span>Current checkpoint</span>
              <select value={activeIndex} onChange={(event) => selectCheckpoint(Number(event.target.value))}>
                {targets.map((target, index) => (
                  <option value={index} key={target.attraction_id || `${target.day}-${target.order}`}>
                    Day {target.day} · {target.attraction_name}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" onClick={() => selectCheckpoint(activeIndex + 1)} disabled={!hasNextCheckpoint}>Next →</button>
          </nav>

          <section className="mood-current-stop">
            <span>Day {activeTarget.day} · Stop {activeTarget.order}</span>
            <h3>{activeTarget.attraction_name}</h3>
            <p>{activeTarget.district || activeTarget.category || "Planned attraction"}</p>
          </section>
        </>
      )}

      {sessionReady && activeTarget && status === "idle" && (
        <div className="tips-preferences" ref={preferencesRef}>
          {autoMoodPrompt && promptSequence > 0 && (
            <div className="tips-demo-prompt" key={promptSequence} role="status">
              <span aria-hidden="true">📍</span>
              <div><strong>Mood check at {activeTarget.attraction_name}</strong><small>Choose an emotion or photo. Nothing is submitted automatically.</small></div>
            </div>
          )}
          <section className="tips-choice-section">
            <div className="tips-choice-heading"><h3>Your interests <small>(select all that apply)</small></h3></div>
            <div className="interest-grid">
              {HOBBIES.map((hobby) => (
                <button type="button" key={hobby.id} className={selectedHobbies.includes(hobby.id) ? "selected" : ""} onClick={() => toggleHobby(hobby.id)} aria-pressed={selectedHobbies.includes(hobby.id)}>
                  <span>{hobby.icon}</span><small>{hobby.label}</small>
                </button>
              ))}
            </div>
          </section>
          <section className="tips-choice-section mood-choice-section">
            <div className="tips-choice-heading mood-heading-row">
              <h3>How are you feeling here?</h3>
              <button type="button" className="photo-mood-button" onClick={() => fileInputRef.current?.click()}><span aria-hidden="true">📷</span> Check with photo</button>
            </div>
            <input ref={fileInputRef} type="file" accept="image/*" capture="user" onChange={handlePhotoSelect} hidden />
            <div className="emotion-grid" aria-label="Choose your current mood">
              {EMOTIONS.map((emotion) => (
                <button type="button" key={emotion.id} className={selectedEmotion === emotion.id ? "selected" : ""} onClick={() => setSelectedEmotion(emotion.id)} aria-pressed={selectedEmotion === emotion.id}>
                  <span>{emotion.emoji}</span><small>{emotion.label}</small>
                </button>
              ))}
            </div>
          </section>
          <button type="button" className="tips-primary-button tips-submit" onClick={submitManualEmotion}>Get smart picks for this stop <span aria-hidden="true">→</span></button>
          <p className="tips-privacy-note">Photos are analyzed for emotion only and are never stored.</p>
        </div>
      )}

      {status === "loading" && <div className="mood-checkin-loading" role="status"><div className="spinner" /><p>Matching this checkpoint, your mood, and nearby places…</p></div>}
      {status === "error" && <div className="mood-checkin-error" role="alert"><p>{error}</p><button type="button" className="btn-secondary" onClick={resetForm}>Try again</button></div>}

      {status === "success" && recommendation && (
        <div className="tips-results">
          <section className="smart-picks-banner">
            <span className="smart-picks-emoji">{emotionEmoji(resultEmotion)}</span>
            <div><h3>{nearbyTips?.headline || "Smart Picks For You"}</h3><p>Near {nearbyTips?.location?.name || activeTarget.attraction_name}, based on your {titleCase(resultEmotion).toLowerCase()} mood{nearbyTips?.hobbies?.length ? ` and ${nearbyTips.hobbies.join(", ")}` : ""}</p></div>
            <span className={`mood-risk-badge risk-${recommendation.risk_level}`}>{titleCase(recommendation.risk_level)} risk</span>
          </section>
          {nearbyTips?.status === "available" && nearbyTips.recommendations?.length > 0 ? (
            <div className="smart-pick-list">
              {nearbyTips.recommendations.map((place, index) => (
                <article className={`smart-pick-card${place.top_pick ? " top-pick" : ""}`} key={`${place.name}-${index}`}>
                  <div className="smart-pick-card-top"><span className="smart-pick-label">💚 {place.recommendation_label || "Good Pick"}</span>{place.top_pick && <span className="top-pick-label">🏆 Top Pick</span>}</div>
                  <div className="smart-pick-title-row"><span className="smart-pick-icon" aria-hidden="true">{place.icon || "✨"}</span><div><h4>{place.name}</h4><div className="smart-pick-meta"><span>{place.activity_type || place.category}</span><span>◷ {place.duration || "1–2 hrs"}</span><span>⌖ {place.distance_km} km</span>{place.hobby_matches?.length > 0 && <span className="interest-match-chip">Matches {place.hobby_matches.join(" + ")}</span>}</div></div></div>
                  <p className="smart-pick-description">{place.description || place.reason}</p>
                  <div className="smart-pick-why"><span>Why this is for you</span><p>{place.why_for_you || place.reason}</p></div>
                  <footer className="smart-pick-footer"><span>◷ Best time: {place.best_time || "Flexible"}</span>{place.solo_friendly && <span>♙ Solo friendly</span>}<a href={place.map_url} target="_blank" rel="noreferrer">Open map ↗</a></footer>
                </article>
              ))}
            </div>
          ) : <div className="nearby-unavailable">{nearbyTips?.message || "No nearby matches were found this time."}</div>}
          <details className="trip-readiness-details"><summary>See travel-readiness advice</summary><div className="trip-readiness-content"><h4>{recommendation.summary}</h4><p>{recommendation.day_ahead_prediction}</p><dl><div><dt>Recommended plan</dt><dd>{recommendation.recommendation}</dd></div><div><dt>Best timing</dt><dd>{recommendation.timing_adjustment}</dd></div><div><dt>Comfort</dt><dd>{(recommendation.comfort_actions || []).join(" · ") || "Keep a comfortable pace."}</dd></div><div><dt>Fallback</dt><dd>{recommendation.fallback_plan}</dd></div></dl></div></details>
          <div className="mood-result-actions">
            <button type="button" className="tips-reset-button" onClick={resetForm}>Update this check-in</button>
            {hasNextCheckpoint && <button type="button" className="tips-primary-button" onClick={() => selectCheckpoint(activeIndex + 1)}>Continue to next stop →</button>}
          </div>
        </div>
      )}
    </section>
  );
}

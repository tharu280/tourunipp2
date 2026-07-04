import { useState, useRef } from 'react';
import { startOfDayMoodCheckinApi } from '../api';
import { mockClassifyEmotion } from '../emotion/mockEmotionClassifier';

function IconCamera() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="20" height="20">
      <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  );
}

function IconCheck() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="18" height="18">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

export default function StartOfDayCheckin({ plan, session }) {
  const [selectedDay, setSelectedDay] = useState(1);
  const [status, setStatus] = useState("idle"); // idle, loading, success, error
  const [result, setResult] = useState(null);
  const fileInputRef = useRef(null);

  const sessionId = session?.session_id || plan?.session_id || plan?.session_storage?.session_id;
  const tripDates = plan?.trip_dates || plan?.plan_overview?.trip_dates || [];
  const totalDays = tripDates.length || plan?.plan_overview?.trip_days || plan?.trip_requirements?.duration_days || 1;
  const daysArray = Array.from({ length: totalDays }, (_, i) => i + 1);

  if (!sessionId) return null;

  const handlePhotoSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setStatus("loading");
    setResult(null);

    try {
      // 1. Local mock classification
      const classification = await mockClassifyEmotion(file);
      
      // 2. Call backend API
      const response = await startOfDayMoodCheckinApi(sessionId, {
        day: selectedDay,
        ...classification,
        model_version: "rafdb5_local_tflite",
        local_inference: true
      });

      setResult(response.recommendation);
      setStatus("success");
    } catch (err) {
      console.error("Mood check failed:", err);
      setStatus("error");
    }
  };

  const resetState = () => {
    setStatus("idle");
    setResult(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <section className="d-card mood-checkin-card">
      <div className="d-card-header">
        <h2 className="d-card-title">Start-of-day mood check</h2>
      </div>
      <div className="d-card-body" style={{ padding: "16px 20px 20px" }}>
        
        {status === "idle" && (
          <div className="mood-checkin-idle">
            <p className="mood-checkin-desc">
              Use a quick photo to personalize today’s advice.
            </p>
            <div className="mood-checkin-controls">
              <div className="mood-day-select">
                <label htmlFor="mood-day">For:</label>
                <select 
                  id="mood-day" 
                  value={selectedDay} 
                  onChange={(e) => setSelectedDay(Number(e.target.value))}
                >
                  {daysArray.map(d => (
                    <option key={d} value={d}>Day {d}</option>
                  ))}
                </select>
              </div>
              <input 
                type="file" 
                accept="image/*" 
                ref={fileInputRef} 
                onChange={handlePhotoSelect} 
                style={{ display: "none" }} 
              />
              <button 
                className="btn-primary mood-upload-btn"
                onClick={() => fileInputRef.current?.click()}
              >
                <IconCamera /> Take / choose photo
              </button>
            </div>
            <p className="mood-checkin-privacy">
              Your photo stays on this device. Only the mood result is saved.
            </p>
          </div>
        )}

        {status === "loading" && (
          <div className="mood-checkin-loading">
            <div className="spinner"></div>
            <p>Reading your mood and checking the day ahead…</p>
          </div>
        )}

        {status === "error" && (
          <div className="mood-checkin-error">
            <p>Mood check failed. Please try again.</p>
            <button className="btn-secondary" onClick={resetState}>Retry</button>
          </div>
        )}

        {status === "success" && result && (
          <div className="mood-checkin-result">
            <div className="mood-result-header">
              <div className="mood-badge">
                <span className="mood-icon">
                  {result.current_emotion === "happy" ? "😊" : 
                   result.current_emotion === "neutral" ? "😐" : 
                   result.current_emotion === "sad" ? "😔" : 
                   result.current_emotion === "surprise" ? "😲" : "😐"}
                </span>
                <span className="mood-label">
                  {result.current_emotion?.charAt(0).toUpperCase() + result.current_emotion?.slice(1)} ({(result.confidence * 100).toFixed(0)}%)
                </span>
              </div>
              <div className={`mood-risk-badge risk-${result.risk_level}`}>
                {result.risk_level?.toUpperCase()} RISK
              </div>
            </div>

            <p className="mood-day-ahead">
              <strong>Day Ahead:</strong> {result.day_ahead_prediction}
            </p>
            
            <div className="mood-recommendation">
              <strong>Recommendation:</strong> {result.recommendation}
            </div>

            <button className="btn-secondary mt-3" onClick={resetState}>Check another day</button>
          </div>
        )}
      </div>
    </section>
  );
}

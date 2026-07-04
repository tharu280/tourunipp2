import { useState, useRef } from 'react';
import { startOfDayMoodCheckinImageApi } from '../api';

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
      const formData = new FormData();
      formData.append("image", file);
      formData.append("day", selectedDay);
      // checkin_type is handled by the api helper or server default

      const response = await startOfDayMoodCheckinImageApi(sessionId, formData);
      setResult(response.recommendation);
      setStatus("success");
    } catch (err) {
      console.error("Mood check failed:", err);
      // specific error if no face is detected
      if (err.message && err.message.toLowerCase().includes("face")) {
        setResult("I couldn’t find a face clearly. Try a brighter front-facing photo.");
      } else {
        setResult("Mood check failed. Please try again.");
      }
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
        <h2 className="d-card-title">Today's travel readiness</h2>
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
              Photo is sent securely to the backend for emotion inference and is not stored. Only the emotion result is saved.
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
            <p>{result || "Mood check failed. Please try again."}</p>
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
                   result.current_emotion === "surprise" ? "😲" :
                   result.current_emotion === "anger" ? "😠" : "😐"}
                </span>
                <span className="mood-label">
                  {result.current_emotion?.charAt(0).toUpperCase() + result.current_emotion?.slice(1)} ({(result.confidence * 100).toFixed(0)}%)
                </span>
              </div>
              <div className={`mood-risk-badge risk-${result.risk_level}`}>
                {result.risk_level?.toUpperCase()} RISK
              </div>
            </div>

            <div className="mood-day-ahead" style={{ marginTop: "1rem" }}>
              <div style={{ fontWeight: 600, fontSize: "16px", marginBottom: "4px" }}>
                {result.summary || "Day ahead"}
              </div>
              <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "14px" }}>
                {result.day_ahead_prediction}
              </p>
            </div>
            
            <div className="mood-recommendation" style={{ marginTop: "1rem", backgroundColor: "var(--bg-secondary)", padding: "1rem", borderRadius: "12px" }}>
              <div style={{ fontWeight: 600, fontSize: "14px", marginBottom: "8px" }}>Recommended Plan</div>
              <p style={{ margin: 0, fontSize: "14px" }}>{result.recommendation}</p>
            </div>

            <div className="mood-chips-container" style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "1rem" }}>
              {result.timing_adjustment && (
                <div className="mood-chip" style={{ display: "flex", gap: "12px", alignItems: "flex-start", backgroundColor: "var(--bg-tertiary)", padding: "10px", borderRadius: "8px" }}>
                  <span style={{ fontSize: "18px" }}>⏱️</span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "12px", textTransform: "uppercase", color: "var(--text-tertiary)" }}>Timing</div>
                    <div style={{ fontSize: "14px" }}>{result.timing_adjustment}</div>
                  </div>
                </div>
              )}
              {result.watch_out_for && result.watch_out_for.length > 0 && (
                <div className="mood-chip" style={{ display: "flex", gap: "12px", alignItems: "flex-start", backgroundColor: "var(--bg-tertiary)", padding: "10px", borderRadius: "8px" }}>
                  <span style={{ fontSize: "18px" }}>⚠️</span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "12px", textTransform: "uppercase", color: "var(--text-tertiary)" }}>Watch out for</div>
                    <div style={{ fontSize: "14px" }}>
                      <ul style={{ margin: 0, paddingLeft: "16px" }}>
                        {result.watch_out_for.map((item, idx) => (
                          <li key={idx}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )}
              {result.comfort_actions && result.comfort_actions.length > 0 && (
                <div className="mood-chip" style={{ display: "flex", gap: "12px", alignItems: "flex-start", backgroundColor: "var(--bg-tertiary)", padding: "10px", borderRadius: "8px" }}>
                  <span style={{ fontSize: "18px" }}>🧘‍♂️</span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "12px", textTransform: "uppercase", color: "var(--text-tertiary)" }}>Comfort Actions</div>
                    <div style={{ fontSize: "14px" }}>
                      <ul style={{ margin: 0, paddingLeft: "16px" }}>
                        {result.comfort_actions.map((item, idx) => (
                          <li key={idx}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )}
              {result.fallback_plan && (
                <div className="mood-chip" style={{ display: "flex", gap: "12px", alignItems: "flex-start", backgroundColor: "var(--bg-tertiary)", padding: "10px", borderRadius: "8px" }}>
                  <span style={{ fontSize: "18px" }}>🔄</span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "12px", textTransform: "uppercase", color: "var(--text-tertiary)" }}>Fallback Plan</div>
                    <div style={{ fontSize: "14px" }}>{result.fallback_plan}</div>
                  </div>
                </div>
              )}
            </div>

            {/* Why this advice? Context chips */}
            <div style={{ marginTop: "1.5rem" }}>
              <div style={{ fontWeight: 600, fontSize: "12px", textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "8px" }}>Why this advice?</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                {result.day_context?.crowd_level && (
                  <span style={{ fontSize: "11px", padding: "4px 8px", backgroundColor: "var(--bg-tertiary)", borderRadius: "4px", color: "var(--text-secondary)" }}>
                    Crowd {result.day_context.crowd_level.charAt(0).toUpperCase() + result.day_context.crowd_level.slice(1)}
                  </span>
                )}
                {result.day_context?.weather_level && (
                  <span style={{ fontSize: "11px", padding: "4px 8px", backgroundColor: "var(--bg-tertiary)", borderRadius: "4px", color: "var(--text-secondary)" }}>
                    Weather {result.day_context.weather_level.charAt(0).toUpperCase() + result.day_context.weather_level.slice(1)}
                  </span>
                )}
                {result.day_context?.road_level && (
                  <span style={{ fontSize: "11px", padding: "4px 8px", backgroundColor: "var(--bg-tertiary)", borderRadius: "4px", color: "var(--text-secondary)" }}>
                    Roads {result.day_context.road_level.charAt(0).toUpperCase() + result.day_context.road_level.slice(1)}
                  </span>
                )}
                {result.day_context?.segment_distance_km != null && (
                  <span style={{ fontSize: "11px", padding: "4px 8px", backgroundColor: "var(--bg-tertiary)", borderRadius: "4px", color: "var(--text-secondary)" }}>
                    Travel {Math.round(result.day_context.segment_distance_km)} km
                  </span>
                )}
                <span style={{ fontSize: "11px", padding: "4px 8px", backgroundColor: "var(--bg-tertiary)", borderRadius: "4px", color: "var(--text-secondary)" }}>
                  {result.current_emotion?.charAt(0).toUpperCase() + result.current_emotion?.slice(1)} {(result.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>

            <button className="btn-secondary mt-3" onClick={resetState}>Check another day</button>
          </div>
        )}
      </div>
    </section>
  );
}

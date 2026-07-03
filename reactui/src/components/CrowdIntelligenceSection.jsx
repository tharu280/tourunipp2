import { getCrowdSummary, titleCase } from "../helpers";

function riskClass(level) {
  if (!level) return "unknown";
  const l = String(level).toLowerCase();
  if (l === "low") return "low";
  if (l === "medium" || l === "moderate") return "medium";
  if (l === "high") return "high";
  return "unknown";
}

export default function CrowdIntelligenceSection({ plan, dashboardData }) {
  const { riskLevel, signalScore, helperSummary, recommendations, redistributionSuggestions } =
    getCrowdSummary(plan, dashboardData);

  const risk = riskLevel || "unknown";
  const cls = riskClass(risk);

  return (
    <div id="section-crowd">
      {/* Risk level row */}
      <div className="crowd-risk-row">
        <span className="crowd-risk-label">Overall crowd risk</span>
        <span className={`crowd-risk-badge ${cls}`}>
          {titleCase(risk)}
          {signalScore != null ? ` · ${Number(signalScore).toFixed(0)}` : ""}
        </span>
      </div>

      {/* Helper summary */}
      {helperSummary && (
        <p className="crowd-helper">{helperSummary}</p>
      )}

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div className="crowd-suggestions">
          {recommendations.slice(0, 4).map((rec, i) => (
            <div key={`rec-${i}`} className="suggestion-item">
              <div className="suggestion-message">
                {typeof rec === "string" ? rec : rec.message || rec.text || JSON.stringify(rec)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Redistribution suggestions */}
      {redistributionSuggestions.length > 0 && (
        <div className="crowd-suggestions">
          {redistributionSuggestions.slice(0, 4).map((item, i) => (
            <div key={`sug-${i}`} className="suggestion-item">
              {item.title && <div className="suggestion-title">{item.title}</div>}
              <div className="suggestion-message">{item.message || item.text || ""}</div>
              {item.day && (
                <div className="suggestion-tag">Day {item.day}{item.priority ? ` · ${titleCase(item.priority)}` : ""}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {!helperSummary && !recommendations.length && !redistributionSuggestions.length && (
        <div className="empty-state">Crowd intelligence details will appear after plan generation.</div>
      )}
    </div>
  );
}

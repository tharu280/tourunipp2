import { getWarnings } from "../helpers";

const ALERT_ICONS = {
  Weather: "🌦",
  Roads: "🛣",
  Crowd: "👥",
  Notice: "ℹ️",
};

export default function AlertsSection({ plan }) {
  const warnings = getWarnings(plan);

  if (!warnings.length) {
    return (
      <div className="alerts-list">
        <div className="empty-state">No alerts for your travel dates.</div>
      </div>
    );
  }

  return (
    <div className="alerts-list" id="section-alerts">
      {warnings.map((item, i) => (
        <div key={i} className="alert-item" role="article">
          <div className="alert-icon" aria-hidden="true">
            {ALERT_ICONS[item.title] || "⚠️"}
          </div>
          <div className="alert-body">
            <div className="alert-title">{item.title}</div>
            <div className="alert-text">
              {typeof item.body === "string" ? item.body : ""}
            </div>
            {item.details?.length > 0 && (
              <ul className="alert-details" aria-label={`${item.title} details`}>
                {item.details.map((d, di) => (
                  <li key={di}>{d}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

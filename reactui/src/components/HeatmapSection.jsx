import { getTimeHeatmap, getLocationHeatmap, titleCase, pressureLevel } from "../helpers";

function levelClass(level) {
  if (!level) return "unknown";
  const l = String(level).toLowerCase();
  if (l === "low") return "low";
  if (l === "medium" || l === "moderate") return "medium";
  if (l === "high") return "high";
  return "unknown";
}

export default function HeatmapSection({ plan, dashboardData }) {
  const timeRows = getTimeHeatmap(plan, dashboardData);
  const locationRows = getLocationHeatmap(plan, dashboardData);

  return (
    <div className="heatmap-block" id="section-heatmap">
      {/* Time pressure */}
      <p className="heatmap-sub-label">Time pressure by day</p>
      {timeRows.length > 0 ? (
        <div className="time-heatmap-grid">
          {timeRows.map((row, i) => {
            const cls = levelClass(row.level || pressureLevel(row.score));
            const score = row.score != null ? Number(row.score).toFixed(0) : null;
            return (
              <div
                key={`time-${i}`}
                className="heat-cell"
                data-level={cls}
              >
                <div className="heat-day">
                  {row.date ? new Date(row.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : `Day ${row.day}`}
                </div>
                <div className="heat-info">
                  <div className="heat-corridor">{row.corridor || "Route"}</div>
                  {(row.bestWindow || row.avoidWindow) && (
                    <div className="heat-windows">
                      {row.bestWindow?.label ? `Best: ${titleCase(row.bestWindow.label)}` : ""}
                      {row.avoidWindow?.label ? ` · Avoid: ${titleCase(row.avoidWindow.label)}` : ""}
                    </div>
                  )}
                </div>
                {score && (
                  <div className={`heat-score ${cls}`}>{score}</div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="empty-state">Time heatmap data will appear after plan generation.</div>
      )}

      {/* Location pressure */}
      <p className="heatmap-sub-label" style={{ marginTop: 20 }}>Location pressure</p>
      {locationRows.length > 0 ? (
        <div className="loc-heatmap-list">
          {locationRows.slice(0, 8).map((row, i) => {
            const cls = levelClass(row.level || pressureLevel(row.score));
            return (
              <div key={`loc-${i}`} className="loc-heat-item">
                <div className={`loc-heat-dot ${cls}`} aria-hidden="true" />
                <div className="loc-heat-info">
                  <div className="loc-heat-name">{row.label || row.name}</div>
                  <div className="loc-heat-meta">{row.meta || titleCase(cls) + " pressure"}</div>
                </div>
                <div className="loc-heat-score">
                  {row.score != null ? Number(row.score).toFixed(0) : titleCase(row.level || cls)}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="empty-state">Location heatmap data will appear after plan generation.</div>
      )}
    </div>
  );
}

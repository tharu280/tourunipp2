import { getTimeHeatmap, getLocationHeatmap, titleCase, pressureLevel } from "../helpers";

/* Abbrev window labels that fit in narrow cells */
function windowAbbr(label) {
  const l = String(label || "").toLowerCase().replace(/ /g, "_");
  if (l.includes("early_morning") || l.includes("early_morn")) return "Early";
  if (l.includes("late_morning")  || l.includes("late_morn"))  return "Late";
  if (l.includes("mid_morning")   || l.includes("mid_morn"))   return "Mid";
  if (l.includes("morning"))  return "Morn";
  if (l.includes("afternoon") || l.includes("aftern")) return "Aftn";
  if (l.includes("evening"))  return "Eve";
  if (l.includes("night"))    return "Night";
  return titleCase(label).slice(0, 5);
}

function levelDotClass(level) {
  if (!level) return "unknown";
  const l = String(level).toLowerCase();
  if (l === "low"  || l === "best") return "low";
  if (l === "medium" || l === "moderate" || l === "good") return "medium";
  if (l === "high" || l === "bad") return "high";
  return "unknown";
}

export default function HeatmapSection({ plan, dashboardData }) {
  const timeRows    = getTimeHeatmap(plan, dashboardData);
  const locationRows = getLocationHeatmap(plan, dashboardData);

  /* ── Group time cells by day for the matrix ── */
  const dayMap = new Map();
  for (const cell of timeRows) {
    const key = cell.day ?? "?";
    if (!dayMap.has(key)) {
      dayMap.set(key, { day: cell.day, date: cell.date, corridor: cell.corridor, windows: [] });
    }
    dayMap.get(key).windows.push(cell);
  }
  const dayRows = [...dayMap.values()].sort((a, b) => Number(a.day) - Number(b.day));

  /* Collect all distinct window labels for column headers */
  const allWindows = [];
  const seenWin    = new Set();
  for (const row of dayRows) {
    for (const w of row.windows) {
      const wk = w.window || w.slot_label || "";
      if (wk && !seenWin.has(wk)) { seenWin.add(wk); allWindows.push(wk); }
    }
  }

  return (
    <div className="heatmap-block" id="section-heatmap">

      {/* ── Time pressure matrix ── */}
      <p className="heatmap-sub-label">Time pressure by day &amp; window</p>

      {dayRows.length > 0 ? (
        <div className="time-heatmap-matrix">
          {/* Column header row */}
          {allWindows.length > 0 && (
            <div className="thm-row" aria-hidden="true">
              <div className="thm-day-label" />
              <div className="thm-cells">
                {allWindows.map((wl) => (
                  <div
                    key={wl}
                    style={{
                      fontSize: 9,
                      fontWeight: 700,
                      textTransform: "uppercase",
                      letterSpacing: "0.3px",
                      color: "var(--text-tertiary)",
                      textAlign: "center",
                      padding: "0 2px 2px",
                    }}
                  >
                    {windowAbbr(wl)}
                  </div>
                ))}
              </div>
            </div>
          )}

          {dayRows.map((row) => {
            const dateLabel = row.date
              ? new Date(row.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })
              : `D${row.day}`;

            /* Build window lookup for this day */
            const winMap = {};
            for (const w of row.windows) {
              const wk = w.window || w.slot_label || "";
              if (wk) winMap[wk] = w;
            }

            return (
              <div key={`day-${row.day}`} className="thm-row">
                <div className="thm-day-label" title={row.corridor || ""}>
                  {dateLabel}
                </div>
                <div className="thm-cells">
                  {allWindows.map((wl) => {
                    const cell  = winMap[wl];
                    const score = cell ? Number(cell.score).toFixed(0) : null;
                    const lvl   = cell?.level || (score != null ? pressureLevel(score) : "");
                    return (
                      <div
                        key={wl}
                        className="thm-cell"
                        data-level={lvl}
                        title={`${row.corridor || "Route"} · ${wl.replace(/_/g, " ")}${score ? ` · ${score}/100` : ""}`}
                      >
                        <div className="thm-cell-score">{score ?? "—"}</div>
                        <div className="thm-cell-label">
                          {lvl === "best" ? "Best" : lvl === "good" ? "Good" : lvl === "bad" ? "Busy" : ""}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="empty-state">Time pressure heatmap will appear after plan generation.</div>
      )}

      {/* ── Location pressure ── */}
      <p className="heatmap-sub-label" style={{ marginTop: 22 }}>Location pressure</p>

      {locationRows.length > 0 ? (
        <div className="loc-heatmap-list">
          {locationRows.slice(0, 8).map((row, i) => {
            const cls   = levelDotClass(row.level || pressureLevel(row.score));
            const score = row.score != null ? Number(row.score).toFixed(0) : null;
            const intensityLabel =
              cls === "low"    ? "Quiet"
            : cls === "medium" ? "Normal"
            : cls === "high"   ? "Busy"
            : "";
            return (
              <div key={`loc-${i}`} className="loc-heat-item">
                <div className={`loc-heat-dot ${cls}`} aria-hidden="true" />
                <div className="loc-heat-info">
                  <div className="loc-heat-name">{row.label || row.name}</div>
                  <div className="loc-heat-meta">
                    {row.meta || `${titleCase(row.type || "Area")} · Estimated intensity: ${intensityLabel}`}
                  </div>
                </div>
                <div className="loc-heat-score">
                  {score != null ? `${score}` : titleCase(row.level || cls)}
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

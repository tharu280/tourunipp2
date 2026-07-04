import { getCrowdSummary, getVisitorIntensityLabel, titleCase, getRouteSegments } from "../helpers";

function riskClass(level) {
  if (!level) return "unknown";
  const l = String(level).toLowerCase();
  if (l === "low") return "low";
  if (l === "medium" || l === "moderate") return "medium";
  if (l === "high") return "high";
  return "unknown";
}

function getAttractionPressure(name, placeId, dashboardData, plan) {
  const crowd = dashboardData?.crowd || plan?.crowd || plan?.crowd_signals || {};
  const list = crowd.attraction_pressure || [];
  return list.find((a) => a.place_id === placeId || a.name === name) || {};
}

function getDayPressure(dayNum, dashboardData, plan) {
  const crowd = dashboardData?.crowd || plan?.crowd || plan?.crowd_signals || {};
  const list = crowd.zone_pressure?.days || [];
  return list.find((d) => d.day === dayNum) || {};
}

export default function CrowdIntelligenceSection({ plan, dashboardData }) {
  const { riskLevel, signalScore, helperSummary, chips } = getCrowdSummary(plan, dashboardData);

  const risk = riskLevel || "unknown";
  const cls = riskClass(risk);
  const visitor = getVisitorIntensityLabel(signalScore);

  const segments = getRouteSegments(plan);
  
  // Track seen attractions to avoid duplicates across days
  const seenPlaceIds = new Set();
  const seenNames = new Set();

  return (
    <div id="section-crowd" style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Estimated intensity banner */}
      <div className="crowd-intensity-banner" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", backgroundColor: "var(--bg-secondary)", padding: "16px", borderRadius: "12px" }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: "14px" }}>Estimated visitor intensity</div>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 2 }}>
            Based on SLTDA arrivals · Wikipedia interest · route context
          </div>
        </div>
        <div style={{ fontWeight: 700, fontSize: "16px", color: `var(--${cls}-color, var(--text-primary))` }}>{visitor}</div>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 4px" }}>
        <span style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-secondary)" }}>Relative crowd index</span>
        <span className={`crowd-risk-badge ${cls}`}>
          {titleCase(risk)}
          {signalScore != null ? ` · ${Number(signalScore).toFixed(0)}/100` : ""}
        </span>
      </div>

      {helperSummary && (
        <p style={{ margin: "0 4px", fontSize: "14px", lineHeight: "1.5", color: "var(--text-secondary)" }}>
          {helperSummary}
        </p>
      )}

      {/* Day by Day Crowd Panels */}
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        {segments.map((seg, i) => {
          const dayNum = seg.day || i + 1;
          const dayPressure = getDayPressure(dayNum, dashboardData, plan);
          const dayCls = riskClass(dayPressure.risk_level || dayPressure.pressure_level || "low");
          const dayScore = dayPressure.pressure_score ?? null;

          // Combine attractions from the segment
          const allAttractions = [
            ...(seg.ranked_places || []),
            ...(seg.top_attractions || []),
            ...(seg.selected_attractions || []),
            ...(seg.gemini_selected_attractions || []),
          ];

          // Deduplicate
          const uniqueAttractions = [];
          for (const attr of allAttractions) {
            const id = attr.place_id || attr.name;
            if (!id) continue;
            if (!seenPlaceIds.has(attr.place_id) && !seenNames.has(attr.name)) {
              if (attr.place_id) seenPlaceIds.add(attr.place_id);
              if (attr.name) seenNames.add(attr.name);
              uniqueAttractions.push(attr);
            }
          }

          const hasAttractions = uniqueAttractions.length > 0;

          return (
            <div key={`crowd-day-${dayNum}`} style={{ backgroundColor: "var(--bg-secondary)", borderRadius: "12px", overflow: "hidden", border: "1px solid var(--border-color)" }}>
              {/* Day Header */}
              <div style={{ padding: "16px", borderBottom: "1px solid var(--border-color)", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: "15px", marginBottom: "4px" }}>Day {dayNum}</div>
                  <div style={{ fontSize: "13px", color: "var(--text-secondary)" }}>
                    {seg.start_point || "Start"} → {seg.end_point || "Destination"}
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className={`crowd-risk-badge ${dayCls}`} style={{ marginBottom: "4px" }}>
                    {titleCase(dayPressure.risk_level || dayPressure.pressure_level || "Low")}
                  </div>
                  {dayScore != null && (
                    <div style={{ fontSize: "12px", color: "var(--text-tertiary)" }}>
                      Score: {Number(dayScore).toFixed(0)}/100
                    </div>
                  )}
                </div>
              </div>

              {/* Day Body */}
              <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
                
                {chips && chips.length > 0 && i === 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "8px" }}>
                    {chips.map(chip => (
                      <span key={chip} style={{ fontSize: "11px", padding: "4px 8px", backgroundColor: "var(--bg-tertiary)", borderRadius: "4px", color: "var(--text-secondary)" }}>
                        {chip}
                      </span>
                    ))}
                  </div>
                )}

                {hasAttractions ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                    {uniqueAttractions.map((attr, idx) => {
                      const attrPressure = getAttractionPressure(attr.name, attr.place_id, dashboardData, plan);
                      const aCls = riskClass(attrPressure.pressure_level || attrPressure.risk_level || "low");
                      const aScore = attrPressure.pressure_score ?? null;
                      const wiki = attrPressure.wiki_interest || attr.wiki_interest || null;
                      const visitTime = attrPressure.best_visit_window?.time_label || attrPressure.preferred_visit_window || attr.best_visit_window;
                      
                      const reasons = attrPressure.reasons || attrPressure.details || [];
                      const reasonText = reasons.length > 0 ? reasons[0] : (aScore > 65 ? "High historical demand" : "Normal demand");

                      return (
                        <div key={`attr-${idx}`} style={{ display: "flex", flexDirection: "column", gap: "8px", padding: "12px", backgroundColor: "var(--bg-tertiary)", borderRadius: "8px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                            <div style={{ fontWeight: 600, fontSize: "14px", lineHeight: "1.3", paddingRight: "8px" }}>{attr.name}</div>
                            <div className={`crowd-risk-badge ${aCls}`} style={{ fontSize: "10px", padding: "2px 6px", whiteSpace: "nowrap" }}>
                              {titleCase(attrPressure.pressure_level || attrPressure.risk_level || "Low")}
                            </div>
                          </div>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", fontSize: "12px", color: "var(--text-secondary)" }}>
                            {aScore != null && (
                              <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                                <span>👥</span> {getVisitorIntensityLabel(aScore)}
                              </span>
                            )}
                            {wiki != null && (
                              <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                                <span>📖</span> {(wiki / 1000).toFixed(1)}k Wiki
                              </span>
                            )}
                            {visitTime && (
                              <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "var(--accent-primary)", fontWeight: 500 }}>
                                <span>🕒</span> Best: {visitTime}
                              </span>
                            )}
                          </div>
                          {reasonText && (
                            <div style={{ fontSize: "12px", color: "var(--text-tertiary)", fontStyle: "italic", marginTop: "2px" }}>
                              "{reasonText}"
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div style={{ padding: "16px", backgroundColor: "var(--bg-tertiary)", borderRadius: "8px", textAlign: "center" }}>
                    <div style={{ fontWeight: 600, fontSize: "14px", marginBottom: "4px" }}>Transfer day toward {seg.end_point || "next destination"}</div>
                    <div style={{ fontSize: "13px", color: "var(--text-secondary)" }}>
                      Enjoy the scenic route. Road conditions apply.
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {segments.length === 0 && (
        <div className="empty-state">Crowd intelligence details will appear after plan generation.</div>
      )}
    </div>
  );
}

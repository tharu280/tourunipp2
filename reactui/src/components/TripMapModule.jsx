import { useState, useMemo, useEffect } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Polyline,
  Popup,
  CircleMarker,
  useMap,
} from "react-leaflet";
import { divIcon } from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  getPolyline,
  getStops,
  getCrowdAttractionMapPoints,
  getWeatherSegmentPoints,
  getRoadAlertsForMap,
  getCrowdIntelPanel,
  getVisitorIntensityLabel,
  titleCase,
} from "../helpers";
import { refreshIntelApi } from "../api";

const SRI_LANKA_CENTER = [7.8731, 80.7718];

/* ── Map mode definitions ─────────────────────────────────────────── */
const MODES = [
  { id: "route",   label: "Route" },
  { id: "crowd",   label: "Crowd" },
  { id: "weather", label: "Weather" },
  { id: "roads",   label: "Roads" },
];

/* ── Colour helpers ───────────────────────────────────────────────── */
function crowdColor(level, score) {
  const l = String(level || "").toLowerCase().replace(/[ _]/g, "");
  const n = Number(score);
  if (l === "veryhigh" || n >= 80) return "#7F1D1D";
  if (l === "high"     || n >= 68) return "#EF4444";
  if (l === "medium"   || l === "moderate" || n >= 36) return "#F59E0B";
  return "#10B981";
}

function weatherColor(riskLevel) {
  const l = String(riskLevel || "").toLowerCase();
  if (l === "high" || l === "risky")            return "#EF4444";
  if (l === "medium" || l === "moderate")       return "#F59E0B";
  if (l === "low" || l === "good" || l === "clear") return "#10B981";
  return "#9CA3AF";
}

function roadColor(severity) {
  const l = String(severity || "").toLowerCase();
  if (l === "critical" || l === "high")   return "#EF4444";
  if (l === "warning"  || l === "medium") return "#F59E0B";
  if (l === "clear"    || l === "low")    return "#10B981";
  return "#9CA3AF";
}

function levelClass(level) {
  const l = String(level || "").toLowerCase();
  if (l === "low" || l === "clear" || l === "good") return "low";
  if (l === "medium" || l === "moderate")           return "medium";
  if (l === "high" || l === "risky")                return "high";
  return "unknown";
}

function windowLabel(raw) {
  return (raw || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ── Fit map to route ─────────────────────────────────────────────── */
function FitRoute({ points }) {
  const map = useMap();
  useEffect(() => {
    if (points.length > 1) {
      map.fitBounds(points, { padding: [28, 28], maxZoom: 10 });
    }
  }, [map, points]);
  return null;
}

/* ── Stop icon factory ────────────────────────────────────────────── */
function makeStopIcon(stop) {
  return divIcon({
    className: `map-pin map-pin-${stop.kind || "day"}`,
    html: `<span>${stop.label || ""}</span>`,
    iconSize:   stop.kind === "start" || stop.kind === "end" ? [42, 28] : [32, 28],
    iconAnchor: stop.kind === "start" || stop.kind === "end" ? [21, 14] : [16, 14],
  });
}

/* ══════════════════════════════════════════════════════════════════
   MAP LAYERS
   ══════════════════════════════════════════════════════════════════ */

function RouteLayer({ polyline, stops }) {
  return (
    <>
      {polyline.length > 1 && (
        <Polyline
          positions={polyline}
          pathOptions={{ color: "#075F55", weight: 3.5, opacity: 0.9 }}
        />
      )}
      {stops.map((stop, i) => (
        <Marker
          key={`stop-${i}-${stop.label}`}
          position={[stop.point.lat, stop.point.lng]}
          icon={makeStopIcon(stop)}
        >
          <Popup>
            <div style={{ fontFamily: "Inter, sans-serif", padding: "2px 0" }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>
                {stop.label ? `${stop.label} · ` : ""}{stop.name}
              </div>
              {stop.detail && (
                <div style={{ fontSize: 12, color: "#6B7280", marginTop: 3 }}>
                  {stop.detail}
                </div>
              )}
            </div>
          </Popup>
        </Marker>
      ))}
    </>
  );
}

function CrowdLayer({ polyline, attractionPoints }) {
  return (
    <>
      {polyline.length > 1 && (
        <Polyline
          positions={polyline}
          pathOptions={{ color: "#075F55", weight: 2.5, opacity: 0.22 }}
        />
      )}
      {attractionPoints.map((item, i) => {
        const color   = crowdColor(item.pressure_level, item.pressure_score);
        const score   = item.pressure_score ?? item.combined_pressure?.score;
        const level   = titleCase(item.pressure_level || "low");
        const visitor = getVisitorIntensityLabel(score);
        const reasons = item.reasons || [];
        const wikiSummary = item.wiki_interest?.summary || null;

        return (
          <CircleMarker
            key={`crowd-${item.place_id || i}`}
            center={[item.lat, item.lng]}
            radius={9}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: 0.72,
              weight: 2.5,
            }}
          >
            <Popup maxWidth={272}>
              <div style={{ fontFamily: "Inter, sans-serif", padding: "2px 0" }}>
                <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4, letterSpacing: "-0.3px" }}>
                  {item.name}
                </div>
                <div style={{ fontSize: 11, color: "#9CA3AF", marginBottom: 8 }}>
                  Day {item.day}{item.date ? ` · ${item.date}` : ""}
                </div>

                {/* Pressure badge */}
                <div style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 5,
                  padding: "4px 10px",
                  borderRadius: 999,
                  background: color + "20",
                  color: color,
                  fontWeight: 700,
                  fontSize: 12,
                  marginBottom: 8,
                }}>
                  {level} · {score != null ? `${score}/100` : "—"}
                </div>

                {/* Visitor intensity */}
                <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 4 }}>
                  Likely visitor intensity:{" "}
                  <span style={{ color }}>{visitor}</span>
                </div>

                {/* Best window */}
                {item.preferred_visit_window && (
                  <div style={{
                    fontSize: 12, color: "#059669", fontWeight: 600, marginBottom: 6,
                    display: "flex", alignItems: "center", gap: 4,
                  }}>
                    Best window: {windowLabel(item.preferred_visit_window)}
                  </div>
                )}

                {/* Top reason */}
                {reasons[0] && (
                  <div style={{
                    fontSize: 11, color: "#6B7280", lineHeight: 1.5,
                    padding: "6px 8px", background: "#F9FAFB", borderRadius: 8,
                    marginBottom: 4,
                  }}>
                    {reasons[0].length > 130 ? reasons[0].slice(0, 130) + "…" : reasons[0]}
                  </div>
                )}

                {/* Wiki note */}
                {wikiSummary && (
                  <div style={{ fontSize: 10, color: "#9CA3AF", marginTop: 4, lineHeight: 1.4 }}>
                    {wikiSummary.length > 100 ? wikiSummary.slice(0, 100) + "…" : wikiSummary}
                  </div>
                )}

                <div style={{
                  fontSize: 10, color: "#C4B5FD", marginTop: 6, fontStyle: "italic",
                }}>
                  Estimated — not live gate counts
                </div>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </>
  );
}

function WeatherLayer({ polyline, segments }) {
  return (
    <>
      {polyline.length > 1 && (
        <Polyline
          positions={polyline}
          pathOptions={{ color: "#075F55", weight: 2.5, opacity: 0.22 }}
        />
      )}
      {segments.map((seg, i) => {
        if (!seg.point?.lat || !seg.point?.lng) return null;
        const color = weatherColor(seg.riskLevel);
        return (
          <CircleMarker
            key={`weather-${i}`}
            center={[seg.point.lat, seg.point.lng]}
            radius={11}
            pathOptions={{ color, fillColor: color, fillOpacity: 0.6, weight: 2.5 }}
          >
            <Popup maxWidth={260}>
              <div style={{ fontFamily: "Inter, sans-serif", padding: "2px 0" }}>
                <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>
                  {seg.date}
                </div>
                {seg.status === "unavailable" || seg.riskLevel === "unknown" ? (
                  <div style={{ fontSize: 12, color: "#6B7280", lineHeight: 1.5 }}>
                    Forecast unavailable this far ahead. Check closer to travel date.
                  </div>
                ) : (
                  <>
                    <div style={{ fontSize: 12, color: "#374151", fontWeight: 600 }}>
                      {titleCase(seg.riskLevel)} weather risk
                    </div>
                    {seg.condition ? (
                      <div style={{ fontSize: 12, color: "#6B7280", marginTop: 4, fontWeight: 500 }}>
                        {seg.condition}
                      </div>
                    ) : seg.riskScore != null ? (
                      <div style={{ fontSize: 12, color: "#6B7280", marginTop: 4, fontWeight: 500 }}>
                        {seg.riskScore <= 30 ? "Likely clear, good for travel" : seg.riskScore <= 65 ? "Moderate rain risk or cloudy" : "High risk of rain or storms"}
                      </div>
                    ) : null}
                    
                    {seg.tempC != null && (
                      <div style={{ fontSize: 11, color: "#6B7280", marginTop: 4 }}>
                        <strong style={{ fontWeight: 600 }}>Temp:</strong> {seg.tempC}°C
                      </div>
                    )}
                    {seg.precipMm != null && (
                      <div style={{ fontSize: 11, color: "#6B7280", marginTop: 2 }}>
                        <strong style={{ fontWeight: 600 }}>Rain:</strong> {seg.precipMm} mm
                      </div>
                    )}
                    {seg.windKph != null && (
                      <div style={{ fontSize: 11, color: "#6B7280", marginTop: 2 }}>
                        <strong style={{ fontWeight: 600 }}>Wind:</strong> {seg.windKph} km/h
                      </div>
                    )}
                    {seg.reason && (
                      <div style={{
                        fontSize: 11, color: "#6B7280", lineHeight: 1.4,
                        padding: "6px 8px", background: "#F9FAFB", borderRadius: 6,
                        marginTop: 6
                      }}>
                        {seg.reason}
                      </div>
                    )}
                  </>
                )}
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </>
  );
}

function RoadsLayer({ polyline, roadData }) {
  const routeColor = roadColor(roadData.riskLevel);
  return (
    <>
      {polyline.length > 1 && (
        <Polyline
          positions={polyline}
          pathOptions={{ color: routeColor, weight: 3.5, opacity: 0.85 }}
        />
      )}
      {roadData.incidents.map((inc, i) => {
        const lat = inc.lat ?? inc.location?.lat;
        const lng = inc.lng ?? inc.location?.lng;
        if (!lat || !lng) return null;
        const c = roadColor(inc.severity || inc.damage_type || "warning");
        return (
          <CircleMarker
            key={`road-${i}`}
            center={[lat, lng]}
            radius={9}
            pathOptions={{ color: c, fillColor: c, fillOpacity: 0.7, weight: 2 }}
          >
            <Popup>
              <div style={{ fontFamily: "Inter, sans-serif" }}>
                <div style={{ fontWeight: 700, fontSize: 13 }}>
                  {inc.title || inc.name || inc.type || "Road alert"}
                </div>
                <div style={{ fontSize: 12, color: "#6B7280", marginTop: 2, marginBottom: 6 }}>
                  {inc.status || inc.description || ""}
                </div>
                <div style={{ display: "inline-block", background: c + "22", color: c, padding: "2px 6px", borderRadius: "4px", fontSize: "11px", fontWeight: 600, marginBottom: 6 }}>
                  {titleCase(inc.severity || inc.damage_type || "Unknown")} Risk
                </div>
                {inc.location && (
                  <div style={{ fontSize: 11, color: "#4B5563", marginTop: 2 }}>
                    <strong>Location:</strong> {inc.location}
                  </div>
                )}
                {roadData.lastUpdated && (
                  <div style={{ fontSize: 10, color: "#9CA3AF", marginTop: 6, fontStyle: "italic" }}>
                    Updated: {new Date(roadData.lastUpdated).toLocaleDateString()}
                  </div>
                )}
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </>
  );
}

/* ══════════════════════════════════════════════════════════════════
   BELOW-MAP PANELS
   ══════════════════════════════════════════════════════════════════ */

function CrowdPanel({ plan, dashboardData }) {
  const intel  = getCrowdIntelPanel(plan, dashboardData);
  const cls    = levelClass(intel.overallLevel);
  const visitor = getVisitorIntensityLabel(intel.overallScore);

  return (
    <div className="map-panel" id="crowd-intel-panel">
      <div className="map-panel-header">
        <span className="map-panel-title">Crowd intelligence</span>
        {intel.overallLevel && (
          <span className={`map-panel-badge ${cls}`}>
            {titleCase(intel.overallLevel)}
          </span>
        )}
      </div>

      {intel.helperSummary && (
        <p className="map-panel-body">{intel.helperSummary}</p>
      )}

      {/* 2×2 stats grid */}
      <div className="crowd-intel-grid">
        <div className="crowd-intel-cell">
          <div className="crowd-intel-cell-label">Estimated intensity</div>
          <div className="crowd-intel-cell-value">{visitor}</div>
        </div>
        {intel.highestDay && (
          <div className="crowd-intel-cell">
            <div className="crowd-intel-cell-label">Busiest day</div>
            <div className="crowd-intel-cell-value">
              Day {intel.highestDay.day}
              {intel.highestDay.pressure_score != null
                ? <span style={{ fontSize: 12, fontWeight: 500, color: "#6B7280", marginLeft: 4 }}>
                    · {intel.highestDay.pressure_score}/100
                  </span>
                : ""}
            </div>
          </div>
        )}
        {intel.bestWindow && (
          <div className="crowd-intel-cell">
            <div className="crowd-intel-cell-label">Best visit window</div>
            <div className="crowd-intel-cell-value">
              {windowLabel(intel.bestWindow.label)}
            </div>
          </div>
        )}
        {intel.highestAttraction && (
          <div className="crowd-intel-cell">
            <div className="crowd-intel-cell-label">Busiest attraction</div>
            <div className="crowd-intel-cell-value crowd-intel-cell-value--sm">
              {intel.highestAttraction.name}
            </div>
          </div>
        )}
      </div>

      {/* Reason chips */}
      {intel.chips.length > 0 && (
        <div className="crowd-reason-chips">
          {intel.chips.map((chip, i) => (
            <span key={i} className="crowd-reason-chip">{chip}</span>
          ))}
        </div>
      )}

      {/* Redistribution suggestions */}
      {intel.redistributionSuggestions.length > 0 && (
        <div className="map-panel-suggestions">
          {intel.redistributionSuggestions.slice(0, 2).map((sug, i) => (
            <div key={i} className="map-panel-suggestion-item">
              {sug.title && (
                <div className="map-panel-suggestion-title">{sug.title}</div>
              )}
              <div className="map-panel-suggestion-body">
                {sug.message || sug.text || ""}
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="map-panel-disclaimer">
        Estimated crowd intensity — not live gate counts. Based on SLTDA tourism arrivals,
        Wikipedia page interest, attraction popularity tier, and route context.
      </p>
    </div>
  );
}

function WeatherPanel({ segments }) {
  const allUnavailable = segments.every(
    (s) => s.status === "unavailable" || s.riskLevel === "unknown"
  );

  return (
    <div className="map-panel">
      <div className="map-panel-header">
        <span className="map-panel-title">Weather</span>
        <span className={`map-panel-badge ${allUnavailable ? "unknown" : "low"}`}>
          {allUnavailable ? "Unavailable" : "Checked"}
        </span>
      </div>

      {allUnavailable ? (
        <p className="map-panel-body">
          Forecast unavailable this far ahead. Check closer to travel date.
        </p>
      ) : (
        <div className="weather-seg-list">
          {segments.map((seg, i) => (
            <div key={i} className="weather-seg-row">
              <div
                className="weather-seg-dot"
                style={{ background: weatherColor(seg.riskLevel) }}
              />
              <div className="weather-seg-info">
                <div className="weather-seg-label">{seg.date}</div>
                <div className="weather-seg-status">
                  {seg.status === "unavailable" || seg.riskLevel === "unknown"
                    ? "Forecast unavailable"
                    : titleCase(seg.riskLevel) + " weather risk"}
                </div>
                {seg.condition ? (
                  <div style={{ fontSize: 13, color: "var(--text-2)", marginTop: 2 }}>
                    {seg.condition}
                  </div>
                ) : seg.riskScore != null && seg.riskLevel !== "unknown" ? (
                  <div style={{ fontSize: 13, color: "var(--text-2)", marginTop: 2 }}>
                    {seg.riskScore <= 30 ? "Likely clear, good for travel" : seg.riskScore <= 65 ? "Moderate rain risk or cloudy" : "High risk of rain or storms"}
                  </div>
                ) : null}
                {seg.reason && (
                  <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 4, fontStyle: "italic" }}>
                    {seg.reason}
                  </div>
                )}
              </div>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2, minWidth: 60 }}>
                {seg.tempC != null && (
                  <div className="weather-seg-temp">{seg.tempC}°C</div>
                )}
                {seg.precipMm != null && (
                  <div style={{ fontSize: 12, color: "var(--text-3)" }}>{seg.precipMm}mm</div>
                )}
                {seg.windKph != null && (
                  <div style={{ fontSize: 12, color: "var(--text-3)" }}>{seg.windKph}km/h</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RoadsPanel({ roadData }) {
  const allClear  = roadData.totalNearRoute === 0 && roadData.criticalCount === 0;
  const clsBadge  = allClear ? "low" : levelClass(roadData.riskLevel);
  const badgeText = allClear ? "All clear" : titleCase(roadData.riskLevel);

  return (
    <div className="map-panel">
      <div className="map-panel-header">
        <span className="map-panel-title">Road warnings</span>
        <span className={`map-panel-badge ${clsBadge}`}>{badgeText}</span>
      </div>

      {allClear ? (
        <p className="map-panel-body">
          No road warnings or incidents detected near this route.
          Road conditions along this corridor are currently clear.
        </p>
      ) : (
        <>
          <p className="map-panel-body">
            {roadData.totalNearRoute} alert
            {roadData.totalNearRoute !== 1 ? "s" : ""} detected near the
            route.{roadData.criticalCount > 0
              ? ` ${roadData.criticalCount} critical.`
              : ""}
          </p>
          <div className="road-alerts-list">
            {roadData.incidents.slice(0, 5).map((inc, i) => {
              const c = roadColor(inc.severity || inc.damage_type || "warning");
              const hasCoords = (inc.lat != null && inc.lng != null) || (inc.location?.lat != null && inc.location?.lng != null);
              return (
                <div key={i} className="road-alert-row" style={{ display: "flex", flexDirection: "column", gap: "8px", padding: "12px", borderBottom: "1px solid var(--border-color)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px" }}>
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "10px" }}>
                      <div className="road-alert-dot" style={{ background: c, marginTop: "6px", flexShrink: 0 }} />
                      <div>
                        <div className="road-alert-name" style={{ fontWeight: 600, fontSize: "14px", lineHeight: 1.3 }}>
                          {inc.title || inc.name || inc.type || "Incident"}
                        </div>
                        <div className="road-alert-meta" style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "2px" }}>
                          {inc.status || inc.description || "Status unknown"}
                        </div>
                      </div>
                    </div>
                    <span
                      className="road-severity-pill"
                      style={{ background: c + "22", color: c, padding: "4px 8px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, whiteSpace: "nowrap" }}
                    >
                      {titleCase(inc.severity || inc.damage_type || "Unknown")}
                    </span>
                  </div>
                  {!hasCoords && (
                    <div style={{ fontSize: "11px", color: "var(--text-tertiary)", fontStyle: "italic", marginLeft: "18px" }}>
                      RoadLK did not provide exact coordinates for this alert.
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}

      {!allClear && roadData.lastUpdated && (
        <p className="map-panel-disclaimer">
          Source: RoadLK · Updated{" "}
          {new Date(roadData.lastUpdated).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
          })}
        </p>
      )}

      {allClear && (
        <p className="map-panel-disclaimer">
          Source: RoadLK road alert feed · No route-side incidents found.
        </p>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ══════════════════════════════════════════════════════════════════ */

export default function TripMapModule({ plan, dashboardData }) {
  const [activeMode,    setActiveMode]    = useState("route");
  const [refreshing,    setRefreshing]    = useState(false);
  const [refreshStatus, setRefreshStatus] = useState(null);

  const polyline        = useMemo(() => getPolyline(plan), [plan]);
  const stops           = useMemo(() => getStops(plan), [plan]);
  const crowdPoints     = useMemo(() => getCrowdAttractionMapPoints(plan, dashboardData), [plan, dashboardData]);
  const weatherSegs     = useMemo(() => getWeatherSegmentPoints(plan), [plan]);
  const roadData        = useMemo(() => getRoadAlertsForMap(plan), [plan]);

  const center = polyline[0] || SRI_LANKA_CENTER;

  /* Manual refresh handler */
  async function handleRefresh() {
    const sessionId = plan?.session_id;
    if (!sessionId || refreshing) return;
    setRefreshing(true);
    setRefreshStatus(null);
    try {
      await refreshIntelApi(sessionId);
      setRefreshStatus("done");
    } catch {
      setRefreshStatus("error");
    } finally {
      setRefreshing(false);
      setTimeout(() => setRefreshStatus(null), 3000);
    }
  }

  const noCrowdPoints = crowdPoints.length === 0;

  return (
    <div className="trip-map-module" id="section-map" aria-label="Trip map">

      {/* ── Mode tabs + refresh ── */}
      <div className="map-module-header">
        <div className="map-mode-tabs" role="tablist" aria-label="Map mode">
          {MODES.map((mode) => (
            <button
              key={mode.id}
              role="tab"
              aria-selected={activeMode === mode.id}
              className={`map-mode-tab${activeMode === mode.id ? " active" : ""}`}
              onClick={() => setActiveMode(mode.id)}
              id={`map-tab-${mode.id}`}
              type="button"
            >
              {mode.label}
            </button>
          ))}
        </div>

        {/* Refresh button */}
        <button
          className={`map-refresh-btn${refreshing ? " spinning" : ""}${refreshStatus === "done" ? " done" : ""}${refreshStatus === "error" ? " err" : ""}`}
          onClick={handleRefresh}
          type="button"
          disabled={refreshing}
          aria-label="Refresh intelligence"
          title="Refresh crowd and road intelligence"
        >
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 10a7 7 0 0 1 12-4.9" />
            <path d="M17 10a7 7 0 0 1-12 4.9" />
            <polyline points="15 5 15 10 10 10" />
            <polyline points="5 15 5 10 10 10" />
          </svg>
          {refreshStatus === "done"  && <span className="map-refresh-label">Updated</span>}
          {refreshStatus === "error" && <span className="map-refresh-label">Failed</span>}
        </button>
      </div>

      {/* ── Leaflet map ── */}
      <div className="map-card" aria-label={`${activeMode} map`}>
        <MapContainer
          center={center}
          zoom={8}
          scrollWheelZoom={false}
          zoomControl={false}
          attributionControl={false}
          style={{ height: "100%", width: "100%" }}
        >
          <FitRoute points={polyline} />
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
            attribution="© OpenStreetMap contributors © CARTO"
          />

          {activeMode === "route" && (
            <RouteLayer polyline={polyline} stops={stops} />
          )}
          {activeMode === "crowd" && (
            <CrowdLayer polyline={polyline} attractionPoints={crowdPoints} />
          )}
          {activeMode === "weather" && (
            <WeatherLayer polyline={polyline} segments={weatherSegs} />
          )}
          {activeMode === "roads" && (
            <RoadsLayer polyline={polyline} roadData={roadData} />
          )}
        </MapContainer>

        {/* Crowd legend overlay */}
        {activeMode === "crowd" && (
          <div className="map-crowd-legend" aria-label="Crowd pressure legend">
            <div className="map-legend-row"><span className="map-legend-dot" style={{ background: "#10B981" }} />Low</div>
            <div className="map-legend-row"><span className="map-legend-dot" style={{ background: "#F59E0B" }} />Medium</div>
            <div className="map-legend-row"><span className="map-legend-dot" style={{ background: "#EF4444" }} />High</div>
          </div>
        )}

        {/* No data overlay for crowd when unresolved */}
        {activeMode === "crowd" && noCrowdPoints && polyline.length > 0 && (
          <div className="map-no-data-overlay">
            <span>Attraction location data not resolved</span>
          </div>
        )}
      </div>

      {/* ── Below-map panels ── */}
      {activeMode === "crowd" && (
        <CrowdPanel plan={plan} dashboardData={dashboardData} />
      )}
      {activeMode === "weather" && (
        <WeatherPanel segments={weatherSegs} />
      )}
      {activeMode === "roads" && (
        <RoadsPanel roadData={roadData} />
      )}
    </div>
  );
}

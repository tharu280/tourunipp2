import { formatDistanceKm, formatDuration, formatMoney, getDailyBriefings, titleCase } from "../helpers";

function StatusPill({ level, children }) {
  const normalized = ["low", "medium", "high"].includes(level) ? level : "unknown";
  return <span className={`daily-status daily-status-${normalized}`}>{children || titleCase(normalized)}</span>;
}

function formatDate(value) {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function valueOrDash(value, suffix = "") {
  const number = Number(value);
  return Number.isFinite(number) ? `${Math.round(number)}${suffix}` : "Not available";
}

function WeatherSummary({ weather }) {
  const unavailable = weather?.status === "unavailable";
  return (
    <div className="daily-signal-card daily-weather-card">
      <div className="daily-signal-heading">
        <div>
          <span className="daily-eyebrow">Weather</span>
          <strong>{weather?.condition || "Forecast unavailable"}</strong>
        </div>
        <StatusPill level={weather?.risk_level} />
      </div>
      {!unavailable && (
        <div className="daily-metrics">
          <span><b>{valueOrDash(weather?.temperature_max_c, "°")}</b> high</span>
          <span><b>{valueOrDash(weather?.rain_probability_pct, "%")}</b> rain</span>
          <span><b>{valueOrDash(weather?.wind_speed_kph, " km/h")}</b> wind</span>
        </div>
      )}
      <p>{weather?.guidance || "Recheck conditions before departure."}</p>
    </div>
  );
}

function AttractionList({ attractions }) {
  if (!attractions?.length) {
    return <p className="daily-empty">No unique attraction is assigned to this route day.</p>;
  }
  return (
    <div className="daily-attraction-list">
      {attractions.map((attraction, index) => (
        <article className="daily-attraction" key={attraction.place_id || `${attraction.name}-${index}`}>
          <div className="daily-attraction-index">{index + 1}</div>
          <div className="daily-attraction-copy">
            <div className="daily-attraction-title-row">
              <h4>{attraction.name}</h4>
              <StatusPill level={attraction.crowd?.level}>
                {attraction.crowd?.score != null
                  ? `${titleCase(attraction.crowd.level)} · ${Math.round(attraction.crowd.score)}/100`
                  : titleCase(attraction.crowd?.level)}
              </StatusPill>
            </div>
            <p>{attraction.action}</p>
            <div className="daily-attraction-meta">
              <span>Best: {titleCase(attraction.recommended_time)}</span>
              <span>
                {attraction.crowd?.source === "attraction_estimate"
                  ? "Attraction estimate"
                  : "Day-level estimate"}
              </span>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

function RoadsSummary({ roads }) {
  return (
    <div className="daily-signal-card">
      <div className="daily-signal-heading">
        <div>
          <span className="daily-eyebrow">Roads</span>
          <strong>
            {roads?.route_alert_count
              ? `${roads.route_alert_count} incident${roads.route_alert_count === 1 ? "" : "s"} near this segment`
              : "No incident assigned to this segment"}
          </strong>
        </div>
        <StatusPill level={roads?.risk_level} />
      </div>
      <p>{roads?.guidance}</p>
      {roads?.incidents?.length > 0 && (
        <ul className="daily-road-list">
          {roads.incidents.map((incident, index) => (
            <li key={incident.report_number || `${incident.location}-${index}`}>
              <b>{incident.damage_type}</b>
              <span>{incident.location} · {titleCase(incident.status)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function StaySummary({ accommodation, costs }) {
  return (
    <div className="daily-stay-cost-grid">
      <div className="daily-signal-card">
        <span className="daily-eyebrow">Tonight</span>
        {accommodation ? (
          <>
            <strong>{accommodation.name}</strong>
            <p>{accommodation.location || "Selected near the overnight route stop"}</p>
            <span className="daily-price">{accommodation.price_label}</span>
          </>
        ) : (
          <p>No overnight stay is planned for this day.</p>
        )}
      </div>
      <div className="daily-signal-card">
        <span className="daily-eyebrow">Tracked day cost</span>
        <strong>{formatMoney(costs?.tracked_total_lkr)}</strong>
        <div className="daily-cost-lines">
          <span>Stay <b>{formatMoney(costs?.accommodation_lkr)}</b></span>
          <span>Bus estimate <b>{formatMoney(costs?.estimated_transport_lkr)}</b></span>
        </div>
        <p className="daily-cost-note">Excludes meals, entry fees and personal spending.</p>
      </div>
    </div>
  );
}

function DailyBriefingCard({ briefing, defaultOpen }) {
  const routeDistance = formatDistanceKm(briefing.route?.distance_km);
  const routeDuration = formatDuration(briefing.route?.duration_seconds);
  return (
    <details className="daily-briefing" open={defaultOpen}>
      <summary className="daily-briefing-summary">
        <div className="daily-number">
          <span>Day</span>
          <b>{briefing.day}</b>
        </div>
        <div className="daily-summary-copy">
          <span>{formatDate(briefing.date)}</span>
          <h3>{briefing.location_label || `Day ${briefing.day}`}</h3>
          <p>{[routeDistance, routeDuration].filter(Boolean).join(" · ") || "Daily route"}</p>
        </div>
        <StatusPill level={briefing.overall_status} />
        <span className="daily-chevron" aria-hidden="true">⌄</span>
      </summary>

      <div className="daily-briefing-body">
        <p className="daily-overview">{briefing.summary}</p>

        <div className="daily-signal-grid">
          <div className="daily-signal-card">
            <div className="daily-signal-heading">
              <div>
                <span className="daily-eyebrow">Crowd outlook</span>
                <strong>
                  {briefing.crowd?.score != null
                    ? `${Math.round(briefing.crowd.score)}/100 relative pressure`
                    : "Estimate unavailable"}
                </strong>
              </div>
              <StatusPill level={briefing.crowd?.risk_level} />
            </div>
            <p>
              {briefing.crowd?.preferred_visit_window
                ? `Preferred visit window: ${titleCase(briefing.crowd.preferred_visit_window)}.`
                : "Use the attraction guidance below for timing."}
            </p>
          </div>
          <WeatherSummary weather={briefing.weather} />
        </div>

        <div className="daily-block-heading">
          <div>
            <span className="daily-eyebrow">Planned stops</span>
            <h3>Attraction conditions</h3>
          </div>
          <span>{briefing.attractions?.length || 0} stops</span>
        </div>
        <AttractionList attractions={briefing.attractions} />

        <RoadsSummary roads={briefing.roads} />
        <StaySummary accommodation={briefing.accommodation} costs={briefing.costs} />

        <div className="daily-action-panel">
          <span className="daily-eyebrow">Recommended plan</span>
          <ol>
            {(briefing.recommendations || []).map((recommendation, index) => (
              <li key={`${briefing.day}-recommendation-${index}`}>{recommendation}</li>
            ))}
          </ol>
          <div className="daily-fallback"><b>Fallback:</b> {briefing.fallback_plan}</div>
        </div>
      </div>
    </details>
  );
}

export default function DailyBriefingSection({ plan }) {
  const briefings = getDailyBriefings(plan);
  if (!briefings.length) return null;
  return (
    <div className="daily-briefing-list">
      {briefings.map((briefing, index) => (
        <DailyBriefingCard key={briefing.day || index} briefing={briefing} defaultOpen={index === 0} />
      ))}
    </div>
  );
}

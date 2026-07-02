import { useMemo, useRef, useState } from "react";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
} from "react-leaflet";
import { divIcon } from "leaflet";
import "leaflet/dist/leaflet.css";
import "./styles.css";

/* ── Constants ───────────────────────────────────────────────────── */
const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:7860"
).replace(/\/$/, "");
const DEFAULT_START_DATE = "2026-07-20";
const SRI_LANKA_CENTER = [7.8731, 80.7718];

const FLIGHT_EXAMPLES = [
  "Dubai",
  "2026 July 20",
  "1 traveller",
  "Economy",
  "500000 LKR",
];

const TRIP_EXAMPLES = [
  "Colombo",
  "Badulla",
  "4 days",
  "Colombo to Galle for 3 days",
];

/* ── Helpers ─────────────────────────────────────────────────────── */
function formatMoney(value, currency = "LKR") {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Not set";
  return `${currency} ${number.toLocaleString()}`;
}

function lodgingPriceLabel(stay) {
  const value =
    stay?.total_price_lkr ??
    stay?.price_lkr ??
    stay?.current_price_lkr ??
    stay?.estimated_nightly_cost_lkr ??
    stay?.price;
  return Number.isFinite(Number(value)) ? formatMoney(value) : "Price not shown";
}

function estimateFlightHandoff(flight, totalBudgetLkr) {
  const total = Number(totalBudgetLkr);
  if (!flight || !Number.isFinite(total)) {
    return {
      estimatedFlightLkr: null,
      remainingBudgetLkr: Number.isFinite(total) ? total : null,
    };
  }
  const price = Number(flight.price);
  if (!Number.isFinite(price))
    return { estimatedFlightLkr: null, remainingBudgetLkr: total };
  const currency = String(flight.currency || "").toUpperCase();
  const estimatedFlightLkr =
    currency === "LKR" ? price : currency === "USD" ? price * 300 : null;
  if (!Number.isFinite(estimatedFlightLkr))
    return { estimatedFlightLkr: null, remainingBudgetLkr: total };
  return {
    estimatedFlightLkr,
    remainingBudgetLkr: Math.max(0, total - estimatedFlightLkr),
  };
}

function formatDuration(seconds) {
  const number = Number(seconds);
  if (!Number.isFinite(number)) return "Flexible";
  const hours = Math.floor(number / 3600);
  const minutes = Math.round((number % 3600) / 60);
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

function formatDistanceKm(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return null;
  return `${number.toLocaleString(undefined, { maximumFractionDigits: 1 })} km`;
}

function segmentDistanceLabel(segment) {
  const km = segment?.segment_distance_km;
  if (Number.isFinite(Number(km)) && Number(km) > 0)
    return formatDistanceKm(km);
  const meters = segment?.segment_distance_m;
  if (Number.isFinite(Number(meters)) && Number(meters) > 0)
    return formatDistanceKm(Number(meters) / 1000);
  return "Distance pending";
}

function getTransportCost(plan) {
  return (
    plan?.transport_cost ||
    plan?.route_data?.transport_cost ||
    plan?.recommended_route?.transport_cost ||
    {}
  );
}

function sentence(value, fallback = "Not available yet") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function titleCase(value) {
  return sentence(value, "Unknown")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function pressureLevel(score, fallback = "planned") {
  const number = Number(score);
  if (!Number.isFinite(number)) return fallback;
  if (number >= 68) return "high";
  if (number >= 36) return "medium";
  return "low";
}

function inferRouteCorridor(plan, item = {}) {
  const districts = [
    ...(item.districts || []),
    plan?.destination_resolved?.district,
    plan?.destination_resolved?.name,
    plan?.route_data?.destination,
  ]
    .filter(Boolean)
    .map((value) => String(value).toLowerCase());

  if (
    districts.some((v) =>
      ["badulla", "ella", "nuwara eliya", "kegalle", "ratnapura"].some((n) =>
        v.includes(n)
      )
    )
  )
    return "Hill Country Corridor";
  if (
    districts.some((v) =>
      ["galle", "matara", "hambantota", "mirissa", "unawatuna"].some((n) =>
        v.includes(n)
      )
    )
  )
    return "South Coast Corridor";
  if (districts.some((v) => v.includes("kandy")))
    return "Central Heritage Corridor";
  if (
    districts.some(
      (v) => v.includes("trincomalee") || v.includes("batticaloa")
    )
  )
    return "East Coast Corridor";
  if (
    districts.some((v) => v.includes("jaffna") || v.includes("anuradhapura"))
  )
    return "Northern Cultural Corridor";
  return item.corridor || "Route Corridor";
}

async function apiPost(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      payload?.detail || response.statusText || "Request failed";
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail)
    );
  }
  return payload;
}

function buildPlanRequest(session, selectedFlight, flightPlan) {
  const req = session?.trip_requirements || {};
  const handoff = estimateFlightHandoff(selectedFlight, req.total_budget_lkr);
  return {
    origin: req.origin,
    destination: req.destination,
    duration: req.duration,
    start_date: req.flight_departure_date || DEFAULT_START_DATE,
    departure_time: "08:00",
    total_budget_lkr: req.total_budget_lkr ?? null,
    accommodation_budget_lkr:
      handoff.remainingBudgetLkr ?? req.accommodation_budget_lkr ?? null,
    selected_flight: selectedFlight || null,
    flight_plan: flightPlan
      ? {
          ...flightPlan,
          selected_result:
            selectedFlight || flightPlan.cheapest_result || null,
        }
      : null,
    include_gemini: true,
    include_roadlk: true,
    include_weather: true,
    include_crowd: true,
    response_mode: "slim",
  };
}

function buildFlightSearchRequest(session) {
  const req = session?.trip_requirements || {};
  return {
    origin: req.flight_origin,
    departure_date: req.flight_departure_date,
    search_mode: req.flight_search_mode || "single_day",
    passengers: Number(req.flight_passengers || 1),
    cabin_class: req.flight_cabin_class || "economy",
    total_budget_lkr: req.total_budget_lkr ?? null,
    currency: "USD",
  };
}

function isTripHandoff(turn) {
  const reply = String(turn?.assistant_reply || "").toLowerCase();
  return (
    turn?.active_phase === "trip" ||
    turn?.is_complete ||
    reply.includes("where should the trip start") ||
    reply.includes("where in sri lanka") ||
    reply.includes("how many days")
  );
}

function getSessionId(plan) {
  return plan?.session_id || plan?.session_storage?.session_id || null;
}

function getRouteSegments(plan) {
  return (
    plan?.route_data?.segments ||
    plan?.recommended_route?.segments ||
    plan?.recommended_route?.route_data?.segments ||
    []
  );
}

function getPolyline(plan) {
  const points = [];
  for (const segment of getRouteSegments(plan)) {
    for (const key of ["start_point", "mid_point", "end_point"]) {
      const point = segment?.[key];
      if (point?.lat && point?.lng) points.push([point.lat, point.lng]);
    }
  }
  if (!points.length) {
    const origin = plan?.origin_resolved;
    const destination = plan?.destination_resolved;
    if (origin?.lat && origin?.lng) points.push([origin.lat, origin.lng]);
    if (destination?.lat && destination?.lng)
      points.push([destination.lat, destination.lng]);
  }
  return points;
}

function getStops(plan) {
  const stops = [];
  const origin = plan?.origin_resolved;
  const destination = plan?.destination_resolved;
  if (origin?.lat && origin?.lng)
    stops.push({ name: origin.name || "Start", point: origin });
  for (const segment of getRouteSegments(plan)) {
    const end = segment?.end_point;
    if (end?.lat && end?.lng) {
      stops.push({
        name:
          segment?.recommended_lodging?.display_name ||
          segment?.day_label ||
          `Day ${segment.day || stops.length}`,
        point: end,
      });
    }
  }
  if (destination?.lat && destination?.lng)
    stops.push({
      name: destination.name || "Destination",
      point: destination,
    });
  return stops;
}

function getAttractions(plan) {
  const attractions = [];
  for (const segment of getRouteSegments(plan)) {
    const selected =
      segment?.selected_attractions ||
      segment?.gemini_selected_attractions ||
      segment?.top_attractions ||
      [];
    for (const item of selected.slice(0, 3)) {
      attractions.push({
        day: segment.day,
        name:
          item.display_name ||
          item.name ||
          item.attraction_name ||
          "Attraction",
        rating: item.rating,
      });
    }
  }
  return attractions.slice(0, 10);
}

function getLodging(plan) {
  const stays = [];
  for (const segment of getRouteSegments(plan)) {
    if (segment?.recommended_lodging)
      stays.push({
        day: segment.day,
        type: "Selected",
        ...segment.recommended_lodging,
      });
    for (const item of segment?.top_lodging || [])
      stays.push({ day: segment.day, type: "Nearby", ...item });
  }
  const seen = new Set();
  return stays
    .filter((item) => {
      const key = `${item.day}-${item.display_name || item.name}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return item.display_name || item.name;
    })
    .slice(0, 8);
}

function getTimeHeatmap(plan) {
  const crowd = plan?.crowd_signals || {};
  const dayRows = crowd?.zone_pressure?.days || [];
  const windows = crowd?.forecast_windows || [];
  const windowByDay = new Map(windows.map((item) => [Number(item.day), item]));
  return dayRows.map((item, index) => {
    const day = Number(item.day || index + 1);
    const window = windowByDay.get(day) || {};
    const score = item.pressure_score ?? item.score ?? item.signal_score;
    return {
      day,
      date: item.date || window.date,
      level: item.pressure_level || item.level || pressureLevel(score),
      score,
      corridor: inferRouteCorridor(plan, {
        ...item,
        corridor: item.corridor || window.corridor,
      }),
      bestWindow: window.best_window,
      avoidWindow: window.avoid_window,
      components: item.components || {},
      reasons: item.reasons || [],
    };
  });
}

function getLocationHeatmap(plan) {
  const crowd = plan?.crowd_signals || {};
  const zone = crowd.zone_pressure || {};
  const districts = (zone.districts || []).map((item) => ({
    label: item.district,
    level: item.pressure_level || item.level,
    score: item.pressure_score ?? item.score,
    meta: item.days?.length ? `Days ${item.days.join(", ")}` : "District pressure",
    reasons: item.reasons || [],
  }));
  const attractions = (crowd.attraction_pressure || [])
    .slice(0, 8)
    .map((item) => ({
      label: item.name || item.attraction_name,
      level: item.pressure_level || item.level || item.risk_level,
      score: item.pressure_score ?? item.score,
      meta: "Attraction pressure",
      reasons: item.reasons || item.signals || [],
    }));
  return [...districts, ...attractions].filter((item) => item.label);
}

function getRoadTrafficSummary(plan) {
  const road =
    plan?.road_alerts || plan?.recommended_route?.road_alerts || {};
  const traffic =
    plan?.traffic_data ||
    plan?.route_data?.traffic_data ||
    plan?.recommended_route?.traffic_data ||
    {};
  const incidents = road.critical_incidents?.length
    ? road.critical_incidents
    : road.incidents || [];
  return {
    road,
    traffic,
    incidents,
    stats: [
      { label: "Road risk", value: titleCase(road.risk_level || "unknown") },
      {
        label: "Near route",
        value: road.total_near_route ?? road.total_deduplicated ?? 0,
      },
      { label: "Critical", value: road.critical_count ?? 0 },
      {
        label: "Delay",
        value: Number.isFinite(Number(traffic.delay_minutes))
          ? `${Number(traffic.delay_minutes).toFixed(1)} min`
          : "unknown",
      },
    ],
  };
}

function componentItems(components = {}) {
  const labels = {
    holiday: "Holiday",
    tourism_demand: "SLTDA",
    weather: "Weather",
    road: "RoadLK",
    traffic: "Traffic",
  };
  return Object.entries(components).map(([key, value]) => ({
    key,
    label: labels[key] || titleCase(key),
    value: Number(value || 0),
  }));
}

function getCrowdSignalCards(plan) {
  const crowd = plan?.crowd_signals || {};
  const signal = crowd.signal_breakdown || {};
  const dayRows = crowd?.zone_pressure?.days || [];
  const averageComponent = (key) => {
    const values = dayRows
      .map((item) => Number(item?.components?.[key]))
      .filter((v) => Number.isFinite(v));
    if (!values.length) return null;
    return Math.round(values.reduce((s, v) => s + v, 0) / values.length);
  };
  const componentLevel = (score) => {
    if (!Number.isFinite(Number(score))) return null;
    if (Number(score) >= 16) return "medium";
    if (Number(score) > 0) return "low";
    return "low";
  };
  const tourism = signal.tourism_demand || crowd.tourism_demand_pressure || {};
  const holiday = signal.holiday_pressure || {};
  const weather = signal.weather_pressure || {};
  const road = signal.road_pressure || {};
  const traffic = signal.traffic_pressure || {};
  const tourismScore = tourism.score ?? averageComponent("tourism_demand");
  const holidayScore = holiday.score ?? averageComponent("holiday");
  const weatherScore =
    weather.score ??
    plan?.weather_data?.summary?.average_score ??
    averageComponent("weather");
  const roadScore =
    road.score ??
    traffic.score ??
    averageComponent("road") ??
    averageComponent("traffic");
  return [
    {
      label: "SLTDA tourism",
      value: titleCase(
        tourism.level || crowd.tourism_level || componentLevel(tourismScore)
      ),
      score: tourismScore,
      detail: tourism.summary || "Daily/weekly arrival trend signal.",
    },
    {
      label: "Holiday pressure",
      value: titleCase(holiday.level || componentLevel(holidayScore)),
      score: holidayScore,
      detail:
        holiday.summary || "Sri Lanka public holiday and weekend signal.",
    },
    {
      label: "Weather",
      value: titleCase(
        componentLevel(weatherScore) ||
          weather.level ||
          plan?.weather_data?.summary?.risk_level ||
          plan?.weather_data?.risk_level
      ),
      score: weatherScore,
      detail:
        weather.summary || "WeatherAPI/Open-Meteo route disruption signal.",
    },
    {
      label: "RoadLK / traffic",
      value: titleCase(
        componentLevel(roadScore) ||
          road.level ||
          plan?.road_alerts?.risk_level ||
          traffic.level
      ),
      score: roadScore,
      detail:
        road.summary ||
        traffic.summary ||
        "Road alerts plus live traffic if available.",
    },
  ];
}

function getWarnings(plan) {
  const warnings = [];
  for (const item of plan?.warnings || [])
    warnings.push({
      title: "Planner warning",
      body: cleanWarningText(String(item)),
    });
  const weather = plan?.weather_data || {};
  if (weather.summary || weather.risk_level) {
    const summary = weather.summary;
    const unavailable =
      summary?.risk_level === "unknown" &&
      (weather.locations || []).some(
        (item) => item?.forecast?.status === "unavailable"
      );
    warnings.push({
      title: "Weather",
      body: unavailable
        ? "Live forecast is outside provider range for one or more trip dates. Crowd scoring continues with SLTDA, Wikipedia, holiday, RoadLK, and traffic signals."
        : summary?.text ||
          summary?.risk_level ||
          weather.risk_level ||
          "Weather signal available.",
      details: (weather.locations || [])
        .slice(0, 4)
        .map(
          (item) =>
            `${item.name || item.label}: ${item?.risk?.risk_level || "unknown"}${item?.risk?.reasons?.length ? ` — ${item.risk.reasons[0]}` : ""}`
        ),
    });
  }
  const road = plan?.road_alerts || {};
  if (road.summary || road.risk_level || road.alerts?.length) {
    warnings.push({
      title: "RoadLK",
      body:
        road.summary ||
        `${titleCase(road.risk_level || "unknown")} road risk. ${road.total_near_route ?? road.total_deduplicated ?? 0} route-side incident(s), ${road.critical_count ?? 0} critical.`,
      details: [
        road.last_updated ? `Last updated: ${road.last_updated}` : null,
        road.corridor_meters
          ? `Route corridor scanned: ${(Number(road.corridor_meters) / 1000).toFixed(0)} km`
          : null,
        road.total_in_bbox !== undefined
          ? `Regional incidents in bounding box: ${road.total_in_bbox}`
          : null,
      ].filter(Boolean),
    });
  }
  const crowd = plan?.crowd_signals || {};
  if (crowd.helper_summary || crowd.risk_level) {
    warnings.push({
      title: "Crowd",
      body:
        crowd.helper_summary || `Crowd pressure is ${crowd.risk_level}.`,
      details: (crowd.redistribution_suggestions || [])
        .slice(0, 4)
        .map((item) => `${item.title}: ${item.message}`),
    });
  }
  return warnings;
}

function cleanWarningText(text) {
  if (!text) return "";
  if (
    text.toLowerCase().includes("ssl handshake failed") ||
    text.toLowerCase().includes("replicasetnoprimary")
  ) {
    return "Session storage could not save to MongoDB locally. The route plan still rendered.";
  }
  return text.length > 220 ? `${text.slice(0, 220)}...` : text;
}

function flightLabel(flight) {
  const airline =
    flight?.airline || flight?.airline_code || "Flight";
  const price = flight?.price
    ? `${flight.currency || "USD"} ${Number(flight.price).toLocaleString()}`
    : "Price unavailable";
  return `${airline} · ${price}`;
}

function normalizeFlightOptions(flightPlan) {
  const results = flightPlan?.results || [];
  const cheapest = flightPlan?.cheapest_result;
  if (results.length) return results;
  return cheapest ? [cheapest] : [];
}

/* ── Ambient Background ──────────────────────────────────────────── */
function AmbientOrbs() {
  return (
    <div className="orb-container" aria-hidden="true">
      <div className="orb orb-1" />
      <div className="orb orb-2" />
      <div className="orb orb-3" />
    </div>
  );
}

/* ── Top Navigation ──────────────────────────────────────────────── */
function TopNav({ step, onReset }) {
  return (
    <nav className="top-nav glass">
      <div className="brand-logo">
        <div className="brand-icon" aria-hidden="true">🗺</div>
        <span className="brand-name">Route<span>Uni</span></span>
      </div>
      {step && <span className="nav-step">{step}</span>}
      <button type="button" className="nav-reset" onClick={onReset}>
        ↩ Start over
      </button>
    </nav>
  );
}

/* ── Welcome Screen ──────────────────────────────────────────────── */
function WelcomeScreen({ onStart }) {
  return (
    <main className="welcome-screen screen">
      <AmbientOrbs />
      <div className="hero-card">
        {/* Decorative stripe handled in CSS */}
        <div className="hero-top">
          <div className="hero-badge">
            <div className="hero-badge-dot" aria-hidden="true" />
            <span>Sri Lanka · AI-Powered Trip Planner</span>
          </div>

          <h1 className="hero-title">
            Plan your<br /><em>perfect</em><br />escape.
          </h1>

          <p className="hero-desc">
            Flights, routes, hotels, crowd intelligence, live weather & emotion
            check-ins — all in one seamless, guided flow.
          </p>
        </div>

        {/* Artistic illustration */}
        <div className="hero-art" aria-hidden="true">
          <div className="art-sun" />
          <div className="art-mountains">
            <div className="art-mountain art-m1" />
            <div className="art-mountain art-m2" />
            <div className="art-mountain art-m3" />
            <div className="art-mountain art-m4" />
          </div>
          <div className="art-water" />
          <div className="art-plane">✈</div>
        </div>

        {/* Feature chips */}
        <div className="hero-features">
          <span className="chip chip-gold">✈ Flights</span>
          <span className="chip chip-jade">🏨 Stays</span>
          <span className="chip chip-sky">🗺 Routes</span>
          <span className="chip chip-ember">🌡 Weather</span>
          <span className="chip chip-gold">👥 Crowds</span>
          <span className="chip chip-jade">😊 Emotions</span>
        </div>

        <button
          id="btn-start-planning"
          type="button"
          className="btn-start"
          onClick={onStart}
        >
          <span>Begin your journey &nbsp;→</span>
        </button>
      </div>
    </main>
  );
}

/* ── Loading Screen ──────────────────────────────────────────────── */
function LoadingScreen({ title, detail, steps = [], icon = "🗺" }) {
  return (
    <main className="loading-screen screen">
      <AmbientOrbs />
      <div className="loader-wrap">
        <div className="spinner-ring" role="status" aria-label="Loading">
          <div className="spinner-inner" />
          <div className="spinner-icon" aria-hidden="true">{icon}</div>
        </div>
        <h1 className="loader-title">{title}</h1>
        <p className="loader-detail">{detail}</p>
        {steps.length > 0 && (
          <div className="loader-steps" aria-label="Loading steps">
            {steps.map((step) => (
              <span key={step} className="loader-step">{step}</span>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

/* ── Chat Stage ──────────────────────────────────────────────────── */
function ChatStage({
  step,
  title,
  subtitle,
  badgeText,
  messages,
  examples,
  input,
  setInput,
  onSend,
  busy,
  error,
  onReset,
}) {
  const windowRef = useRef(null);

  // Auto-scroll on new messages
  const prevLen = useRef(0);
  if (windowRef.current && messages.length !== prevLen.current) {
    prevLen.current = messages.length;
    setTimeout(
      () =>
        windowRef.current?.scrollTo({
          top: windowRef.current.scrollHeight,
          behavior: "smooth",
        }),
      60
    );
  }

  return (
    <div className="chat-screen screen">
      <AmbientOrbs />
      <div className="chat-frame">
        <TopNav step={step} onReset={onReset} />

        <div className="chat-header">
          {badgeText && (
            <div className="chat-header-badge">
              <span className="chip chip-gold">{badgeText}</span>
            </div>
          )}
          <h1 className="chat-title" dangerouslySetInnerHTML={{ __html: title }} />
          <p className="chat-subtitle">{subtitle}</p>
        </div>

        <div
          className="chat-window glass"
          ref={windowRef}
          aria-live="polite"
          aria-label="Conversation"
        >
          {messages.map((message) => (
            <div
              key={message.id}
              className={`bubble ${message.role}`}
            >
              <span className="bubble-label">
                {message.role === "user" ? "You" : "RouteUni Planner"}
              </span>
              <div className="bubble-body">{message.text}</div>
            </div>
          ))}
          {busy && (
            <div className="bubble assistant thinking">
              <span className="bubble-label">RouteUni Planner</span>
              <div className="bubble-body">
                <div className="thinking-dot" />
                <div className="thinking-dot" />
                <div className="thinking-dot" />
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="error-box" role="alert">
            <span className="error-icon" aria-hidden="true">⚠</span>
            <span>{error}</span>
          </div>
        )}

        <div className="quick-row" aria-label="Quick suggestions">
          {examples.map((example) => (
            <button
              key={example}
              type="button"
              className="quick-chip"
              onClick={() => setInput(example)}
              disabled={busy}
            >
              {example}
            </button>
          ))}
        </div>

        <div className="composer">
          <form className="composer-inner glass2" onSubmit={onSend}>
            <textarea
              id="chat-input"
              className="composer-textarea"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your answer or pick a suggestion above…"
              disabled={busy}
              rows={3}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if (!busy && input.trim()) onSend(e);
                }
              }}
            />
            <button
              type="button"
              className="btn-voice"
              disabled
              aria-label="Voice input (coming soon)"
            >
              🎙 Voice
            </button>
            <button
              id="btn-send-message"
              type="submit"
              className="btn-send"
              disabled={busy || !input.trim()}
            >
              {busy ? "Thinking…" : "Send →"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

/* ── Flight Options Screen ───────────────────────────────────────── */
function FlightOptionsScreen({
  session,
  flightPlan,
  selectedFlightIndex,
  setSelectedFlightIndex,
  onNext,
  onRetry,
  error,
}) {
  const req = session?.trip_requirements || {};
  const options = normalizeFlightOptions(flightPlan);
  const selected = options[selectedFlightIndex] || options[0] || null;
  const budgetHandoff = estimateFlightHandoff(selected, req.total_budget_lkr);

  return (
    <div className="screen">
      <AmbientOrbs />
      <div className="page-frame">
        <TopNav step="Flight selection" onReset={onRetry} />

        <div className="flight-screen">
          {/* Hero */}
          <div className="flight-hero-card glass">
            <div>
              <p className="flight-route-label">Flight to Colombo</p>
              <h1 className="flight-route-title">
                {req.flight_origin || "Origin"} → CMB
              </h1>
              <p className="flight-route-meta">
                {req.flight_departure_date} &nbsp;·&nbsp;{" "}
                {req.flight_passengers || 1} traveller(s) &nbsp;·&nbsp;{" "}
                {titleCase(req.flight_cabin_class || "economy")}
              </p>
            </div>
            <button
              id="btn-flight-continue"
              type="button"
              className="btn-continue"
              onClick={onNext}
            >
              Continue to trip →
            </button>
          </div>

          {error && (
            <div className="error-box" role="alert">
              <span className="error-icon" aria-hidden="true">⚠</span>
              <span>{error}</span>
            </div>
          )}

          {/* Selected ticket summary */}
          <div className="ticket-card glass">
            <div className="ticket-header">
              <div>
                <p className="ticket-label">Selected flight</p>
                <p className="ticket-airline">
                  {selected ? flightLabel(selected) : "No live fare returned"}
                </p>
                <p className="ticket-note">
                  {selected?.booking_link ||
                  selected?.deep_link ||
                  selected?.link
                    ? "Booking link saved with this option."
                    : "No live fare? The route planner will still build your full trip."}
                </p>
              </div>
              <span className="chip chip-jade">✓ Cheapest</span>
            </div>
            <div className="ticket-budget-grid">
              <div className="budget-item">
                <p className="budget-label">Est. flight spend</p>
                <p className="budget-value gold">
                  {formatMoney(budgetHandoff.estimatedFlightLkr)}
                </p>
              </div>
              <div className="budget-item">
                <p className="budget-label">Remaining for tour & stays</p>
                <p className="budget-value">
                  {formatMoney(budgetHandoff.remainingBudgetLkr)}
                </p>
              </div>
            </div>
          </div>

          {/* Flight list */}
          <div className="options-list">
            {(options.length
              ? options
              : [{ airline: "Route planner fallback", price: null }]
            ).map((flight, index) => (
              <button
                className={`flight-option-btn ${index === selectedFlightIndex ? "selected" : ""}`}
                key={`${flight.airline || "flight"}-${flight.price || index}-${index}`}
                type="button"
                onClick={() => setSelectedFlightIndex(index)}
                aria-pressed={index === selectedFlightIndex}
              >
                <div className="option-info">
                  <p className="option-airline">
                    {flight.airline || flight.airline_code || "Flight option"}
                  </p>
                  <p className="option-time">
                    {flight.departure_at ||
                      flight.departure_date ||
                      req.flight_departure_date ||
                      "Departure time pending"}
                  </p>
                </div>
                <div className="option-price">
                  {flight.price
                    ? `${flight.currency || "USD"} ${Number(flight.price).toLocaleString()}`
                    : "Continue"}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Plan Map ────────────────────────────────────────────────────── */
function PlanMap({ plan }) {
  const polyline = getPolyline(plan);
  const stops = getStops(plan);
  const center = polyline[0] || SRI_LANKA_CENTER;
  const icon = divIcon({ className: "map-pin", html: "" });

  return (
    <section className="panel glass" aria-labelledby="map-heading">
      <div className="panel-head">
        <h2 className="panel-title" id="map-heading">🗺 Route map</h2>
        <p className="panel-sub">
          {polyline.length
            ? "Generated stops and crowd markers plotted on your route."
            : "Coordinates appear once route data is fully available."}
        </p>
      </div>
      <div className="map-frame">
        <MapContainer
          center={center}
          zoom={8}
          scrollWheelZoom={false}
          className="route-map"
        >
          <TileLayer
            attribution="© OpenStreetMap contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {polyline.length > 1 && (
            <Polyline
              positions={polyline}
              pathOptions={{ color: "#f0b429", weight: 4, opacity: 0.85 }}
            />
          )}
          {stops.map((stop, index) => (
            <Marker
              icon={icon}
              key={`${stop.name}-${index}`}
              position={[stop.point.lat, stop.point.lng]}
            >
              <Popup>{stop.name}</Popup>
            </Marker>
          ))}
          {(plan?.crowd_signals?.attraction_pressure || [])
            .slice(0, 8)
            .map((item, index) => {
              const lat = item?.location?.lat || item?.lat;
              const lng = item?.location?.lng || item?.lng;
              if (!lat || !lng) return null;
              return (
                <CircleMarker
                  key={`${item.name || item.attraction_name}-${index}`}
                  center={[lat, lng]}
                  radius={7}
                  pathOptions={{
                    color: "#f0b429",
                    fillColor: "#ef4444",
                    fillOpacity: 0.4,
                    weight: 1.5,
                  }}
                >
                  <Popup>
                    {item.name || item.attraction_name || "Crowd signal"}
                  </Popup>
                </CircleMarker>
              );
            })}
        </MapContainer>
      </div>
    </section>
  );
}

/* ── Metric Cards ────────────────────────────────────────────────── */
function MetricCards({ plan, selectedFlight }) {
  const budget = plan?.budget_summary || {};
  const flight =
    selectedFlight || plan?.flight_plan?.cheapest_result || {};
  const crowd = plan?.crowd_signals || {};
  const transport = getTransportCost(plan);

  const cards = [
    {
      id: "metric-budget",
      label: "Budget for stays",
      value: formatMoney(
        budget.accommodation_budget_lkr ||
          budget.remaining_accommodation_budget_lkr ||
          budget.total_budget_lkr
      ),
      className: "gold",
      icon: "💰",
    },
    {
      id: "metric-flight",
      label: "Selected flight",
      value: flight?.price
        ? `${flight.currency || "USD"} ${Number(flight.price).toLocaleString()}`
        : "Saved",
      className: "sky",
      icon: "✈",
    },
    {
      id: "metric-crowd",
      label: "Crowd pressure",
      value: sentence(crowd.risk_level, "Unknown"),
      className:
        crowd.risk_level === "high"
          ? "ember"
          : crowd.risk_level === "medium"
          ? "gold"
          : "jade",
      icon: "👥",
    },
    {
      id: "metric-transport",
      label: "Transport estimate",
      value: formatMoney(
        transport.estimated_total_lkr || transport.total_lkr
      ),
      className: "jade",
      icon: "🚗",
    },
  ];

  return (
    <div className="metric-row" role="list" aria-label="Trip metrics">
      {cards.map((card) => (
        <div
          key={card.id}
          id={card.id}
          className="metric-card glass"
          role="listitem"
        >
          <span className="metric-label">
            <span aria-hidden="true">{card.icon}</span> {card.label}
          </span>
          <span className={`metric-value ${card.className}`}>
            {card.value}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ── Day Plan Panel ──────────────────────────────────────────────── */
function DayPlanPanel({ plan }) {
  const segments = getRouteSegments(plan);
  const attractions = getAttractions(plan);

  return (
    <section className="panel glass" aria-labelledby="itinerary-heading">
      <div className="panel-head">
        <h2 className="panel-title" id="itinerary-heading">
          🗓 Daily Itinerary
        </h2>
        <p className="panel-sub">
          Route segments, travel time, distances, and recommended stays.
        </p>
      </div>

      <div className="day-grid">
        {segments.length ? (
          segments.map((segment, index) => (
            <article
              className="day-card"
              key={`${segment.day}-${index}`}
            >
              <p className="day-number">
                Day {segment.day || index + 1}
              </p>
              <p className="day-label">
                {segment.day_label || "Route segment"}
              </p>
              <p className="day-meta">
                ⏱ {formatDuration(segment.segment_duration_seconds)}
                &ensp;·&ensp;
                📍 {segmentDistanceLabel(segment)}
              </p>
              {segment.recommended_lodging?.display_name && (
                <p className="day-stay">
                  <span aria-hidden="true">🏨</span>
                  {segment.recommended_lodging.display_name}
                </p>
              )}
            </article>
          ))
        ) : (
          <p className="muted">No day segments returned yet.</p>
        )}
      </div>

      {attractions.length > 0 && (
        <>
          <p
            className="panel-sub"
            style={{ marginTop: "20px", marginBottom: "10px" }}
          >
            ✨ Highlighted attractions
          </p>
          <div className="attraction-row" aria-label="Attractions">
            {attractions.map((item, index) => (
              <span
                key={`${item.name}-${index}`}
                className="attraction-chip"
              >
                {item.name}
              </span>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

/* ── Accommodation Panel ─────────────────────────────────────────── */
function AccommodationPanel({ plan }) {
  const stays = getLodging(plan);

  return (
    <section className="panel glass" aria-labelledby="accommodation-heading">
      <div className="panel-head">
        <h2 className="panel-title" id="accommodation-heading">
          🏨 Accommodation
        </h2>
        <p className="panel-sub">
          Selected stays and backup options from the rebuilt dataset.
        </p>
      </div>

      <div className="lodging-grid">
        {stays.length ? (
          stays.map((stay, index) => (
            <article
              className="lodging-card"
              key={`${stay.day}-${stay.display_name || stay.name}-${index}`}
            >
              <p className="lodging-day-tag">
                Day {stay.day || "?"} · {stay.type}
              </p>
              <p className="lodging-name">
                {stay.display_name || stay.name}
              </p>
              <p className="lodging-location">
                📍{" "}
                {stay.location_name ||
                  stay.district ||
                  stay.address ||
                  "Sri Lanka"}
              </p>
              <p className="lodging-price">{lodgingPriceLabel(stay)}</p>
            </article>
          ))
        ) : (
          <p className="muted">No accommodation data returned yet.</p>
        )}
      </div>
    </section>
  );
}

/* ── Crowd Intelligence Panel ────────────────────────────────────── */
function CrowdIntelPanel({ plan }) {
  const time = getTimeHeatmap(plan);
  const locations = getLocationHeatmap(plan);
  const signals = getCrowdSignalCards(plan);
  const crowd = plan?.crowd_signals || {};
  const suggestions = crowd.redistribution_suggestions || [];
  const { stats: roadStats, incidents, traffic } =
    getRoadTrafficSummary(plan);

  return (
    <section className="panel glass" aria-labelledby="crowd-heading">
      <div className="panel-head">
        <h2 className="panel-title" id="crowd-heading">
          📊 Crowd Intelligence
        </h2>
        <p className="panel-sub">
          {crowd.helper_summary ||
            "Combined from SLTDA arrivals, Wikipedia interest, holidays, weather, RoadLK, and live traffic."}
        </p>
      </div>

      {/* Signal cards */}
      <div className="signal-grid">
        {signals.map((item) => (
          <div key={item.label} className="signal-card">
            <p className="signal-label">{item.label}</p>
            <p className="signal-value">{item.value}</p>
            <p className="signal-detail">
              {Number.isFinite(Number(item.score))
                ? `Score: ${item.score}`
                : item.detail}
            </p>
          </div>
        ))}
      </div>

      {/* Heatmaps */}
      <div className="heatmap-cols">
        {/* Time heatmap */}
        <div className="heatmap-block">
          <div className="heatmap-block-title">
            <strong>Time pressure</strong>
            <span>Best & avoid windows per day</span>
          </div>
          <div className="heat-cells">
            {time.length ? (
              time.map((item, index) => (
                <div
                  className="heat-cell"
                  data-level={String(item.level).toLowerCase()}
                  key={`${item.date}-${index}`}
                >
                  <p className="heat-date">
                    {item.date || `Day ${item.day}`}
                  </p>
                  <p className="heat-score">{item.score ?? "—"}</p>
                  <p className="heat-info">
                    {titleCase(item.level)} · {item.corridor || "Route day"}
                  </p>
                  {(item.bestWindow || item.avoidWindow) && (
                    <p className="heat-windows">
                      Best:{" "}
                      {titleCase(item.bestWindow?.label || "morning")}
                      <br />
                      Avoid:{" "}
                      {titleCase(item.avoidWindow?.label || "evening")}
                    </p>
                  )}
                  {/* Component bars */}
                  {componentItems(item.components).length > 0 && (
                    <div className="comp-bar-list">
                      {componentItems(item.components).map((comp) => (
                        <div key={comp.key} className="comp-bar-row">
                          <span className="comp-bar-label">
                            {comp.label}
                          </span>
                          <div className="comp-bar-track">
                            <div
                              className="comp-bar-fill"
                              style={{
                                width: `${Math.min(100, comp.value * 4)}%`,
                              }}
                            />
                          </div>
                          <span className="comp-bar-val">{comp.value}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))
            ) : (
              <p className="muted">No time heatmap cells returned.</p>
            )}
          </div>
        </div>

        {/* Location heatmap */}
        <div className="heatmap-block">
          <div className="heatmap-block-title">
            <strong>Location heatmap</strong>
            <span>Districts & attraction-level pressure</span>
          </div>
          <div className="loc-heat-list">
            {locations.length ? (
              locations.map((item, index) => (
                <div
                  key={`${item.label}-${index}`}
                  className="loc-heat-item"
                >
                  <div className="loc-heat-info">
                    <p className="loc-heat-name">{item.label}</p>
                    <p className="loc-heat-meta">{item.meta}</p>
                    {item.reasons?.[0] && (
                      <p
                        className="loc-heat-meta"
                        style={{ marginTop: "3px" }}
                      >
                        {item.reasons[0]}
                      </p>
                    )}
                  </div>
                  <div className="loc-heat-score">
                    {item.score ?? item.level ?? "—"}
                  </div>
                </div>
              ))
            ) : (
              <p className="muted">
                No location heatmap points returned.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Road & Traffic / Suggestions */}
      <div className="intel-cols">
        <div className="road-panel-inner">
          <div className="heatmap-block-title" style={{ marginBottom: 14 }}>
            <strong>🚧 RoadLK / Traffic</strong>
            <span>{traffic.summary || "Route alerts & delays"}</span>
          </div>
          <div className="road-stats">
            {roadStats.map((item) => (
              <div key={item.label} className="road-stat-card">
                <p className="road-stat-lbl">{item.label}</p>
                <p className="road-stat-val">{item.value}</p>
              </div>
            ))}
          </div>
          <div className="incident-list">
            {incidents.length ? (
              incidents.slice(0, 4).map((item, index) => (
                <div
                  key={item.id || item.title || index}
                  className="incident-item"
                >
                  <p className="incident-title">
                    {item.title ||
                      item.damage_type ||
                      item.status ||
                      "Road incident"}
                  </p>
                  <p className="incident-desc">
                    {item.road_name ||
                      item.location ||
                      item.description ||
                      "Route-side incident detected."}
                  </p>
                </div>
              ))
            ) : (
              <p className="muted">
                No active incidents found near this route.
              </p>
            )}
          </div>
        </div>

        <div className="suggestion-panel-inner">
          <div className="heatmap-block-title" style={{ marginBottom: 14 }}>
            <strong>💡 Flow Recommendations</strong>
            <span>Timing shifts & fallback stops</span>
          </div>
          <div className="suggestion-list">
            {suggestions.length ? (
              suggestions.slice(0, 6).map((item, index) => (
                <div
                  key={`${item.type}-${item.day}-${index}`}
                  className="suggestion-item"
                  data-priority={item.priority || "medium"}
                >
                  <p className="suggestion-day-tag">
                    Day {item.day || "?"} · {titleCase(item.priority || "medium")}
                  </p>
                  <p className="suggestion-title">{item.title}</p>
                  <p className="suggestion-msg">{item.message}</p>
                </div>
              ))
            ) : (
              <p className="muted">
                No redistribution suggestions for this run.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Warnings Panel ──────────────────────────────────────────────── */
function WarningsPanel({ plan }) {
  const warnings = getWarnings(plan);

  return (
    <section className="panel glass" aria-labelledby="warnings-heading">
      <div className="panel-head">
        <h2 className="panel-title" id="warnings-heading">
          ⚠ Alerts & Warnings
        </h2>
        <p className="panel-sub">
          Weather, road, and crowd signal advisories for your route.
        </p>
      </div>
      <div className="warning-grid">
        {warnings.length ? (
          warnings.map((item, index) => (
            <article
              key={`${item.title}-${index}`}
              className="warning-card"
            >
              <p className="warning-tag">
                <span aria-hidden="true">
                  {item.title === "Weather"
                    ? "🌧"
                    : item.title === "RoadLK"
                    ? "🚧"
                    : item.title === "Crowd"
                    ? "👥"
                    : "⚠"}
                </span>
                {item.title}
              </p>
              <p className="warning-body">
                {typeof item.body === "string"
                  ? item.body
                  : JSON.stringify(item.body)}
              </p>
              {item.details?.length > 0 && (
                <ul className="warning-details">
                  {item.details.map((detail, di) => (
                    <li key={`${item.title}-${di}`}>{detail}</li>
                  ))}
                </ul>
              )}
            </article>
          ))
        ) : (
          <p className="muted">No warning signals for this run.</p>
        )}
      </div>
    </section>
  );
}

/* ── Emotion Check-in Panel ──────────────────────────────────────── */
function EmotionCheckInPanel({ plan }) {
  const [preview, setPreview] = useState("");
  const [selected, setSelected] = useState("");
  const [locationStatus, setLocationStatus] = useState("Not captured");
  const sessionId = getSessionId(plan);

  function onFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setSelected(file.name);
    setPreview(URL.createObjectURL(file));
  }

  function captureLocation() {
    if (!navigator.geolocation) {
      setLocationStatus("Location not supported");
      return;
    }
    setLocationStatus("Requesting…");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = pos.coords.latitude.toFixed(5);
        const lng = pos.coords.longitude.toFixed(5);
        const acc = Math.round(pos.coords.accuracy || 0);
        setLocationStatus(`${lat}, ${lng} · ±${acc}m`);
      },
      () => setLocationStatus("Permission denied"),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 }
    );
  }

  return (
    <section className="panel glass emotion-panel" aria-labelledby="emotion-heading">
      <div className="panel-head">
        <h2 className="panel-title" id="emotion-heading">
          😊 Emotion Check-in
        </h2>
        <p className="panel-sub">
          Local CNN inference output can be saved against this session later.
          Your raw image never leaves the device.
        </p>
      </div>
      <div className="emotion-layout">
        <label className="upload-zone" htmlFor="emotion-upload" aria-label="Upload photo for emotion check-in">
          <input
            id="emotion-upload"
            accept="image/*"
            onChange={onFile}
            type="file"
          />
          {preview ? (
            <img alt="Emotion check-in preview" src={preview} />
          ) : (
            <>
              <span className="upload-icon" aria-hidden="true">📷</span>
              <span className="upload-text">Add photo</span>
            </>
          )}
        </label>
        <div className="emotion-info">
          <p className="emotion-session">
            <strong>
              {selected || "No photo selected yet"}
            </strong>
          </p>
          <p className="emotion-session">
            Session: <code>{sessionId || "not saved yet"}</code>
          </p>
          <p className="emotion-location">
            📍 {locationStatus}
          </p>
          <button
            type="button"
            className="btn-location"
            onClick={captureLocation}
          >
            <span aria-hidden="true">🎯</span>
            Use current location
          </button>
        </div>
      </div>
    </section>
  );
}

/* ── Itinerary Panel ─────────────────────────────────────────────── */
function ItineraryPanel({ plan }) {
  const markdown = plan?.itinerary_markdown;
  if (!markdown) return null;

  return (
    <section className="panel glass itinerary-panel" aria-labelledby="itinerary-md-heading">
      <div className="panel-head">
        <h2 className="panel-title" id="itinerary-md-heading">
          📝 Full Itinerary
        </h2>
        <p className="panel-sub">
          AI-generated itinerary guidance for your route.
        </p>
      </div>
      <pre className="itinerary-content">{markdown}</pre>
    </section>
  );
}

/* ── Results Output ──────────────────────────────────────────────── */
function PlanOutput({ plan, selectedFlight, onReset }) {
  return (
    <div className="screen">
      <AmbientOrbs />
      <div className="results-screen">
        <TopNav step="Route ready" onReset={onReset} />

        {/* Hero */}
        <header className="result-hero glass">
          <div className="result-hero-content">
            <p className="result-hero-label">
              ✈ Your Sri Lanka Trip Package
            </p>
            <h1 className="result-hero-title">
              {plan?.origin_resolved?.name || "Start"} →{" "}
              {plan?.destination_resolved?.name || "Destination"}
            </h1>
            <p className="result-hero-sub">
              {plan?.trip_dates?.length || "Planned"}-day route with flights,
              stays, crowd pressure, live maps, and AI itinerary guidance.
            </p>
          </div>
        </header>

        <MetricCards plan={plan} selectedFlight={selectedFlight} />
        <PlanMap plan={plan} />
        <DayPlanPanel plan={plan} />
        <AccommodationPanel plan={plan} />
        <CrowdIntelPanel plan={plan} />
        <WarningsPanel plan={plan} />
        <ItineraryPanel plan={plan} />
        <EmotionCheckInPanel plan={plan} />
      </div>
    </div>
  );
}

/* ── Root App ────────────────────────────────────────────────────── */
export default function App() {
  const [screen, setScreen] = useState("welcome");
  const [flightMessages, setFlightMessages] = useState([]);
  const [tripMessages, setTripMessages] = useState([]);
  const [session, setSession] = useState(null);
  const [flightPlan, setFlightPlan] = useState(null);
  const [selectedFlightIndex, setSelectedFlightIndex] = useState(0);
  const [pendingTripReply, setPendingTripReply] = useState("");
  const [plan, setPlan] = useState(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const idRef = useRef(0);

  const selectedFlight = useMemo(() => {
    const options = normalizeFlightOptions(flightPlan);
    return options[selectedFlightIndex] || options[0] || null;
  }, [flightPlan, selectedFlightIndex]);

  function makeMessage(role, text) {
    return { id: `${Date.now()}-${idRef.current++}`, role, text };
  }

  async function startFlow() {
    setScreen("booting");
    setError("");
    try {
      const payload = await apiPost("/chat", {
        message: "hey",
        session: null,
      });
      setSession(payload.session);
      setFlightMessages([
        makeMessage(
          "assistant",
          payload.turn?.assistant_reply || "Which city are you flying from?"
        ),
      ]);
      setScreen("flightChat");
    } catch (err) {
      setError(err.message);
      setScreen("flightChat");
      setFlightMessages([
        makeMessage(
          "assistant",
          "Which city are you flying from?"
        ),
      ]);
    }
  }

  async function runFlightSearch(nextSession, tripReply) {
    setScreen("flightLoading");
    setError("");
    try {
      const payload = await apiPost(
        "/flights/search",
        buildFlightSearchRequest(nextSession)
      );
      setFlightPlan(payload);
      setSelectedFlightIndex(0);
      setPendingTripReply(
        tripReply || "Where should the trip start in Sri Lanka?"
      );
      setScreen("flightOptions");
    } catch (err) {
      setFlightPlan(null);
      setSelectedFlightIndex(0);
      setPendingTripReply(
        tripReply || "Where should the trip start in Sri Lanka?"
      );
      setError(err.message);
      setScreen("flightOptions");
    }
  }

  async function sendFlightMessage(event) {
    event.preventDefault();
    const clean = input.trim();
    if (!clean || busy) return;
    setInput("");
    setError("");
    setBusy(true);
    setFlightMessages((cur) => [...cur, makeMessage("user", clean)]);
    try {
      const payload = await apiPost("/chat", { message: clean, session });
      const nextSession = payload.session;
      const turn = payload.turn || {};
      setSession(nextSession);
      setFlightMessages((cur) => [
        ...cur,
        makeMessage("assistant", turn.assistant_reply || "Got it."),
      ]);
      setBusy(false);
      if (isTripHandoff(turn)) {
        await runFlightSearch(nextSession, turn.assistant_reply);
      }
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  function continueToTrip() {
    setInput("");
    setError("");
    setTripMessages([
      makeMessage(
        "assistant",
        pendingTripReply || "Where should the trip start in Sri Lanka?"
      ),
    ]);
    setScreen("tripChat");
  }

  async function runPlanner(nextSession) {
    setScreen("planning");
    setError("");
    try {
      const payload = await apiPost(
        "/plan",
        buildPlanRequest(nextSession, selectedFlight, flightPlan)
      );
      setPlan(payload);
      setScreen("results");
    } catch (err) {
      setError(err.message);
      setScreen("tripChat");
    }
  }

  async function sendTripMessage(event) {
    event.preventDefault();
    const clean = input.trim();
    if (!clean || busy) return;
    setInput("");
    setError("");
    setBusy(true);
    setTripMessages((cur) => [...cur, makeMessage("user", clean)]);
    try {
      const payload = await apiPost("/chat", { message: clean, session });
      const nextSession = payload.session;
      const turn = payload.turn || {};
      setSession(nextSession);
      setTripMessages((cur) => [
        ...cur,
        makeMessage("assistant", turn.assistant_reply || "Got it."),
      ]);
      setBusy(false);
      if (turn.is_complete) await runPlanner(nextSession);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  function reset() {
    setScreen("welcome");
    setFlightMessages([]);
    setTripMessages([]);
    setSession(null);
    setFlightPlan(null);
    setSelectedFlightIndex(0);
    setPendingTripReply("");
    setPlan(null);
    setInput("");
    setBusy(false);
    setError("");
  }

  /* ── Screen Routing ─── */
  if (screen === "welcome") return <WelcomeScreen onStart={startFlow} />;

  if (screen === "booting") {
    return (
      <LoadingScreen
        icon="🛫"
        title="Opening your planner"
        detail="Preparing the flight intake session…"
        steps={["Starting chat", "Checking backend", "Creating session"]}
      />
    );
  }

  if (screen === "flightLoading") {
    return (
      <LoadingScreen
        icon="✈"
        title="Finding your flights"
        detail="Searching Colombo-bound fares and selecting the cheapest option for your budget."
        steps={[
          "Checking exact date",
          "Trying week fallback",
          "Ranking prices",
        ]}
      />
    );
  }

  if (screen === "planning") {
    return (
      <LoadingScreen
        icon="🗺"
        title="Building your route"
        detail="Searching routes, choosing stays, reading weather, crowd pressure, RoadLK, and map data."
        steps={[
          "Selecting route",
          "Ranking hotels",
          "Building heatmaps",
          "Writing itinerary",
        ]}
      />
    );
  }

  if (screen === "flightOptions") {
    return (
      <FlightOptionsScreen
        session={session}
        flightPlan={flightPlan}
        selectedFlightIndex={selectedFlightIndex}
        setSelectedFlightIndex={setSelectedFlightIndex}
        onNext={continueToTrip}
        onRetry={reset}
        error={error}
      />
    );
  }

  if (screen === "results") {
    return (
      <PlanOutput
        plan={plan}
        selectedFlight={selectedFlight}
        onReset={reset}
      />
    );
  }

  /* Flight chat & Trip chat */
  const isTrip = screen === "tripChat";
  return (
    <ChatStage
      step={isTrip ? "Trip route" : "Flight intake"}
      badgeText={
        isTrip ? "✈ Step 2 — Shape the route" : "✈ Step 1 — Lock the flight"
      }
      title={
        isTrip
          ? "Now shape your <em>Sri Lanka</em> route."
          : "First, let's lock <em>your flight</em>."
      }
      subtitle={
        isTrip
          ? "Tell me where to start, where to end, and how many days."
          : "Share your origin city, travel date, number of travellers, cabin class, and total budget."
      }
      messages={isTrip ? tripMessages : flightMessages}
      examples={isTrip ? TRIP_EXAMPLES : FLIGHT_EXAMPLES}
      input={input}
      setInput={setInput}
      onSend={isTrip ? sendTripMessage : sendFlightMessage}
      busy={busy}
      error={error}
      onReset={reset}
    />
  );
}

/* ── TourUni Data Helpers ────────────────────────────────────────────
   Pure functions for normalizing and formatting backend response data.
 ──────────────────────────────────────────────────────────────────── */

const DEFAULT_START_DATE = "2026-07-20";

/* ── Formatting ───────────────────────────────────────────────────── */

export function formatMoney(value, currency = "LKR") {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "—";
  return `${currency} ${number.toLocaleString()}`;
}

export function formatDuration(seconds) {
  const number = Number(seconds);
  if (!Number.isFinite(number)) return null;
  const hours = Math.floor(number / 3600);
  const minutes = Math.round((number % 3600) / 60);
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

export function formatDistanceKm(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return null;
  return `${number.toLocaleString(undefined, { maximumFractionDigits: 1 })} km`;
}

export function titleCase(value) {
  if (value === null || value === undefined || value === "") return "Unknown";
  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function sentence(value, fallback = "Not available") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

export function pressureLevel(score, fallback = "low") {
  const number = Number(score);
  if (!Number.isFinite(number)) return fallback;
  if (number >= 68) return "high";
  if (number >= 36) return "medium";
  return "low";
}

/* ── Flight helpers ──────────────────────────────────────────────── */

export function normalizeFlightOptions(flightPlan) {
  if (!flightPlan) return [];
  const results =
    flightPlan?.results ||
    flightPlan?.flight_results ||
    [];
  const cheapest = flightPlan?.cheapest_result;
  const selected = flightPlan?.selected_result;
  if (results.length) return results;
  const fallbacks = [selected, cheapest].filter(Boolean);
  return fallbacks.length ? fallbacks : [];
}

export function getBookingLink(flight) {
  if (!flight) return null;
  return (
    flight.booking_link ||
    flight.deep_link ||
    flight.ticket_link ||
    flight.generated_booking_link ||
    flight.link ||
    null
  );
}

export function estimateFlightHandoff(flight, totalBudgetLkr) {
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
    currency === "LKR"
      ? price
      : currency === "USD"
      ? price * 300
      : currency === "AED"
      ? price * 82
      : null;
  if (!Number.isFinite(estimatedFlightLkr))
    return { estimatedFlightLkr: null, remainingBudgetLkr: total };
  return {
    estimatedFlightLkr,
    remainingBudgetLkr: Math.max(0, total - estimatedFlightLkr),
  };
}

export function buildFlightSearchRequest(session) {
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

export function buildPlanRequest(session, selectedFlight, flightPlan) {
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

export function isTripHandoff(turn) {
  const reply = String(turn?.assistant_reply || "").toLowerCase();
  return (
    turn?.active_phase === "trip" ||
    turn?.is_complete ||
    reply.includes("where should the trip start") ||
    reply.includes("where in sri lanka") ||
    reply.includes("how many days") ||
    reply.includes("start location") ||
    reply.includes("starting point")
  );
}

export function getSessionId(plan) {
  return plan?.session_id || plan?.session_storage?.session_id || null;
}

/* ── Route / Map data ────────────────────────────────────────────── */

export function getRouteSegments(plan) {
  return (
    plan?.route_data?.segments ||
    plan?.recommended_route?.segments ||
    plan?.recommended_route?.route_data?.segments ||
    []
  );
}

export function getPolyline(plan) {
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

export function getStops(plan) {
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
  if (
    destination?.lat &&
    destination?.lng &&
    !stops.some(
      (s) => s.point.lat === destination.lat && s.point.lng === destination.lng
    )
  ) {
    stops.push({ name: destination.name || "Destination", point: destination });
  }
  return stops;
}

/* ── Attractions / Lodging ──────────────────────────────────────── */

export function getAttractions(plan) {
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
        dayLabel: segment.day_label,
        name:
          item.display_name ||
          item.name ||
          item.attraction_name ||
          "Attraction",
        rating: item.rating,
      });
    }
  }
  return attractions.slice(0, 15);
}

export function getLodging(plan) {
  // Try top-level fields first
  const topLevel =
    plan?.selected_accommodations ||
    plan?.accommodations ||
    plan?.lodging_plan?.selected_stays ||
    [];
  if (topLevel.length) {
    return topLevel.slice(0, 8).map((stay, i) => ({
      day: stay.day || i + 1,
      type: "Selected",
      ...stay,
    }));
  }
  // Fall back to segment recommended_lodging
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

export function lodgingPriceLabel(stay) {
  const value =
    stay?.total_price_lkr ??
    stay?.price_lkr ??
    stay?.current_price_lkr ??
    stay?.estimated_nightly_cost_lkr ??
    stay?.price;
  return Number.isFinite(Number(value))
    ? `LKR ${Number(value).toLocaleString()}`
    : "Price on request";
}

export function segmentDistanceLabel(segment) {
  const km = segment?.segment_distance_km;
  if (Number.isFinite(Number(km)) && Number(km) > 0)
    return formatDistanceKm(km);
  const meters = segment?.segment_distance_m;
  if (Number.isFinite(Number(meters)) && Number(meters) > 0)
    return formatDistanceKm(Number(meters) / 1000);
  return null;
}

/* ── Transport / Budget ──────────────────────────────────────────── */

export function getTransportCost(plan) {
  return (
    plan?.transport_cost ||
    plan?.route_data?.transport_cost ||
    plan?.recommended_route?.transport_cost ||
    {}
  );
}

export function getBudgetSummary(plan, selectedFlight, totalBudgetLkr) {
  const budget = plan?.budget_summary || {};
  const transport = getTransportCost(plan);
  const handoff = estimateFlightHandoff(selectedFlight, totalBudgetLkr);

  const flightLkr =
    budget.flight_budget_lkr ||
    budget.flight_estimate_lkr ||
    handoff.estimatedFlightLkr;
  const accomLkr =
    budget.accommodation_budget_lkr ||
    budget.remaining_accommodation_budget_lkr;
  const transportLkr =
    budget.transport_budget_lkr ||
    transport.estimated_total_lkr ||
    transport.total_lkr;
  const activitiesLkr =
    budget.activities_budget_lkr || budget.remaining_budget_lkr;
  const totalLkr = budget.total_budget_lkr || totalBudgetLkr;

  return { flightLkr, accomLkr, transportLkr, activitiesLkr, totalLkr };
}

/* ── Crowd / Heatmap ─────────────────────────────────────────────── */

export function getTimeHeatmap(plan, dashboardData) {
  // Try dashboard cache first
  const dashCells =
    dashboardData?.dashboard_cache?.time_heatmap_cells ||
    dashboardData?.time_heatmap_cells ||
    [];
  if (dashCells.length) return dashCells;

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
      corridor: item.corridor || window.corridor || "Route",
      bestWindow: window.best_window,
      avoidWindow: window.avoid_window,
      components: item.components || {},
    };
  });
}

export function getLocationHeatmap(plan, dashboardData) {
  // Try dashboard cache first
  const dashPoints =
    dashboardData?.dashboard_cache?.location_heatmap_points ||
    dashboardData?.location_heatmap_points ||
    [];
  if (dashPoints.length) return dashPoints;

  const crowd = plan?.crowd_signals || {};
  const zone = crowd.zone_pressure || {};
  const districts = (zone.districts || []).map((item) => ({
    label: item.district,
    level: item.pressure_level || item.level,
    score: item.pressure_score ?? item.score,
    meta: "District pressure",
  }));
  const attractions = (crowd.attraction_pressure || [])
    .slice(0, 8)
    .map((item) => ({
      label: item.name || item.attraction_name,
      level: item.pressure_level || item.level || item.risk_level,
      score: item.pressure_score ?? item.score,
      meta: "Attraction pressure",
    }));
  return [...districts, ...attractions].filter((item) => item.label);
}

export function getCrowdSummary(plan, dashboardData) {
  const crowd =
    dashboardData?.crowd ||
    plan?.crowd_signals ||
    {};
  return {
    riskLevel: crowd.risk_level || crowd.crowd_risk_level || null,
    signalScore: crowd.signal_score || crowd.composite_score || null,
    helperSummary: crowd.helper_summary || null,
    recommendations: crowd.recommendations || [],
    redistributionSuggestions: crowd.redistribution_suggestions || [],
    overallRisk: crowd.overall_risk || crowd.risk_level || null,
  };
}

/* ── Road / Warnings ─────────────────────────────────────────────── */

export function getRoadTrafficSummary(plan) {
  const road = plan?.road_alerts || plan?.recommended_route?.road_alerts || {};
  const traffic =
    plan?.traffic_data ||
    plan?.route_data?.traffic_data ||
    plan?.recommended_route?.traffic_data ||
    {};
  const incidents = road.critical_incidents?.length
    ? road.critical_incidents
    : road.incidents || [];
  return { road, traffic, incidents };
}

export function getWarnings(plan) {
  const warnings = [];
  for (const item of plan?.warnings || []) {
    const text = String(item);
    if (
      text.toLowerCase().includes("ssl") ||
      text.toLowerCase().includes("mongodb") ||
      text.toLowerCase().includes("replicaset")
    )
      continue;
    warnings.push({ title: "Notice", body: text.slice(0, 220) });
  }
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
        ? "Live forecast is outside provider range for some trip dates."
        : summary?.text || summary?.risk_level || "Weather data available.",
      details: (weather.locations || [])
        .slice(0, 3)
        .map(
          (item) =>
            `${item.name || item.label}: ${item?.risk?.risk_level || "unknown"}`
        ),
    });
  }
  const road = plan?.road_alerts || {};
  if (road.summary || road.risk_level || road.alerts?.length) {
    warnings.push({
      title: "Roads",
      body:
        road.summary ||
        `${titleCase(road.risk_level || "unknown")} road conditions. ${road.total_near_route ?? 0} route-side alerts.`,
    });
  }
  const crowd = plan?.crowd_signals || {};
  if (crowd.helper_summary || crowd.risk_level) {
    warnings.push({
      title: "Crowd",
      body: crowd.helper_summary || `Crowd pressure: ${crowd.risk_level}.`,
      details: (crowd.redistribution_suggestions || [])
        .slice(0, 3)
        .map((item) => `${item.title}: ${item.message}`),
    });
  }
  return warnings;
}

/* ── Overall Conditions ──────────────────────────────────────────── */

export function getOverallConditions(plan) {
  const crowd = plan?.crowd_signals || {};
  const weather = plan?.weather_data?.summary || {};
  const road = plan?.road_alerts || {};
  return {
    crowd: crowd.risk_level || "unknown",
    weather: weather.risk_level || plan?.weather_data?.risk_level || "unknown",
    roads: road.risk_level || "unknown",
    overall:
      crowd.risk_level === "low" &&
      (weather.risk_level === "low" || weather.risk_level === "unknown")
        ? "Good"
        : crowd.risk_level === "high" || road.risk_level === "high"
        ? "Caution"
        : "Moderate",
  };
}

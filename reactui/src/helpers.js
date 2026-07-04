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

export function mergePlanWithDashboard(plan, dashboardData) {
  if (!dashboardData) return plan || {};

  const route = dashboardData.route || {};
  const recommendedRoute = route.recommended_route || {};

  return {
    ...(plan || {}),
    dashboard: dashboardData,
    session_id: dashboardData.session_id || plan?.session_id,
    trip_requirements:
      dashboardData.trip_requirements || plan?.trip_requirements,
    plan_overview: dashboardData.plan_overview || plan?.plan_overview,
    trip_dates:
      dashboardData.plan_overview?.trip_dates ||
      plan?.trip_dates,
    budget_summary:
      dashboardData.budget ||
      plan?.budget_summary,
    package_explanation:
      dashboardData.package_explanation ||
      plan?.package_explanation,
    transport_cost:
      dashboardData.transport_cost ||
      plan?.transport_cost,
    route_data:
      route.route_data ||
      recommendedRoute.route_data ||
      plan?.route_data,
    recommended_route:
      recommendedRoute ||
      plan?.recommended_route,
    origin_resolved:
      route.origin_resolved ||
      plan?.origin_resolved,
    destination_resolved:
      route.destination_resolved ||
      plan?.destination_resolved,
    crowd:
      dashboardData.crowd ||
      plan?.crowd,
    crowd_signals:
      dashboardData.crowd ||
      recommendedRoute.crowd_signals ||
      plan?.crowd_signals,
    weather_summary:
      recommendedRoute.weather_summary ||
      plan?.weather_summary,
    weather_data:
      dashboardData.weather_data ||
      recommendedRoute.weather_data ||
      plan?.weather_data,
    road_alerts:
      dashboardData.road_alerts ||
      recommendedRoute.road_alerts ||
      plan?.road_alerts,
    itinerary:
      dashboardData.itinerary ||
      plan?.itinerary,
    dashboard_cache:
      dashboardData.dashboard_cache ||
      plan?.dashboard_cache,
  };
}

/* ── Route / Map data ────────────────────────────────────────────── */

export function getRouteSegments(plan) {
  return (
    plan?.route_data?.segments ||
    plan?.route?.route_data?.segments ||
    plan?.recommended_route?.segments ||
    plan?.recommended_route?.route_data?.segments ||
    plan?.route?.recommended_route?.segments ||
    plan?.route?.recommended_route?.route_data?.segments ||
    []
  );
}

function toLatLng(point) {
  const lat = Number(point?.lat ?? point?.latitude);
  const lng = Number(point?.lng ?? point?.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  return [lat, lng];
}

function coordinateKey(point) {
  const latLng = toLatLng(point);
  if (!latLng) return null;
  return `${latLng[0].toFixed(5)},${latLng[1].toFixed(5)}`;
}

function pushUniquePoint(points, point) {
  const latLng = toLatLng(point);
  if (!latLng) return;
  const previous = points[points.length - 1];
  if (previous && previous[0] === latLng[0] && previous[1] === latLng[1]) {
    return;
  }
  points.push(latLng);
}

function collectPath(points, path) {
  if (!Array.isArray(path)) return;
  for (const point of path) {
    pushUniquePoint(points, point);
  }
}

function routePointAtRatio(routePoints, ratio, fallbackPoint) {
  if (Array.isArray(routePoints) && routePoints.length) {
    const boundedRatio = Math.max(0, Math.min(1, Number(ratio) || 0));
    const index = Math.round((routePoints.length - 1) * boundedRatio);
    const selected = routePoints[index];
    if (selected) {
      return { lat: selected[0], lng: selected[1] };
    }
  }
  return fallbackPoint;
}

export function getPolyline(plan) {
  const realRouteCandidates = [
    plan?.route_data?.sampled_points,
    plan?.recommended_route?.sampled_points,
    plan?.recommended_route?.route_data?.sampled_points,
    plan?.route?.route_data?.sampled_points,
    plan?.route?.recommended_route?.sampled_points,
    plan?.route?.recommended_route?.route_data?.sampled_points,
  ];

  for (const candidate of realRouteCandidates) {
    const routePoints = [];
    collectPath(routePoints, candidate);
    if (routePoints.length > 1) return routePoints;
  }

  const points = [];
  for (const segment of getRouteSegments(plan)) {
    collectPath(points, segment?.segment_path_points);
  }
  if (points.length > 1) return points;

  for (const segment of getRouteSegments(plan)) {
    for (const key of ["start_point", "mid_point", "end_point"]) {
      pushUniquePoint(points, segment?.[key]);
    }
  }
  if (!points.length) {
    const origin = plan?.origin_resolved || plan?.route?.origin_resolved;
    const destination =
      plan?.destination_resolved || plan?.route?.destination_resolved;
    pushUniquePoint(points, origin);
    pushUniquePoint(points, destination);
  }
  return points;
}

export function getStops(plan) {
  const stops = [];
  const segments = getRouteSegments(plan);
  const tripRequirements = plan?.trip_requirements || plan?.dashboard?.trip_requirements || {};
  const routePoints = getPolyline(plan);
  const origin =
    routePointAtRatio(routePoints, 0, null) ||
    plan?.origin_resolved ||
    plan?.route?.origin_resolved ||
    segments[0]?.start_point;
  const destination =
    routePointAtRatio(routePoints, 1, null) ||
    plan?.destination_resolved ||
    plan?.route?.destination_resolved ||
    segments[segments.length - 1]?.end_point;
  const seen = new Set();
  const pushStop = (stop) => {
    const key = coordinateKey(stop.point);
    if (!key || seen.has(key)) return;
    seen.add(key);
    stops.push(stop);
  };

  if (origin?.lat && origin?.lng) {
    pushStop({
      kind: "start",
      label: "Start",
      name: origin.name || tripRequirements.origin || "Start",
      detail: "Trip begins here",
      point: origin,
    });
  }

  for (const segment of segments) {
    if (!segment?.is_overnight_stop) continue;
    const day = segment.day || stops.length;
    const checkpoint = routePointAtRatio(
      routePoints,
      day / Math.max(segments.length, 1),
      segment?.end_point,
    );
    if (checkpoint?.lat && checkpoint?.lng) {
      pushStop({
        kind: "day",
        label: `D${day}`,
        name:
          segment?.recommended_lodging?.display_name ||
          segment?.day_label ||
          `Day ${day}`,
        detail:
          segment?.recommended_lodging?.display_name
            ? `Day ${day} checkpoint · nearby stay: ${segment.recommended_lodging.display_name}`
            : `Route checkpoint · ${segment.day_label || `Day ${day}`}`,
        point: checkpoint,
      });
    }
  }

  if (
    destination?.lat &&
    destination?.lng
  ) {
    const key = coordinateKey(destination);
    const destinationName =
      destination.name || tripRequirements.destination || "Destination";
    if (key && seen.has(key)) {
      const lastStop = stops.find((stop) => coordinateKey(stop.point) === key);
      if (lastStop) {
        lastStop.kind = "end";
        lastStop.label = "End";
        lastStop.name = destinationName;
        lastStop.detail = "Trip ends here";
      }
    } else {
      pushStop({
        kind: "end",
        label: "End",
        name: destinationName,
        detail: "Trip ends here",
        point: destination,
      });
    }
  }
  return stops;
}

/* ── Attractions / Lodging ──────────────────────────────────────── */

function selectedAttractionsForSegment(segment) {
  return (
    segment?.selected_attractions ||
    segment?.gemini_selected_attractions ||
    segment?.top_attractions ||
    []
  );
}

function attractionName(item) {
  return (
    item?.display_name ||
    item?.name ||
    item?.attraction_name ||
    "Attraction"
  );
}

function attractionSignature(names) {
  return names
    .map((name) => String(name || "").trim().toLowerCase())
    .filter(Boolean)
    .sort()
    .join("|");
}

export function getAttractions(plan) {
  const attractions = [];
  for (const segment of getRouteSegments(plan)) {
    const selected = selectedAttractionsForSegment(segment);
    for (const item of selected.slice(0, 3)) {
      attractions.push({
        day: segment.day,
        dayLabel: segment.day_label,
        name: attractionName(item),
        rating: item.rating,
      });
    }
  }
  return attractions.slice(0, 15);
}

export function getItineraryRows(plan) {
  const rows = [];
  let previousSignature = "";
  const destination =
    plan?.destination_resolved?.name ||
    plan?.route?.destination_resolved?.name ||
    plan?.trip_requirements?.destination ||
    plan?.dashboard?.trip_requirements?.destination ||
    "the destination";

  for (const segment of getRouteSegments(plan)) {
    const day = segment.day || rows.length + 1;
    const names = selectedAttractionsForSegment(segment)
      .slice(0, 3)
      .map(attractionName);
    const signature = attractionSignature(names);
    const isRepeated =
      signature && previousSignature && signature === previousSignature;
    const fallbackName =
      segment?.recommended_lodging?.display_name ||
      destination ||
      "the next stop";

    rows.push({
      segment,
      day,
      label: segment.day_label || `Day ${day}`,
      highlights: isRepeated
        ? [`Travel toward ${fallbackName}`]
        : names,
      isRepeated,
    });

    if (signature) previousSignature = signature;
  }

  return rows;
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

  // Main stay carousel should show only the selected overnight stay.
  // `top_lodging` is an alternatives list and should not appear as extra hotels per day.
  const stays = [];
  for (const segment of getRouteSegments(plan)) {
    if (segment?.is_overnight_stop === false) continue;
    if (segment?.recommended_lodging) {
      stays.push({
        day: segment.day,
        type: "Selected",
        ...segment.recommended_lodging,
      });
    }
  }

  const seen = new Set();
  return stays
    .filter((item) => {
      const key = `${item.day}-${item.place_id || item.display_name || item.name}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return item.display_name || item.name;
    })
    .sort((a, b) => Number(a.day || 0) - Number(b.day || 0));
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
    budget.selected_flight_budget_lkr_estimated ||
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
    plan?.crowd ||
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
  for (const item of plan?.plan_overview?.warnings || []) {
    const text = String(item);
    warnings.push({ title: "Planning note", body: text.slice(0, 220) });
  }
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
  const weatherSummary = plan?.weather_summary || weather.summary || {};
  if (weatherSummary || weather.risk_level) {
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
        : weatherSummary?.text ||
          weatherSummary?.summary ||
          weatherSummary?.risk_level ||
          weather.risk_level ||
          "Weather data available.",
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
  const crowd = plan?.crowd || plan?.crowd_signals || {};
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
  const crowd = plan?.crowd || plan?.crowd_signals || {};
  const weather =
    plan?.weather_summary ||
    plan?.weather_data?.summary ||
    {};
  const road = plan?.road_alerts || {};
  return {
    crowd: crowd.risk_level || "unknown",
    weather:
      weather.risk_level ||
      plan?.weather_data?.risk_level ||
      "unknown",
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

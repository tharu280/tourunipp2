import { StatusBar } from "expo-status-bar";
import { LinearGradient } from "expo-linear-gradient";
import { useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  ImageBackground,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import Svg, { Circle, Path } from "react-native-svg";

const API_BASE = (
  process.env.EXPO_PUBLIC_API_BASE_URL ||
  "https://tourismproject-backendtouruni.hf.space"
).replace(/\/$/, "");

const heroImage = require("./assets/hero-train.png");

const COLORS = {
  ink: "#17241f",
  muted: "#69766f",
  soft: "#f7f8f4",
  panel: "#ffffff",
  line: "#dfe6df",
  accent: "#075f55",
  accentSoft: "#e4f2ee",
  amber: "#946b2d",
  warning: "#b25635",
};

const INITIAL_SESSION = {
  trip_requirements: {
    needs_flights: true,
    origin: null,
    destination: null,
    duration: null,
    accommodation_budget_lkr: null,
    total_budget_lkr: null,
    flight_origin_input: null,
    flight_origin: null,
    flight_departure_date: null,
    flight_search_mode: null,
    flight_passengers: null,
    flight_cabin_class: null,
  },
  history: [],
  active_phase: "flight",
};

const INTRO_MESSAGE = {
  role: "assistant",
  content:
    "Hi, I'm TourUni. Let's find the best flight to Sri Lanka. Where are you departing from?",
};

const FLIGHT_CHIPS = ["Dubai", "2026-07-20", "1 traveller", "Economy", "500000 LKR"];
const TRIP_CHIPS = ["Colombo", "Badulla", "4 days", "Colombo to Galle for 3 days"];

function money(value, currency = "LKR") {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Not available";
  return `${currency} ${number.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function hasNumber(value) {
  if (value === null || value === undefined || value === "") return false;
  return Number.isFinite(Number(value));
}

function sentence(value, fallback = "Not available") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function titleCase(value) {
  return sentence(value, "Unknown")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function getReq(session) {
  return session?.trip_requirements || {};
}

function flightReady(session) {
  const req = getReq(session);
  return Boolean(
    req.flight_origin &&
      req.flight_departure_date &&
      req.flight_passengers &&
      req.flight_cabin_class &&
      req.total_budget_lkr
  );
}

function tripReady(session) {
  const req = getReq(session);
  return Boolean(req.origin && req.destination && req.duration);
}

async function apiPost(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.detail || response.statusText || "Request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

async function apiGet(path) {
  const response = await fetch(`${API_BASE}${path}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.detail || response.statusText || "Request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

function flightSearchPayload(session) {
  const req = getReq(session);
  return {
    origin: req.flight_origin,
    departure_date: req.flight_departure_date,
    search_mode: req.flight_search_mode || "single_day",
    passengers: Number(req.flight_passengers || 1),
    cabin_class: req.flight_cabin_class || "economy",
    total_budget_lkr: req.total_budget_lkr,
    currency: "USD",
  };
}

function flightCostLkr(flight) {
  const price = Number(flight?.price);
  if (!Number.isFinite(price)) return null;
  const currency = String(flight?.currency || "USD").toUpperCase();
  if (currency === "LKR") return price;
  if (currency === "USD") return price * 300;
  return null;
}

function planPayload(session, selectedFlight, flightPlan) {
  const req = getReq(session);
  const total = Number(req.total_budget_lkr);
  const flightLkr = flightCostLkr(selectedFlight);
  return {
    origin: req.origin,
    destination: req.destination,
    duration: req.duration,
    start_date: req.flight_departure_date || "2026-07-20",
    departure_time: "08:00",
    total_budget_lkr: req.total_budget_lkr,
    accommodation_budget_lkr:
      Number.isFinite(total) && Number.isFinite(flightLkr)
        ? Math.max(0, total - flightLkr)
        : req.accommodation_budget_lkr,
    selected_flight: selectedFlight,
    flight_plan: flightPlan
      ? {
          ...flightPlan,
          selected_result: selectedFlight || flightPlan.cheapest_result || null,
        }
      : null,
    include_gemini: true,
    include_roadlk: true,
    include_weather: true,
    include_crowd: true,
    response_mode: "slim",
  };
}

function getFlightOptions(flightPlan) {
  const results = flightPlan?.results || flightPlan?.flight_results || [];
  const cheapest = flightPlan?.cheapest_result || flightPlan?.selected_result;
  const combined = cheapest ? [cheapest, ...results] : results;
  const seen = new Set();
  return combined.filter((item) => {
    const key = [
      item?.origin,
      item?.destination,
      item?.depart_at || item?.departure_at || item?.departure_time,
      item?.price,
      item?.airline,
    ].join("|");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function bookingUrl(flight, flightPlan) {
  return (
    flight?.booking_link ||
    flight?.deep_link ||
    flight?.ticket_link ||
    flightPlan?.booking_link ||
    flightPlan?.generated_booking_link ||
    null
  );
}

function flightLabel(flight) {
  const airline = flight?.airline || flight?.airline_name || "Flight option";
  const origin = flight?.origin || "DXB";
  const destination = flight?.destination || "CMB";
  return `${airline} - ${origin} to ${destination}`;
}

function flightTime(flight) {
  const depart = flight?.depart_at || flight?.departure_at || flight?.departure_time;
  const duration = flight?.duration || flight?.duration_seconds;
  if (duration && Number.isFinite(Number(duration))) {
    const hours = Math.floor(Number(duration) / 3600);
    const minutes = Math.round((Number(duration) % 3600) / 60);
    return `${sentence(depart, "Flexible time")} - ${hours}h ${minutes}m`;
  }
  return sentence(depart, "Flexible time");
}

function getRouteSegments(plan) {
  return (
    plan?.route_data?.segments ||
    plan?.route?.route_data?.segments ||
    plan?.recommended_route?.segments ||
    plan?.recommended_route?.route_data?.segments ||
    []
  );
}

function getAccommodations(plan) {
  const direct =
    plan?.selected_accommodations ||
    plan?.accommodations ||
    plan?.lodging_plan?.selected_stays ||
    plan?.itinerary?.accommodations ||
    [];
  if (Array.isArray(direct) && direct.length) return direct;
  return getRouteSegments(plan)
    .map((segment) => segment?.recommended_lodging)
    .filter(Boolean);
}

function getItineraryDays(plan) {
  const days = plan?.itinerary?.days || plan?.daily_itinerary || plan?.itinerary_days;
  if (Array.isArray(days) && days.length) return days;
  const segments = getRouteSegments(plan);
  return segments.map((segment, index) => ({
    day: index + 1,
    title: segment?.day_label || `Day ${index + 1}`,
    summary:
      segment?.summary ||
      segment?.description ||
      (segment?.top_attractions || [])
        .slice(0, 3)
        .map((place) => place.display_name || place.name)
        .filter(Boolean)
        .join(", ") ||
      "Route segment planned.",
  }));
}

function getCrowdScore(plan) {
  return (
    plan?.crowd?.signal_score ??
    plan?.crowd_signals?.overall_pressure_score ??
    plan?.crowd_signals?.signal_score ??
    plan?.crowd_signals?.score ??
    plan?.crowd_summary?.score ??
    plan?.dashboard?.crowd?.signal_score ??
    plan?.crowd_score ??
    null
  );
}

function pressureLabel(score) {
  if (!hasNumber(score)) return "Unknown";
  const value = Number(score);
  if (value >= 68) return "High";
  if (value >= 36) return "Medium";
  return "Low";
}

function pressureDetail(score) {
  if (!hasNumber(score)) return "Awaiting score";
  return `Score ${Number(score).toFixed(0)}`;
}

function weatherTile(plan) {
  const rawRisk = plan?.weather_summary?.risk_level || plan?.weather_data?.risk_level;
  const rawSummary = plan?.weather_summary?.summary || plan?.weather_data?.summary;
  const isKnown = rawRisk && String(rawRisk).toLowerCase() !== "unknown";
  return {
    value: isKnown ? titleCase(rawRisk) : "Unknown",
    detail: isKnown ? sentence(rawSummary, "Forecast checked") : "Outside window",
  };
}

function transportTile(plan) {
  const transport = plan?.transport_cost || {};
  const fare =
    transport?.estimated_total_lkr ||
    transport?.estimated_total_fare_lkr ||
    transport?.estimated_fare_lkr;
  if (hasNumber(fare)) {
    return { value: money(fare), detail: "Estimated public transport fare" };
  }
  return { value: "No fare", detail: "No route fare match" };
}

function enrichPlanWithDashboard(planPayload, dashboard) {
  if (!dashboard) return planPayload;
  const route = dashboard.route || {};
  const recommendedRoute = route.recommended_route || {};
  return {
    ...planPayload,
    dashboard,
    dashboard_cache: dashboard.dashboard_cache || planPayload.dashboard_cache,
    plan_overview: dashboard.plan_overview || planPayload.plan_overview,
    budget_summary: dashboard.budget || planPayload.budget_summary,
    package_explanation: dashboard.package_explanation || planPayload.package_explanation,
    transport_cost: dashboard.transport_cost || planPayload.transport_cost,
    crowd: dashboard.crowd || planPayload.crowd,
    crowd_signals: dashboard.crowd || recommendedRoute.crowd_signals || planPayload.crowd_signals,
    weather_summary: recommendedRoute.weather_summary || planPayload.weather_summary,
    route_data: route.route_data || recommendedRoute.route_data || planPayload.route_data,
    recommended_route: recommendedRoute || planPayload.recommended_route,
    origin_resolved: route.origin_resolved || planPayload.origin_resolved,
    destination_resolved: route.destination_resolved || planPayload.destination_resolved,
    itinerary: dashboard.itinerary || planPayload.itinerary,
  };
}

function heatLevelColor(level) {
  const normalized = String(level || "").toLowerCase();
  if (normalized === "high" || normalized === "bad") return "#d96a4a";
  if (normalized === "medium" || normalized === "good") return "#d99f4e";
  return COLORS.accent;
}

function ScreenFrame({ children, tone = "light" }) {
  return (
    <SafeAreaView style={[styles.safe, tone === "dark" && styles.safeDark]}>
      <StatusBar style={tone === "dark" ? "light" : "dark"} />
      {children}
    </SafeAreaView>
  );
}

function Header({ title, subtitle, onBack }) {
  return (
    <View style={styles.header}>
      {onBack ? (
        <Pressable onPress={onBack} style={styles.backButton}>
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      ) : (
        <View style={styles.backSpacer} />
      )}
      <View style={styles.headerCenter}>
        <Text style={styles.headerTitle}>{title}</Text>
        {subtitle ? <Text style={styles.headerSubtitle}>{subtitle}</Text> : null}
      </View>
      <View style={styles.backSpacer} />
    </View>
  );
}

function StartScreen({ onStart }) {
  return (
    <ScreenFrame tone="dark">
      <ImageBackground source={heroImage} resizeMode="cover" style={styles.hero}>
        <LinearGradient colors={["rgba(0,0,0,0.16)", "rgba(0,0,0,0.22)", "rgba(0,0,0,0.72)"]} style={styles.heroShade}>
          <View style={styles.heroContent}>
            <Text style={styles.heroTitle}>TourUni</Text>
            <Text style={styles.heroSubtitle}>Plan Sri Lanka with one conversation.</Text>
            <Pressable onPress={onStart} style={styles.heroButton}>
              <Text style={styles.heroButtonText}>Get started</Text>
            </Pressable>
            <Text style={styles.heroFootnote}>Flights, routes, stays, crowd pressure, and budget in one flow.</Text>
          </View>
        </LinearGradient>
      </ImageBackground>
    </ScreenFrame>
  );
}

function MessageBubble({ item }) {
  const isUser = item.role === "user";
  return (
    <View style={[styles.messageRow, isUser && styles.messageRowUser]}>
      <View style={[styles.bubble, isUser ? styles.userBubble : styles.botBubble]}>
        {!isUser ? <Text style={styles.bubbleLabel}>TourUni</Text> : null}
        <Text style={[styles.bubbleText, isUser && styles.userBubbleText]}>{item.content}</Text>
      </View>
    </View>
  );
}

function ChatScreen({
  title,
  subtitle,
  session,
  input,
  setInput,
  onSend,
  loading,
  chips,
  onBack,
}) {
  const scrollRef = useRef(null);
  const messages = useMemo(() => {
    if (!session?.history?.length) return [INTRO_MESSAGE];
    return session.history;
  }, [session]);

  function send(value = input) {
    const trimmed = String(value || "").trim();
    if (!trimmed || loading) return;
    onSend(trimmed);
  }

  return (
    <View style={styles.chatFrame}>
      <Header title={title} subtitle={subtitle} onBack={onBack} />
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.flex}
      >
        <ScrollView
          ref={scrollRef}
          style={styles.chatScroll}
          contentContainerStyle={styles.chatContent}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
        >
          {messages.map((item, index) => (
            <MessageBubble key={`${item.role}-${index}-${item.content}`} item={item} />
          ))}
          {loading ? (
            <View style={styles.loadingBubble}>
              <ActivityIndicator color={COLORS.accent} />
              <Text style={styles.loadingText}>Thinking through the next step</Text>
            </View>
          ) : null}
        </ScrollView>
        <View style={styles.chipRail}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            {chips.map((chip) => (
              <Pressable key={chip} onPress={() => send(chip)} style={styles.chip}>
                <Text style={styles.chipText}>{chip}</Text>
              </Pressable>
            ))}
          </ScrollView>
        </View>
        <View style={styles.composer}>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder="Type your answer"
            placeholderTextColor="#97a49d"
            style={styles.input}
            multiline
          />
          <Pressable style={styles.micButton}>
            <Text style={styles.micText}>Mic</Text>
          </Pressable>
          <Pressable onPress={() => send()} disabled={loading} style={[styles.sendButton, loading && styles.disabledButton]}>
            <Text style={styles.sendText}>Send</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

function LoadingScreen({ title, subtitle }) {
  return (
    <ScreenFrame>
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={COLORS.accent} />
        <Text style={styles.loadingTitle}>{title}</Text>
        <Text style={styles.loadingSubtitle}>{subtitle}</Text>
      </View>
    </ScreenFrame>
  );
}

function FlightOptionsScreen({ flightPlan, selectedFlight, setSelectedFlight, onNext, onBack }) {
  const options = getFlightOptions(flightPlan);
  return (
    <ScreenFrame>
      <Header title="Select your flight" subtitle="Colombo is fixed as arrival airport" onBack={onBack} />
      <ScrollView style={styles.scroll} contentContainerStyle={styles.page}>
        {options.map((flight, index) => {
          const selected = selectedFlight === flight || (!selectedFlight && index === 0);
          const link = bookingUrl(flight, flightPlan);
          return (
            <Pressable
              key={`${flightLabel(flight)}-${index}`}
              onPress={() => setSelectedFlight(flight)}
              style={[styles.flightCard, selected && styles.flightCardSelected]}
            >
              <View style={styles.cardTopLine}>
                <Text style={styles.flightName}>{flightLabel(flight)}</Text>
                {selected ? <Text style={styles.selectedText}>Selected</Text> : null}
              </View>
              <Text style={styles.flightMeta}>{flightTime(flight)}</Text>
              <View style={styles.cardTopLine}>
                <Text style={styles.flightPrice}>{money(flight?.price, flight?.currency || "USD")}</Text>
                {link ? (
                  <Pressable onPress={() => Linking.openURL(link)} style={styles.linkButton}>
                    <Text style={styles.linkText}>View ticket</Text>
                  </Pressable>
                ) : null}
              </View>
            </Pressable>
          );
        })}
        {!options.length ? (
          <View style={styles.emptyPanel}>
            <Text style={styles.emptyTitle}>No tickets returned</Text>
            <Text style={styles.emptyText}>The backend did not return flight options for this request.</Text>
          </View>
        ) : null}
      </ScrollView>
      <View style={styles.bottomAction}>
        <Pressable onPress={onNext} style={styles.primaryButton}>
          <Text style={styles.primaryButtonText}>Use selected flight</Text>
        </Pressable>
      </View>
    </ScreenFrame>
  );
}

function RouteSketch({ plan }) {
  const origin = sentence(plan?.origin_resolved?.name || plan?.route_data?.origin || getReq(plan?.chat_session).origin, "Start");
  const destination = sentence(plan?.destination_resolved?.name || plan?.route_data?.destination || getReq(plan?.chat_session).destination, "Destination");
  return (
    <View style={styles.mapCard}>
      <Svg width="100%" height="178" viewBox="0 0 320 178">
        <Path d="M42 128 C 94 40, 159 146, 278 54" stroke="#075f55" strokeWidth="4" fill="none" strokeLinecap="round" />
        <Path d="M42 128 C 94 40, 159 146, 278 54" stroke="rgba(7,95,85,0.18)" strokeWidth="16" fill="none" strokeLinecap="round" />
        <Circle cx="42" cy="128" r="9" fill="#075f55" />
        <Circle cx="278" cy="54" r="9" fill="#075f55" />
        <Circle cx="156" cy="92" r="6" fill="#d99f4e" />
      </Svg>
      <View style={styles.routeLabels}>
        <Text style={styles.routeLabel}>{origin}</Text>
        <Text style={styles.routeLabel}>{destination}</Text>
      </View>
    </View>
  );
}

function PlanScreen({ plan, selectedFlight, flightPlan, onRestart }) {
  const days = getItineraryDays(plan);
  const stays = getAccommodations(plan);
  const budget = plan?.budget_summary || {};
  const crowdScore = getCrowdScore(plan);
  const weather = weatherTile(plan);
  const transport = transportTile(plan);
  const ticket = bookingUrl(selectedFlight, flightPlan);

  return (
    <ScreenFrame>
      <Header title="Your Sri Lanka plan" subtitle={sentence(plan?.session_id, "Saved session")} />
      <ScrollView style={styles.scroll} contentContainerStyle={styles.page}>
        <RouteSketch plan={plan} />

        <View style={styles.conditionGrid}>
          <InfoTile title="Crowd" value={pressureLabel(crowdScore)} detail={pressureDetail(crowdScore)} />
          <InfoTile title="Weather" value={weather.value} detail={weather.detail} />
          <InfoTile title="Transport" value={transport.value} detail={transport.detail} />
        </View>

        <Section title="Itinerary">
          {days.slice(0, 8).map((day, index) => (
            <View key={`day-${index}`} style={styles.dayRow}>
              <View style={styles.dayNumber}>
                <Text style={styles.dayNumberText}>{day.day || index + 1}</Text>
              </View>
              <View style={styles.dayCopy}>
                <Text style={styles.dayTitle}>{sentence(day.title || day.destination || day.location, `Day ${index + 1}`)}</Text>
                <Text style={styles.daySummary}>{sentence(day.summary || day.description || day.activities?.join(", "), "Activities selected for the route.")}</Text>
              </View>
            </View>
          ))}
        </Section>

        <Section title="Accommodation">
          {stays.slice(0, 4).map((stay, index) => (
            <View key={`stay-${index}`} style={styles.stayCard}>
              <Text style={styles.stayName}>{sentence(stay.name || stay.property_name, "Selected stay")}</Text>
              <Text style={styles.stayMeta}>{sentence(stay.location || stay.city || stay.district, "Near route")}</Text>
              <Text style={styles.stayPrice}>{money(stay.total_price_lkr || stay.price_lkr || stay.current_price_lkr || stay.estimated_nightly_cost_lkr)}</Text>
            </View>
          ))}
          {!stays.length ? <Text style={styles.emptyText}>Accommodation choices will appear when the plan includes lodging data.</Text> : null}
        </Section>

        <Section title="Flight and budget">
          <View style={styles.summaryCard}>
            <Text style={styles.summaryTitle}>{selectedFlight ? flightLabel(selectedFlight) : "Flight not selected"}</Text>
            <Text style={styles.summaryText}>{selectedFlight ? flightTime(selectedFlight) : "No flight search was attached to this plan."}</Text>
            {ticket ? (
              <Pressable onPress={() => Linking.openURL(ticket)} style={styles.secondaryButton}>
                <Text style={styles.secondaryButtonText}>Open ticket link</Text>
              </Pressable>
            ) : null}
          </View>
          <View style={styles.budgetCard}>
            <BudgetLine label="Total" value={budget.total_budget_lkr} />
            <BudgetLine label="Flights" value={budget.selected_flight_estimated_lkr || budget.flight_budget_lkr} />
            <BudgetLine label="Accommodation" value={budget.accommodation_budget_lkr || budget.remaining_accommodation_budget_lkr} />
            <BudgetLine label="Nightly lodging" value={budget.nightly_lodging_budget_lkr} />
          </View>
        </Section>

        <Section title="Crowd intelligence">
          <View style={styles.summaryCard}>
            <Text style={styles.summaryTitle}>{pressureLabel(crowdScore)} route pressure</Text>
            <Text style={styles.summaryText}>
              {sentence(
                plan?.crowd_signals?.summary ||
                  plan?.itinerary_guidance?.crowd_recommendation ||
                  plan?.future_advice?.summary,
                "Crowd, weather, route, and tourism trend signals are attached to the saved session."
              )}
            </Text>
          </View>
        </Section>

        <Pressable onPress={onRestart} style={styles.resetButton}>
          <Text style={styles.resetText}>Plan another trip</Text>
        </Pressable>
      </ScrollView>
    </ScreenFrame>
  );
}

function InfoTile({ title, value, detail }) {
  return (
    <View style={styles.infoTile}>
      <Text style={styles.infoTitle}>{title}</Text>
      <Text style={styles.infoValue}>{value}</Text>
      <Text style={styles.infoDetail} numberOfLines={2}>{detail}</Text>
    </View>
  );
}

function Section({ title, children }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function BudgetLine({ label, value }) {
  return (
    <View style={styles.budgetLine}>
      <Text style={styles.budgetLabel}>{label}</Text>
      <Text style={styles.budgetValue}>{money(value)}</Text>
    </View>
  );
}

function TourUniApp() {
  const [stage, setStage] = useState("start");
  const [session, setSession] = useState(INITIAL_SESSION);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [flightPlan, setFlightPlan] = useState(null);
  const [selectedFlight, setSelectedFlight] = useState(null);
  const [plan, setPlan] = useState(null);

  function reset() {
    setStage("start");
    setSession(INITIAL_SESSION);
    setInput("");
    setLoading(false);
    setError(null);
    setFlightPlan(null);
    setSelectedFlight(null);
    setPlan(null);
  }

  async function searchFlights(nextSession) {
    setStage("flightLoading");
    setError(null);
    const payload = await apiPost("/flights/search", flightSearchPayload(nextSession));
    const options = getFlightOptions(payload);
    setFlightPlan(payload);
    setSelectedFlight(payload.cheapest_result || options[0] || null);
    setStage("flightOptions");
  }

  async function generatePlan(nextSession, flight = selectedFlight, flights = flightPlan) {
    setStage("planLoading");
    setError(null);
    const payload = await apiPost("/plan", planPayload(nextSession, flight, flights));
    setPlan(payload);
    setStage("plan");
  }

  async function continueAfterFlight() {
    try {
      if (tripReady(session)) {
        await generatePlan(session, selectedFlight, flightPlan);
        return;
      }
      setStage("tripChat");
    } catch (err) {
      setError(err.message);
    }
  }

  async function sendMessage(message) {
    setInput("");
    setLoading(true);
    setError(null);
    try {
      const response = await apiPost("/chat", { message, session });
      const nextSession = response.session;
      setSession(nextSession);

      if (!flightPlan && flightReady(nextSession)) {
        await searchFlights(nextSession);
        return;
      }

      if (response.turn?.is_complete && selectedFlight) {
        await generatePlan(nextSession);
        return;
      }

      setStage(response.turn?.active_phase === "trip" ? "tripChat" : "flightChat");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (stage === "start") {
    return <StartScreen onStart={() => setStage("flightChat")} />;
  }

  if (stage === "flightLoading") {
    return <LoadingScreen title="Getting your flights" subtitle="Searching ticket options to Colombo and selecting the best value." />;
  }

  if (stage === "planLoading") {
    return <LoadingScreen title="Building your perfect route plan" subtitle="Selecting routes, stays, crowd windows, weather signals, and budget split." />;
  }

  if (stage === "flightOptions") {
    return (
      <FlightOptionsScreen
        flightPlan={flightPlan}
        selectedFlight={selectedFlight}
        setSelectedFlight={setSelectedFlight}
        onNext={continueAfterFlight}
        onBack={() => setStage("flightChat")}
      />
    );
  }

  if (stage === "plan") {
    return <PlanScreen plan={plan} selectedFlight={selectedFlight} flightPlan={flightPlan} onRestart={reset} />;
  }

  return (
    <ScreenFrame>
      <ChatScreen
        title={stage === "tripChat" ? "Trip details" : "Flight details"}
        subtitle={stage === "tripChat" ? "Route, duration, and Sri Lanka stay" : "Flight to Colombo and total budget"}
        session={session}
        input={input}
        setInput={setInput}
        onSend={sendMessage}
        loading={loading}
        chips={stage === "tripChat" ? TRIP_CHIPS : FLIGHT_CHIPS}
        onBack={stage === "tripChat" ? () => setStage("flightOptions") : reset}
      />
      {error ? (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}
    </ScreenFrame>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <TourUniApp />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: COLORS.soft,
  },
  safeDark: {
    backgroundColor: "#07110e",
  },
  flex: {
    flex: 1,
  },
  chatFrame: {
    flex: 1,
    backgroundColor: COLORS.soft,
  },
  hero: {
    flex: 1,
  },
  heroShade: {
    flex: 1,
    justifyContent: "flex-end",
  },
  heroContent: {
    paddingHorizontal: 28,
    paddingBottom: 38,
  },
  heroTitle: {
    color: "#ffffff",
    fontSize: 54,
    fontWeight: "700",
    letterSpacing: -1.8,
  },
  heroSubtitle: {
    marginTop: 8,
    color: "rgba(255,255,255,0.88)",
    fontSize: 19,
    lineHeight: 27,
    fontWeight: "500",
  },
  heroButton: {
    marginTop: 36,
    height: 58,
    borderRadius: 29,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.accent,
  },
  heroButtonText: {
    color: "#ffffff",
    fontSize: 17,
    fontWeight: "700",
  },
  heroFootnote: {
    marginTop: 18,
    color: "rgba(255,255,255,0.78)",
    fontSize: 13,
    lineHeight: 19,
    textAlign: "center",
  },
  header: {
    height: 58,
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: COLORS.line,
    backgroundColor: COLORS.soft,
  },
  headerCenter: {
    flex: 1,
    alignItems: "center",
  },
  headerTitle: {
    color: COLORS.ink,
    fontSize: 17,
    fontWeight: "700",
    letterSpacing: -0.2,
  },
  headerSubtitle: {
    marginTop: 2,
    color: COLORS.muted,
    fontSize: 12,
    fontWeight: "500",
  },
  backButton: {
    width: 64,
    height: 38,
    justifyContent: "center",
  },
  backSpacer: {
    width: 64,
  },
  backText: {
    color: COLORS.accent,
    fontSize: 15,
    fontWeight: "600",
  },
  chatScroll: {
    flex: 1,
  },
  chatContent: {
    padding: 18,
    paddingBottom: 26,
  },
  messageRow: {
    flexDirection: "row",
    justifyContent: "flex-start",
    marginBottom: 16,
  },
  messageRowUser: {
    justifyContent: "flex-end",
  },
  bubble: {
    maxWidth: "82%",
    borderRadius: 22,
    paddingHorizontal: 16,
    paddingVertical: 13,
  },
  botBubble: {
    backgroundColor: COLORS.panel,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.line,
  },
  userBubble: {
    backgroundColor: COLORS.accent,
  },
  bubbleLabel: {
    color: COLORS.muted,
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.8,
    marginBottom: 7,
  },
  bubbleText: {
    color: COLORS.ink,
    fontSize: 16,
    lineHeight: 23,
    fontWeight: "400",
  },
  userBubbleText: {
    color: "#ffffff",
  },
  loadingBubble: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    backgroundColor: COLORS.panel,
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.line,
  },
  loadingText: {
    color: COLORS.muted,
    fontSize: 14,
  },
  chipRail: {
    paddingVertical: 8,
    paddingHorizontal: 14,
  },
  chip: {
    height: 38,
    paddingHorizontal: 15,
    borderRadius: 19,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 8,
    backgroundColor: COLORS.panel,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.line,
  },
  chipText: {
    color: COLORS.ink,
    fontSize: 14,
    fontWeight: "600",
  },
  composer: {
    padding: 14,
    paddingTop: 10,
    backgroundColor: COLORS.panel,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: COLORS.line,
  },
  input: {
    minHeight: 82,
    borderRadius: 18,
    paddingHorizontal: 15,
    paddingVertical: 13,
    color: COLORS.ink,
    fontSize: 16,
    lineHeight: 22,
    backgroundColor: "#f8faf7",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.line,
    textAlignVertical: "top",
  },
  micButton: {
    marginTop: 10,
    height: 48,
    borderRadius: 24,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.accentSoft,
  },
  micText: {
    color: COLORS.accent,
    fontSize: 15,
    fontWeight: "700",
  },
  sendButton: {
    marginTop: 10,
    height: 52,
    borderRadius: 26,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.accent,
  },
  disabledButton: {
    opacity: 0.55,
  },
  sendText: {
    color: "#ffffff",
    fontSize: 16,
    fontWeight: "700",
  },
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 34,
  },
  loadingTitle: {
    marginTop: 22,
    color: COLORS.ink,
    fontSize: 28,
    fontWeight: "700",
    letterSpacing: -0.7,
    textAlign: "center",
  },
  loadingSubtitle: {
    marginTop: 10,
    color: COLORS.muted,
    fontSize: 16,
    lineHeight: 24,
    textAlign: "center",
  },
  scroll: {
    flex: 1,
  },
  page: {
    padding: 16,
    paddingBottom: 120,
  },
  flightCard: {
    marginBottom: 12,
    padding: 16,
    borderRadius: 22,
    backgroundColor: COLORS.panel,
    borderWidth: 1,
    borderColor: COLORS.line,
  },
  flightCardSelected: {
    borderColor: COLORS.accent,
    backgroundColor: "#f3fbf8",
  },
  cardTopLine: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
  },
  flightName: {
    flex: 1,
    color: COLORS.ink,
    fontSize: 16,
    fontWeight: "700",
  },
  selectedText: {
    color: COLORS.accent,
    fontSize: 12,
    fontWeight: "800",
  },
  flightMeta: {
    marginTop: 9,
    color: COLORS.muted,
    fontSize: 14,
    lineHeight: 20,
  },
  flightPrice: {
    marginTop: 14,
    color: COLORS.ink,
    fontSize: 24,
    fontWeight: "800",
    letterSpacing: -0.5,
  },
  linkButton: {
    marginTop: 12,
    paddingHorizontal: 14,
    height: 38,
    borderRadius: 19,
    justifyContent: "center",
    backgroundColor: COLORS.accentSoft,
  },
  linkText: {
    color: COLORS.accent,
    fontSize: 13,
    fontWeight: "700",
  },
  bottomAction: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    padding: 16,
    paddingBottom: 22,
    backgroundColor: "rgba(247,248,244,0.94)",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: COLORS.line,
  },
  primaryButton: {
    height: 56,
    borderRadius: 28,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.accent,
  },
  primaryButtonText: {
    color: "#ffffff",
    fontSize: 16,
    fontWeight: "700",
  },
  emptyPanel: {
    padding: 20,
    borderRadius: 22,
    backgroundColor: COLORS.panel,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.line,
  },
  emptyTitle: {
    color: COLORS.ink,
    fontSize: 18,
    fontWeight: "700",
  },
  emptyText: {
    color: COLORS.muted,
    fontSize: 14,
    lineHeight: 21,
  },
  mapCard: {
    overflow: "hidden",
    borderRadius: 26,
    padding: 14,
    backgroundColor: "#e8f0ec",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "#d5ded8",
  },
  routeLabels: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: -6,
  },
  routeLabel: {
    color: COLORS.ink,
    fontSize: 14,
    fontWeight: "700",
  },
  conditionGrid: {
    flexDirection: "row",
    gap: 10,
    marginTop: 14,
  },
  infoTile: {
    flex: 1,
    minHeight: 112,
    padding: 13,
    borderRadius: 20,
    backgroundColor: COLORS.panel,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.line,
  },
  infoTitle: {
    color: COLORS.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  infoValue: {
    marginTop: 8,
    color: COLORS.ink,
    fontSize: 19,
    fontWeight: "800",
  },
  infoDetail: {
    marginTop: 5,
    color: COLORS.muted,
    fontSize: 12,
    lineHeight: 16,
  },
  section: {
    marginTop: 24,
  },
  sectionTitle: {
    color: COLORS.ink,
    fontSize: 20,
    fontWeight: "800",
    letterSpacing: -0.35,
    marginBottom: 12,
  },
  dayRow: {
    flexDirection: "row",
    padding: 14,
    marginBottom: 10,
    borderRadius: 20,
    backgroundColor: COLORS.panel,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.line,
  },
  dayNumber: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.accent,
  },
  dayNumberText: {
    color: "#ffffff",
    fontSize: 14,
    fontWeight: "800",
  },
  dayCopy: {
    flex: 1,
    marginLeft: 12,
  },
  dayTitle: {
    color: COLORS.ink,
    fontSize: 16,
    fontWeight: "700",
  },
  daySummary: {
    marginTop: 4,
    color: COLORS.muted,
    fontSize: 14,
    lineHeight: 20,
  },
  stayCard: {
    padding: 15,
    marginBottom: 10,
    borderRadius: 20,
    backgroundColor: COLORS.panel,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.line,
  },
  stayName: {
    color: COLORS.ink,
    fontSize: 16,
    fontWeight: "700",
  },
  stayMeta: {
    marginTop: 4,
    color: COLORS.muted,
    fontSize: 13,
  },
  stayPrice: {
    marginTop: 12,
    color: COLORS.accent,
    fontSize: 17,
    fontWeight: "800",
  },
  summaryCard: {
    padding: 15,
    borderRadius: 20,
    backgroundColor: COLORS.panel,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.line,
  },
  summaryTitle: {
    color: COLORS.ink,
    fontSize: 16,
    fontWeight: "700",
  },
  summaryText: {
    marginTop: 6,
    color: COLORS.muted,
    fontSize: 14,
    lineHeight: 21,
  },
  secondaryButton: {
    marginTop: 14,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.accentSoft,
  },
  secondaryButtonText: {
    color: COLORS.accent,
    fontSize: 14,
    fontWeight: "700",
  },
  budgetCard: {
    marginTop: 10,
    padding: 15,
    borderRadius: 20,
    backgroundColor: COLORS.panel,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.line,
  },
  budgetLine: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: COLORS.line,
  },
  budgetLabel: {
    color: COLORS.muted,
    fontSize: 14,
    fontWeight: "600",
  },
  budgetValue: {
    color: COLORS.ink,
    fontSize: 14,
    fontWeight: "700",
  },
  resetButton: {
    marginTop: 26,
    height: 52,
    borderRadius: 26,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: COLORS.line,
    backgroundColor: COLORS.panel,
  },
  resetText: {
    color: COLORS.ink,
    fontSize: 15,
    fontWeight: "700",
  },
  errorBanner: {
    position: "absolute",
    left: 16,
    right: 16,
    bottom: 18,
    padding: 14,
    borderRadius: 18,
    backgroundColor: "#fff0ea",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "#f1bca7",
  },
  errorText: {
    color: COLORS.warning,
    fontSize: 13,
    fontWeight: "600",
  },
});

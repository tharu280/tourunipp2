import { useEffect, useMemo, useState } from "react";

import GetStarted from "./components/GetStarted";
import ChatIntake from "./components/ChatIntake";
import LoadingState from "./components/LoadingState";
import FlightOptions from "./components/FlightOptions";
import PlanDashboard from "./components/PlanDashboard";

import {
  chatApi,
  flightSearchApi,
  planApi,
  dashboardApi,
} from "./api";

import {
  normalizeFlightOptions,
  buildFlightSearchRequest,
  buildPlanRequest,
  isTripHandoff,
  getSessionId,
} from "./helpers";

/* ── Constants ──────────────────────────────────────────────────── */
const FLIGHT_CHIPS = ["Dubai", "12 July 2026", "1 passenger", "Economy", "500,000 LKR"];
const TRIP_CHIPS = ["Colombo", "Kandy", "4 days", "Colombo to kandy"];

/* ── Unique message IDs ─────────────────────────────────────────── */
let _msgId = 0;
function makeMsg(role, text) {
  return {
    id: `m-${Date.now()}-${_msgId++}`,
    role,
    text,
    time: new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }),
  };
}

/* ── Root App ───────────────────────────────────────────────────── */
export default function App() {
  // ── Screen state machine ──────────────────────────────────────
  const [screen, setScreen] = useState("welcome");
  //  welcome | booting | flightChat | flightLoading |
  //  flightOptions | tripChat | planning | results

  // ── Chat state ────────────────────────────────────────────────
  const [flightMessages, setFlightMessages] = useState([]);
  const [tripMessages, setTripMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // ── Session / plan data ───────────────────────────────────────
  const [session, setSession] = useState(null);
  const [flightPlan, setFlightPlan] = useState(null);
  const [selectedFlightIdx, setSelectedFlightIdx] = useState(0);
  const [pendingTripReply, setPendingTripReply] = useState("");
  const [plan, setPlan] = useState(null);
  const [dashboardData, setDashboardData] = useState(null);

  // ── Derived selected flight ───────────────────────────────────
  const selectedFlight = useMemo(() => {
    const opts = normalizeFlightOptions(flightPlan);
    return opts[selectedFlightIdx] || opts[0] || null;
  }, [flightPlan, selectedFlightIdx]);

  useEffect(() => {
    const sessionId = new URLSearchParams(window.location.search).get("session_id");
    if (!sessionId) return;

    let cancelled = false;
    async function loadDashboardSession() {
      setScreen("sessionLoading");
      setError("");
      try {
        const dash = await dashboardApi(sessionId);
        if (cancelled) return;
        setDashboardData(dash);
        setSession({ trip_requirements: dash.trip_requirements || {} });
        setPlan({
          session_id: dash.session_id,
          trip_requirements: dash.trip_requirements || {},
          plan_overview: dash.plan_overview || {},
        });
        setScreen("results");
      } catch (err) {
        if (cancelled) return;
        setError(err.message);
        setScreen("welcome");
      }
    }

    loadDashboardSession();
    return () => {
      cancelled = true;
    };
  }, []);

  /* ── Helpers ────────────────────────────────────────────────── */
  function reset() {
    const url = new URL(window.location);
    url.searchParams.delete("session_id");
    window.history.replaceState({}, document.title, url);
    sessionStorage.clear();
    localStorage.clear();

    setScreen("welcome");
    setFlightMessages([]);
    setTripMessages([]);
    setInput("");
    setBusy(false);
    setError("");
    setSession(null);
    setFlightPlan(null);
    setSelectedFlightIdx(0);
    setPendingTripReply("");
    setPlan(null);
    setDashboardData(null);
  }

  /* ── 1. Get Started → boot chat ─────────────────────────────── */
  async function handleStart() {
    setScreen("booting");
    setError("");
    try {
      const payload = await chatApi({ message: "hey", session: null });
      setSession(payload.session);
      setFlightMessages([
        makeMsg(
          "assistant",
          payload.turn?.assistant_reply ||
            "Hi, I'm TourUni.\nLet's find the best flight to Sri Lanka.\n\nWhere are you departing from?"
        ),
      ]);
      setScreen("flightChat");
    } catch (err) {
      // Even on error, open chat with a fallback greeting
      setFlightMessages([
        makeMsg(
          "assistant",
          "Hi, I'm TourUni.\nLet's find the best flight to Sri Lanka.\n\nWhere are you departing from?"
        ),
      ]);
      setScreen("flightChat");
    }
  }

  /* ── 2. Flight search ───────────────────────────────────────── */
  async function runFlightSearch(nextSession, tripReply) {
    setScreen("flightLoading");
    setError("");
    try {
      const payload = await flightSearchApi(buildFlightSearchRequest(nextSession));
      setFlightPlan(payload);
      setSelectedFlightIdx(0);
      setPendingTripReply(tripReply || "Great! Where should the trip start in Sri Lanka?");
      setScreen("flightOptions");
    } catch (err) {
      setFlightPlan(null);
      setSelectedFlightIdx(0);
      setPendingTripReply(tripReply || "Great! Where should the trip start in Sri Lanka?");
      setError("Flight search failed — you can still continue to plan your trip.");
      setScreen("flightOptions");
    }
  }

  /* ── 3. Send flight chat message ────────────────────────────── */
  async function sendFlightMessage(e) {
    e?.preventDefault?.();
    const clean = input.trim();
    if (!clean || busy) return;
    setInput("");
    setError("");
    setBusy(true);
    setFlightMessages((prev) => [...prev, makeMsg("user", clean)]);

    try {
      const payload = await chatApi({ message: clean, session });
      const nextSession = payload.session;
      const turn = payload.turn || {};
      setSession(nextSession);
      if (turn.assistant_reply) {
        setFlightMessages((prev) => [...prev, makeMsg("assistant", turn.assistant_reply)]);
      }
      setBusy(false);
      if (isTripHandoff(turn)) {
        await runFlightSearch(nextSession, turn.assistant_reply);
      }
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  /* ── 4. Continue to trip chat ───────────────────────────────── */
  function continueToTrip() {
    setInput("");
    setError("");
    setTripMessages([
      makeMsg(
        "assistant",
        pendingTripReply || "Great! Where should your Sri Lanka trip start?"
      ),
    ]);
    setScreen("tripChat");
  }

  /* ── 5. Plan generation ─────────────────────────────────────── */
  async function runPlanner(nextSession) {
    setScreen("planning");
    setError("");
    try {
      const payload = await planApi(buildPlanRequest(nextSession, selectedFlight, flightPlan));
      setPlan(payload);

      // Fetch dashboard enrichment
      const sessionId = getSessionId(payload);
      if (sessionId) {
        try {
          const dash = await dashboardApi(sessionId);
          setDashboardData(dash);
        } catch {
          // Dashboard fetch failure is non-critical
        }
      }
      setScreen("results");
    } catch (err) {
      setError(err.message);
      setScreen("tripChat");
    }
  }

  /* ── 6. Send trip chat message ──────────────────────────────── */
  async function sendTripMessage(e) {
    e?.preventDefault?.();
    const clean = input.trim();
    if (!clean || busy) return;
    setInput("");
    setError("");
    setBusy(true);
    setTripMessages((prev) => [...prev, makeMsg("user", clean)]);

    try {
      const payload = await chatApi({ message: clean, session });
      const nextSession = payload.session;
      const turn = payload.turn || {};
      setSession(nextSession);
      if (turn.assistant_reply) {
        setTripMessages((prev) => [...prev, makeMsg("assistant", turn.assistant_reply)]);
      }
      setBusy(false);
      if (turn.is_complete) await runPlanner(nextSession);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  /* ── Screen router ──────────────────────────────────────────── */

  if (screen === "welcome") {
    return <GetStarted onStart={handleStart} />;
  }

  if (screen === "booting") {
    return (
      <LoadingState
        title="Opening your planner…"
        detail="Preparing your flight intake session."
        steps={["Starting chat", "Connecting backend"]}
      />
    );
  }

  if (screen === "flightLoading") {
    return (
      <LoadingState
        title="Finding your best flights…"
        detail="Checking Colombo arrivals and budget fit."
        steps={["Exact date search", "Week fallback", "Ranking fares"]}
      />
    );
  }

  if (screen === "planning") {
    return (
      <LoadingState
        title="Building your route plan…"
        detail="Selecting routes, stays, crowd windows, weather signals, and budget split."
        steps={["Route selection", "Hotel ranking", "Crowd heatmaps", "Itinerary"]}
      />
    );
  }

  if (screen === "sessionLoading") {
    return (
      <LoadingState
        title="Opening your saved route…"
        detail="Loading the itinerary, crowd signals, map, and budget dashboard."
        steps={["Session", "Route", "Crowd", "Map"]}
      />
    );
  }

  if (screen === "flightOptions") {
    return (
      <FlightOptions
        session={session}
        flightPlan={flightPlan}
        selectedIndex={selectedFlightIdx}
        setSelectedIndex={setSelectedFlightIdx}
        onContinue={continueToTrip}
        onBack={reset}
        error={error}
      />
    );
  }

  if (screen === "results") {
    return (
      <PlanDashboard
        plan={plan}
        dashboardData={dashboardData}
        selectedFlight={selectedFlight}
        session={session}
        onReset={reset}
      />
    );
  }

  /* Flight chat & Trip chat */
  const isTrip = screen === "tripChat";
  return (
    <ChatIntake
      title={isTrip ? "Trip details" : "Flight details"}
      messages={isTrip ? tripMessages : flightMessages}
      chips={isTrip ? TRIP_CHIPS : FLIGHT_CHIPS}
      input={input}
      setInput={setInput}
      onSend={isTrip ? sendTripMessage : sendFlightMessage}
      busy={busy}
      error={error}
      onBack={isTrip ? continueToTrip : reset}
      onReset={reset}
    />
  );
}

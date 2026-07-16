import { useEffect, useMemo, useState } from "react";

import GetStarted from "./components/GetStarted";
import AuthScreen from "./components/AuthScreen";
import AccountScreen from "./components/AccountScreen";
import ChatIntake from "./components/ChatIntake";
import LoadingState from "./components/LoadingState";
import FlightOptions from "./components/FlightOptions";
import PlanDashboard from "./components/PlanDashboard";

import {
  chatApi,
  flightSearchApi,
  flightConfirmApi,
  planApi,
  dashboardApi,
  signupApi,
  loginApi,
  refreshAuthApi,
  logoutApi,
  latestSessionApi,
  setAccessToken,
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
  //  flightOptions | tripChat | planning | results | auth | account

  // ── Authentication ───────────────────────────────────────────
  const [authStatus, setAuthStatus] = useState("checking");
  const [authUser, setAuthUser] = useState(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [latestSessionId, setLatestSessionId] = useState(null);

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
  const [plan, setPlan] = useState(null);
  const [dashboardData, setDashboardData] = useState(null);

  // ── Derived selected flight ───────────────────────────────────
  const selectedFlight = useMemo(() => {
    const opts = normalizeFlightOptions(flightPlan);
    return opts[selectedFlightIdx] || opts[0] || null;
  }, [flightPlan, selectedFlightIdx]);

  useEffect(() => {
    let cancelled = false;

    async function restoreAccount() {
      try {
        const payload = await refreshAuthApi();
        if (cancelled) return;
        setAccessToken(payload.access_token);
        setAuthUser(payload.user);
        try {
          const latest = await latestSessionApi();
          if (cancelled) return;
          setLatestSessionId(latest.session_id || null);
        } catch {
          if (cancelled) return;
          setLatestSessionId(null);
        }
        setAuthStatus("authenticated");
      } catch {
        if (cancelled) return;
        setAccessToken(null);
        setAuthUser(null);
        setLatestSessionId(null);
        setAuthStatus("guest");
      }
    }

    restoreAccount();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const sessionId = new URLSearchParams(window.location.search).get("session_id");
    if (!sessionId || authStatus === "checking") return;
    if (authStatus !== "authenticated") {
      setScreen("auth");
      return;
    }

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
        setLatestSessionId(dash.session_id);
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
  }, [authStatus]);

  /* ── Helpers ────────────────────────────────────────────────── */
  function putSessionInUrl(sessionId) {
    const url = new URL(window.location);
    if (sessionId) url.searchParams.set("session_id", sessionId);
    else url.searchParams.delete("session_id");
    window.history.replaceState({}, document.title, url);
  }

  async function openSavedSession(sessionId) {
    setScreen("sessionLoading");
    setError("");
    const dash = await dashboardApi(sessionId);
    setDashboardData(dash);
    setSession({ trip_requirements: dash.trip_requirements || {} });
    setPlan({
      session_id: dash.session_id,
      trip_requirements: dash.trip_requirements || {},
      plan_overview: dash.plan_overview || {},
    });
    setLatestSessionId(dash.session_id);
    putSessionInUrl(dash.session_id);
    setScreen("results");
  }

  function resetPlannerState() {
    putSessionInUrl(null);

    setScreen("welcome");
    setFlightMessages([]);
    setTripMessages([]);
    setInput("");
    setBusy(false);
    setError("");
    setSession(null);
    setFlightPlan(null);
    setSelectedFlightIdx(0);
    setPlan(null);
    setDashboardData(null);
  }

  async function startNewPlanner() {
    resetPlannerState();
    await handleStart();
  }

  async function startAuthenticatedPlanner() {
    if (authStatus !== "authenticated") {
      setScreen("auth");
      return;
    }
    if (latestSessionId) {
      try {
        await openSavedSession(latestSessionId);
        return;
      } catch {
        setLatestSessionId(null);
      }
    }
    await handleStart();
  }

  async function submitAuth({ mode, name, email, password }) {
    const payload = mode === "signup"
      ? await signupApi({ name: name.trim(), email: email.trim(), password })
      : await loginApi({ email: email.trim(), password });

    setAccessToken(payload.access_token);
    setAuthUser(payload.user);
    let latestId = null;
    try {
      const latest = await latestSessionApi();
      latestId = latest.session_id || null;
    } catch {
      latestId = null;
    }
    setLatestSessionId(latestId);
    setAuthStatus("authenticated");

    const sessionId = new URLSearchParams(window.location.search).get("session_id");
    if (!sessionId) {
      if (latestId) await openSavedSession(latestId);
      else await handleStart();
    }
  }

  async function logout() {
    if (authBusy) return;
    setAuthBusy(true);
    try {
      await logoutApi();
      setAccessToken(null);
      setAuthUser(null);
      setLatestSessionId(null);
      setAuthStatus("guest");
      resetPlannerState();
    } finally {
      setAuthBusy(false);
    }
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
  async function runFlightSearch(nextSession) {
    setScreen("flightLoading");
    setError("");
    try {
      const payload = await flightSearchApi(buildFlightSearchRequest(nextSession));
      setFlightPlan(payload);
      setSelectedFlightIdx(0);
      setScreen("flightOptions");
    } catch (err) {
      setFlightPlan(null);
      setSelectedFlightIdx(0);
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
      if (isTripHandoff(turn)) {
        // Flight intake stops at selection; trip intake remains locked until
        // the user confirms an option on the next screen.
        setBusy(false);
        await runFlightSearch(nextSession);
        return;
      }
      if (turn.assistant_reply) {
        setFlightMessages((prev) => [...prev, makeMsg("assistant", turn.assistant_reply)]);
      }
      setBusy(false);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  /* ── 4. Continue to trip chat ───────────────────────────────── */
  async function continueToTrip() {
    if (busy) return;
    setInput("");
    setError("");
    setBusy(true);
    try {
      const payload = await flightConfirmApi({
        session,
        selected_flight: selectedFlight,
        continue_without_live_fare: !selectedFlight,
      });
      const nextSession = payload.session;
      const turn = payload.turn || {};
      setSession(nextSession);
      setTripMessages([
        makeMsg(
          "assistant",
          turn.assistant_reply || "Great! Where should your Sri Lanka trip start?"
        ),
      ]);
      setScreen("tripChat");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
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
        setLatestSessionId(sessionId);
        putSessionInUrl(sessionId);
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

  if (authStatus === "checking") {
    return (
      <LoadingState
        title="Opening TourUni…"
        detail="Restoring your secure session."
        steps={["Account", "Planner"]}
      />
    );
  }

  if (screen === "auth") {
    return (
      <AuthScreen
        onBack={() => setScreen("welcome")}
        onSubmit={submitAuth}
      />
    );
  }

  if (screen === "account") {
    return (
      <AccountScreen
        user={authUser}
        onBack={() => setScreen("welcome")}
        onLogout={logout}
        busy={authBusy}
      />
    );
  }

  if (screen === "welcome") {
    return (
      <GetStarted
        onStart={startAuthenticatedPlanner}
        onProfile={() => setScreen(authUser ? "account" : "auth")}
        user={authUser}
        hasSavedTrip={Boolean(latestSessionId)}
      />
    );
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
        busy={busy}
        onBack={resetPlannerState}
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
        onReset={startNewPlanner}
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
      onBack={isTrip ? continueToTrip : resetPlannerState}
      onReset={resetPlannerState}
    />
  );
}

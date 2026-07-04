/* ── TourUni API Client ─────────────────────────────────────────────
   All backend calls go through this module.
   Base URL: VITE_API_BASE_URL env var (defaults to HF Space)
 ──────────────────────────────────────────────────────────────────── */

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  "https://tourismproject-backendtouruni.hf.space"
).replace(/\/$/, "");

async function request(method, path, body) {
  const options = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) options.body = JSON.stringify(body);

  const res = await fetch(`${API_BASE}${path}`, options);
  const payload = await res.json().catch(() => ({}));

  if (!res.ok) {
    const detail = payload?.detail || res.statusText || "Request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

/* ── Named API functions ─────────────────────────────────────────── */

export const chatApi = (body) => request("POST", "/chat", body);

export const flightSearchApi = (body) => request("POST", "/flights/search", body);

export const planApi = (body) => request("POST", "/plan", body);

export const dashboardApi = (sessionId) =>
  request("GET", `/sessions/${sessionId}/dashboard`);

export const chatbotContextApi = (sessionId) =>
  request("GET", `/sessions/${sessionId}/chatbot-context`);

export const emotionTargetsApi = (sessionId) =>
  request("GET", `/sessions/${sessionId}/emotion-targets`);

export const refreshIntelApi = (sessionId) =>
  request("POST", `/sessions/${sessionId}/refresh-intelligence`);

export const emotionCheckinApi = (sessionId, body) =>
  request("POST", `/sessions/${sessionId}/emotion-checkins`, body);

export const startOfDayMoodCheckinApi = (sessionId, body) =>
  emotionCheckinApi(sessionId, { ...body, checkin_type: "start_of_day" });

export const startOfDayMoodCheckinImageApi = async (sessionId, formData) => {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/emotion-checkins/image`, {
    method: "POST",
    body: formData,
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = payload?.detail || res.statusText || "Request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
};

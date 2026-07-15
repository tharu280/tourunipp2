/* ── TourUni API Client ─────────────────────────────────────────────
   All backend calls go through this module.
   Base URL: VITE_API_BASE_URL env var. Production defaults to the
   same-origin Vercel proxy so secure auth cookies work on mobile Safari.
 ──────────────────────────────────────────────────────────────────── */

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:7860" : "/api")
).replace(/\/$/, "");

let accessToken = null;

export function setAccessToken(token) {
  accessToken = token || null;
}

async function request(method, path, body, retryAuth = true) {
  const options = {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "include",
  };
  if (accessToken) options.headers.Authorization = `Bearer ${accessToken}`;
  if (body !== undefined) options.body = JSON.stringify(body);

  const res = await fetch(`${API_BASE}${path}`, options);
  const payload = await res.json().catch(() => ({}));

  if (res.status === 401 && retryAuth && !path.startsWith("/auth/")) {
    try {
      const refreshed = await request("POST", "/auth/refresh", undefined, false);
      setAccessToken(refreshed.access_token);
      return request(method, path, body, false);
    } catch {
      setAccessToken(null);
    }
  }

  if (!res.ok) {
    const detail = payload?.detail || res.statusText || "Request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

/* ── Named API functions ─────────────────────────────────────────── */

export const chatApi = (body) => request("POST", "/chat", body);

export const signupApi = (body) => request("POST", "/auth/signup", body);

export const loginApi = (body) => request("POST", "/auth/login", body);

export const refreshAuthApi = () => request("POST", "/auth/refresh");

export const logoutApi = () => request("POST", "/auth/logout");

export const currentUserApi = () => request("GET", "/auth/me");

export const flightSearchApi = (body) => request("POST", "/flights/search", body);

export const flightConfirmApi = (body) => request("POST", "/flights/confirm", body);

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
  return requestForm(
    `/sessions/${sessionId}/emotion-checkins/image`,
    formData,
  );
};

async function requestForm(path, formData, retryAuth = true) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    credentials: "include",
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
    body: formData,
  });
  const payload = await res.json().catch(() => ({}));

  if (res.status === 401 && retryAuth) {
    try {
      const refreshed = await request("POST", "/auth/refresh", undefined, false);
      setAccessToken(refreshed.access_token);
      return requestForm(path, formData, false);
    } catch {
      setAccessToken(null);
    }
  }

  if (!res.ok) {
    const detail = payload?.detail || res.statusText || "Request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

import { useState } from "react";

import heroImg from "/sri_lanka_hero.jpg";


function BackIcon() {
  return (
    <svg width="21" height="21" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m15 18-6-6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}


export default function AuthScreen({ onBack, onSubmit, initialMode = "login" }) {
  const [mode, setMode] = useState(initialMode);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isSignup = mode === "signup";

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await onSubmit({ mode, name, email, password });
    } catch (err) {
      setError(err.message || "We couldn't sign you in. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  function switchMode(nextMode) {
    setMode(nextMode);
    setError("");
  }

  return (
    <main className="auth-screen animate-slide-up">
      <div className="auth-visual" style={{ backgroundImage: `url(${heroImg})` }} aria-hidden="true" />
      <div className="auth-visual-shade" aria-hidden="true" />

      <button className="auth-back" onClick={onBack} type="button" aria-label="Back">
        <BackIcon />
      </button>

      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="auth-brand" aria-hidden="true">TU</div>
        <p className="auth-eyebrow">TourUni</p>
        <h1 id="auth-title">{isSignup ? "Create your travel account" : "Welcome back"}</h1>
        <p className="auth-intro">
          {isSignup
            ? "Save your Sri Lanka plans and reopen them securely on any device."
            : "Sign in to continue planning your Sri Lanka journey."}
        </p>

        <div className="auth-mode-switch" role="tablist" aria-label="Account action">
          <button
            className={mode === "login" ? "is-active" : ""}
            onClick={() => switchMode("login")}
            type="button"
            role="tab"
            aria-selected={mode === "login"}
          >
            Sign in
          </button>
          <button
            className={mode === "signup" ? "is-active" : ""}
            onClick={() => switchMode("signup")}
            type="button"
            role="tab"
            aria-selected={mode === "signup"}
          >
            Create account
          </button>
        </div>

        <form className="auth-form" onSubmit={submit}>
          {isSignup && (
            <label>
              <span>Name</span>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoComplete="name"
                minLength={2}
                maxLength={80}
                placeholder="Your name"
                required
              />
            </label>
          )}
          <label>
            <span>Email</span>
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              inputMode="email"
              autoComplete="email"
              maxLength={254}
              placeholder="you@example.com"
              required
            />
          </label>
          <label>
            <span>Password</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              autoComplete={isSignup ? "new-password" : "current-password"}
              minLength={isSignup ? 10 : 1}
              maxLength={128}
              placeholder={isSignup ? "At least 10 characters" : "Your password"}
              required
            />
          </label>

          {error && <p className="auth-error" role="alert">{error}</p>}

          <button className="auth-submit" type="submit" disabled={busy}>
            {busy ? "Please wait…" : isSignup ? "Create account" : "Sign in"}
          </button>
        </form>

        <p className="auth-security-note">Secure sign-in. Your password is never stored as plain text.</p>
      </section>
    </main>
  );
}

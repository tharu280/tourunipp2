export default function AccountScreen({ user, onBack, onLogout, busy }) {
  const initial = (user?.name || user?.email || "T").trim().charAt(0).toUpperCase();

  return (
    <main className="account-screen animate-slide-up">
      <header className="account-header">
        <button type="button" onClick={onBack} aria-label="Back">Back</button>
        <span>Account</span>
        <span aria-hidden="true" />
      </header>
      <section className="account-card">
        <div className="account-avatar" aria-hidden="true">{initial}</div>
        <h1>{user?.name}</h1>
        <p>{user?.email}</p>
        <div className="account-session-state">
          <span aria-hidden="true" />
          Secure session active
        </div>
        <button type="button" onClick={onLogout} disabled={busy}>
          {busy ? "Signing out…" : "Sign out"}
        </button>
      </section>
    </main>
  );
}

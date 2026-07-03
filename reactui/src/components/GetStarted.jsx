import heroImg from "/sri_lanka_hero.jpg";

export default function GetStarted({ onStart }) {
  return (
    <main className="gs-screen animate-slide-up" id="screen-get-started">
      {/* Hero background */}
      <div
        className="gs-hero"
        style={{ backgroundImage: `url(${heroImg})` }}
        role="img"
        aria-label="Sri Lanka scenic nine arch bridge with train through tea hills"
      />
      <div className="gs-overlay" aria-hidden="true" />

      {/* Content */}
      <div className="gs-content">
        <h1 className="gs-wordmark">TourUni</h1>
        <p className="gs-subtitle">Your AI travel assistant<br/>for Sri Lanka.</p>

        <button
          id="btn-get-started"
          className="gs-cta"
          onClick={onStart}
          type="button"
        >
          Get started
        </button>

        <p className="gs-footer">Plan smarter. Travel better.</p>
      </div>
    </main>
  );
}

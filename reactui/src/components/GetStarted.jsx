import React from 'react';
import heroImg from "/sri_lanka_hero.jpg";

const MenuIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="4" y1="12" x2="16" y2="12"></line>
    <line x1="4" y1="6" x2="20" y2="6"></line>
    <line x1="4" y1="18" x2="20" y2="18"></line>
  </svg>
);

const ProfileIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path>
    <circle cx="12" cy="7" r="4"></circle>
  </svg>
);

const AiSparkleIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>
  </svg>
);

const ArrowRightIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <line x1="5" y1="12" x2="19" y2="12"></line>
    <polyline points="12 5 19 12 12 19"></polyline>
  </svg>
);

const ShieldIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
    <polyline points="9 12 11 14 15 10"></polyline>
  </svg>
);

export default function GetStarted({ onStart, onProfile, user }) {
  return (
    <main className="gs-screen animate-slide-up" id="screen-get-started">
      <div
        className="gs-hero"
        style={{ backgroundImage: `url(${heroImg})` }}
        role="img"
        aria-label="Sri Lanka scenic mountains"
      />
      
      <div className="gs-overlay-top" aria-hidden="true" />
      <div className="gs-overlay-bottom" aria-hidden="true" />

      <div className="gs-top-nav">
        <button className="gs-icon-btn" aria-label="Menu" type="button">
          <MenuIcon />
        </button>
        <button className="gs-icon-btn" aria-label={user ? "Open account" : "Sign in"} type="button" onClick={onProfile}>
          {user ? <span className="gs-user-initial">{user.name?.charAt(0)?.toUpperCase() || "T"}</span> : <ProfileIcon />}
        </button>
      </div>

      <div className="gs-content">
        <div className="gs-text-container">
          <p className="gs-pre-title">The</p>
          <h1 className="gs-title">Tourbot</h1>
          <p className="gs-subtitle">
            Your AI travel assistant<br/>
            for <span className="gs-highlight">Sri Lanka</span>.
          </p>
        </div>

        <button
          id="btn-get-started"
          className="gs-cta"
          onClick={onStart}
          type="button"
        >
          <span className="gs-cta-icon-left"><AiSparkleIcon /></span>
          <span className="gs-cta-text">Get started</span>
          <span className="gs-cta-icon-right"><ArrowRightIcon /></span>
        </button>

        <div className="gs-trust-line">
          <ShieldIcon />
          <span>Plan smarter. Travel better.</span>
        </div>
      </div>
    </main>
  );
}

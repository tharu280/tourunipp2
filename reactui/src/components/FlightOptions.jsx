import { normalizeFlightOptions, getBookingLink, estimateFlightHandoff, formatMoney, titleCase } from "../helpers";

/* ── SVG Icons ─────────────────────────────────────────────────── */
function IconBack() {
  return (
    <svg viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 18l-6-6 6-6" />
    </svg>
  );
}

function IconCheck() {
  return (
    <svg viewBox="0 0 24 24" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" stroke="currentColor" fill="none" style={{width:12,height:12}}>
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function IconExternalLink() {
  return (
    <svg viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" stroke="currentColor" fill="none">
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

/* ── Airline initials fallback ──────────────────────────────────── */
function airlineInitials(name) {
  if (!name) return "✈";
  const words = name.trim().split(/\s+/);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

/* ── Airline logo color ─────────────────────────────────────────── */
function airlineColor(name) {
  if (!name) return "#075F55";
  const lc = name.toLowerCase();
  if (lc.includes("sri") || lc.includes("uul")) return "#007DC5";
  if (lc.includes("emirates")) return "#D71921";
  if (lc.includes("fly") || lc.includes("flydubai")) return "#E31837";
  if (lc.includes("arabia")) return "#FF6600";
  if (lc.includes("qatar")) return "#5C1344";
  if (lc.includes("etihad")) return "#BD8B2E";
  if (lc.includes("air india")) return "#E0272C";
  return "#075F55";
}

/* ── Parse flight time display ──────────────────────────────────── */
function parseFlightDisplay(flight, req) {
  const depAt = flight.departure_at || flight.departure_time || flight.departure_date || "";
  const arrAt = flight.arrival_at || flight.arrival_time || "";
  let depCode = flight.from_airport || flight.origin_code || flight.from || "";
  let arrCode = flight.to_airport || flight.destination_code || flight.to || "CMB";
  const depDate = req?.flight_departure_date || "";

  // Format time from ISO or HH:MM
  function fmtTime(str) {
    if (!str) return null;
    // ISO: 2026-07-20T02:20:00
    const iso = str.match(/T(\d{2}:\d{2})/);
    if (iso) return iso[1];
    // HH:MM
    const hm = str.match(/(\d{2}:\d{2})/);
    if (hm) return hm[1];
    return null;
  }

  const depTime = fmtTime(depAt);
  const arrTime = fmtTime(arrAt);

  // Duration
  let duration = null;
  if (flight.duration_hours) {
    const h = Math.floor(Number(flight.duration_hours));
    const m = Math.round((Number(flight.duration_hours) - h) * 60);
    duration = h > 0 ? `${h}h ${m > 0 ? m + "m" : ""}`.trim() : `${m}m`;
  } else if (flight.duration_minutes) {
    const tot = Number(flight.duration_minutes);
    const h = Math.floor(tot / 60);
    const m = tot % 60;
    duration = h > 0 ? `${h}h ${m > 0 ? m + "m" : ""}`.trim() : `${m}m`;
  }

  const stops = flight.stops !== undefined ? Number(flight.stops) : null;
  const stopsLabel = stops === 0 ? "Non-stop" : stops === 1 ? "1 stop" : stops !== null ? `${stops} stops` : "Non-stop";

  return { depTime, arrTime, depCode, arrCode, depDate, duration, stopsLabel };
}

/* ── Single Flight Card ─────────────────────────────────────────── */
function FlightCard({ flight, index, selected, onSelect, req }) {
  const bookingLink = getBookingLink(flight);
  const { depTime, arrTime, depCode, arrCode, depDate, duration, stopsLabel } =
    parseFlightDisplay(flight, req);
  const airline = flight.airline || flight.airline_code || "Flight";
  const price = flight.price;
  const currency = flight.currency || "USD";
  const passengers = Number(req?.flight_passengers || 1);
  const color = airlineColor(airline);

  return (
    <article
      className={`flight-card${selected ? " selected" : ""}`}
      onClick={() => onSelect(index)}
      role="radio"
      aria-checked={selected}
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === " " || e.key === "Enter") onSelect(index); }}
    >
      {/* Best value badge */}
      {selected && (
        <div className="flight-badge">
          <IconCheck />
          Best value selected
        </div>
      )}

      {/* Top row: airline + price */}
      <div className="flight-card-top">
        <div className="flight-airline-row">
          <div className="airline-logo" style={{ color }}>
            {airlineInitials(airline)}
          </div>
          <span className="airline-name">{airline}</span>
        </div>
        <div className="flight-price-col">
          {price ? (
            <>
              <div className="flight-price">{currency} {Number(price).toLocaleString()}</div>
              <div className="flight-price-note">Total for {passengers}</div>
            </>
          ) : (
            <div className="flight-price" style={{color:"var(--text-3)"}}>—</div>
          )}
        </div>
      </div>

      {/* Route row */}
      <div className="flight-route-row">
        <div>
          <div className="flight-port">{depCode || "DXB"}</div>
          <div className="flight-port-time">{depTime || "—"}</div>
        </div>

        <div className="flight-connector">
          <span className="flight-duration">{duration || "—"}</span>
          <div className="flight-line" />
          <span className="flight-stops-label">{stopsLabel}</span>
        </div>

        <div className="flight-port-right">
          <div className="flight-port">{arrCode}</div>
          <div className="flight-port-time">{arrTime || "—"}</div>
        </div>
      </div>

      {/* Booking link */}
      {bookingLink && (
        <a
          className="flight-booking-link"
          href={bookingLink}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
        >
          View details &amp; booking
          <IconExternalLink />
        </a>
      )}
    </article>
  );
}

/* ── Main FlightOptions Screen ──────────────────────────────────── */
export default function FlightOptions({
  session,
  flightPlan,
  selectedIndex,
  setSelectedIndex,
  onContinue,
  onBack,
  error,
  busy = false,
}) {
  const req = session?.trip_requirements || {};
  const options = normalizeFlightOptions(flightPlan);
  const origin = req.flight_origin || "Origin";
  const date = req.flight_departure_date || "";
  const passengers = req.flight_passengers || 1;

  const selected = options[selectedIndex] || options[0] || null;
  const { estimatedFlightLkr, remainingBudgetLkr } = estimateFlightHandoff(
    selected,
    req.total_budget_lkr
  );

  // Placeholder when no results
  const displayOptions =
    options.length > 0
      ? options
      : [{ airline: "No live fare available", price: null }];

  return (
    <div className="flight-screen" id="screen-flight-options">
      {/* Navigation */}
      <nav className="flight-nav">
        <button className="flight-nav-back" onClick={onBack} type="button" aria-label="Go back">
          <IconBack />
        </button>
        <div className="flight-nav-center">
          <div className="flight-nav-title">Select your flight</div>
          <div className="flight-nav-sub">
            {origin} → Colombo (CMB) · {date}
          </div>
        </div>
        <div className="flight-nav-info" />
      </nav>

      {/* Scrollable content */}
      <div className="flight-content" role="radiogroup" aria-label="Flight options">
        {error && (
          <div className="chat-error" role="alert" style={{ marginBottom: 16 }}>
            {error}
          </div>
        )}

        {/* Best value (first / selected) */}
        {displayOptions.length > 0 && (
          <>
            <p className="flight-section-label" style={{ marginBottom: 12 }}>
              {options.length > 0 ? "Best value" : "Flight search"}
            </p>
            <FlightCard
              flight={displayOptions[0]}
              index={0}
              selected={selectedIndex === 0}
              onSelect={setSelectedIndex}
              req={req}
            />
          </>
        )}

        {/* Other options */}
        {displayOptions.length > 1 && (
          <>
            <p className="flight-section-label" style={{ marginTop: 20, marginBottom: 12 }}>
              Other options
            </p>
            {displayOptions.slice(1).map((flight, i) => (
              <FlightCard
                key={`flight-${i + 1}`}
                flight={flight}
                index={i + 1}
                selected={selectedIndex === i + 1}
                onSelect={setSelectedIndex}
                req={req}
              />
            ))}
          </>
        )}

        {/* Budget handoff info */}
        {(estimatedFlightLkr || remainingBudgetLkr) && (
          <div style={{
            marginTop: 20,
            padding: "14px 16px",
            background: "var(--green-light)",
            borderRadius: "var(--r-lg)",
            borderLeft: "3px solid var(--green)",
          }}>
            {estimatedFlightLkr && (
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ fontSize: 13, color: "var(--text-2)" }}>Est. flight cost</span>
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--green)" }}>
                  {formatMoney(estimatedFlightLkr)}
                </span>
              </div>
            )}
            {remainingBudgetLkr && (
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 13, color: "var(--text-2)" }}>Remaining for trip</span>
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
                  {formatMoney(remainingBudgetLkr)}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Sticky bottom action */}
      <div className="flight-sticky-bar">
        <button
          id="btn-use-flight"
          className="flight-sticky-btn"
          onClick={onContinue}
          type="button"
          disabled={busy}
        >
          {busy
            ? "Confirming flight…"
            : selected
              ? "Use selected flight"
              : "Continue without live fare"}
        </button>
      </div>
    </div>
  );
}

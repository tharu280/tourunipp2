import { getBookingLink } from "../helpers";

function IconExternalLink() {
  return (
    <svg viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" stroke="currentColor" fill="none" style={{width:14,height:14}}>
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

export default function FlightSummary({ flight, passengers }) {
  if (!flight) return null;

  const airline = flight.airline || flight.airline_code || "Flight";
  const price = flight.price;
  const currency = flight.currency || "USD";
  const bookingLink = getBookingLink(flight);

  const depCode = flight.from_airport || flight.origin_code || flight.from || "DXB";
  const arrCode = flight.to_airport || flight.destination_code || flight.to || "CMB";

  function fmtTime(str) {
    if (!str) return null;
    const iso = str.match(/T(\d{2}:\d{2})/);
    if (iso) return iso[1];
    const hm = str.match(/(\d{2}:\d{2})/);
    if (hm) return hm[1];
    return null;
  }

  const depTime = fmtTime(flight.departure_at || flight.departure_time || "");
  const arrTime = fmtTime(flight.arrival_at || flight.arrival_time || "");
  const date = flight.departure_at
    ? new Date(flight.departure_at).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" })
    : flight.departure_date || "";

  return (
    <div className="flight-summary-card" id="section-flight-summary">
      <div className="fs-route-row">
        <div>
          <div className="fs-airline">{airline}</div>
          <div className="fs-route">
            {depCode} {depTime ? `${depTime} → ` : "→ "}
            {arrCode} {arrTime || ""}
          </div>
          {date && <div className="fs-date">{date} · {passengers > 1 ? `${passengers} passengers` : "1 passenger"}</div>}
        </div>
        {price && (
          <div className="fs-price-col">
            <div className="fs-price">{currency} {Number(price).toLocaleString()}</div>
            <div className="fs-price-note">Total for {passengers || 1}</div>
          </div>
        )}
      </div>

      {bookingLink ? (
        <a
          href={bookingLink}
          target="_blank"
          rel="noopener noreferrer"
          className="fs-view-btn"
          style={{ display: "inline-flex" }}
        >
          View ticket
          <IconExternalLink />
        </a>
      ) : (
        <button
          className="fs-view-btn"
          type="button"
          disabled
          style={{ opacity: 0.5 }}
          aria-label="No booking link available"
        >
          View ticket
          <IconExternalLink />
        </button>
      )}
    </div>
  );
}

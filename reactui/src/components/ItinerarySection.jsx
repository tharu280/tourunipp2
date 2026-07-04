import { getItineraryRows, formatDuration, segmentDistanceLabel } from "../helpers";

function IconChevronRight() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 18l6-6-6-6" />
    </svg>
  );
}

export default function ItinerarySection({ plan }) {
  const rows = getItineraryRows(plan);

  if (!rows.length) {
    return (
      <div className="empty-state">
        Itinerary details will appear once your route is generated.
      </div>
    );
  }

  return (
    <div className="itinerary-list" id="section-itinerary">
      {rows.map(({ segment: seg, day, label, highlights, isFallback }, i) => {
        const dayNum = day || i + 1;
        const distance = segmentDistanceLabel(seg) || formatDuration(seg.segment_duration_seconds);

        return (
          <div key={`day-${dayNum}-${i}`} className="itinerary-row">
            {/* Number Badge */}
            <div className="itinerary-badge" aria-hidden="true">
              <span className="itinerary-badge-label">Day</span>
              <span className="itinerary-badge-num">{dayNum}</span>
            </div>

            {/* Info */}
            <div className="itinerary-info">
              <div className="itinerary-label">{label}</div>
              {(distance || highlights.length > 0) && (
                <div className="itinerary-meta">
                  {distance && <div className="itinerary-distance" style={{marginBottom: 6, fontSize: 13, color: "var(--text-3)"}}>{distance}</div>}
                  {highlights.length > 0 && (
                    <ul className={isFallback ? "itinerary-attrs-list fallback" : "itinerary-attrs-list"} style={{
                      listStyle: "none", margin: 0, padding: 0, 
                      fontSize: 14, color: isFallback ? "var(--text-3)" : "var(--text-2)",
                      fontStyle: isFallback ? "italic" : "normal",
                      lineHeight: 1.4
                    }}>
                      {highlights.map((hlt, idx) => (
                        <li key={idx} style={{ 
                          display: "flex", alignItems: "flex-start", gap: 6, marginBottom: 4 
                        }}>
                          {!isFallback && <span style={{ color: "var(--text-3)", marginTop: -2 }}>•</span>}
                          <span style={{ 
                            wordBreak: "break-word", 
                            overflowWrap: "break-word" 
                          }}>{hlt}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>

            {/* Chevron */}
            <div className="itinerary-chevron">
              <IconChevronRight />
            </div>
          </div>
        );
      })}
    </div>
  );
}

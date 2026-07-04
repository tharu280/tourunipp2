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
      {rows.map(({ segment: seg, day, label, highlights, isRepeated }, i) => {
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
                  {distance && <span className="itinerary-distance">{distance}</span>}
                  {distance && highlights.length > 0 && <span className="itinerary-dot-sep" />}
                  {highlights.length > 0 && (
                    <span className={isRepeated ? "itinerary-attrs itinerary-attrs-muted" : "itinerary-attrs"}>
                      {highlights.join(", ")}
                    </span>
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

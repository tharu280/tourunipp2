import { getRouteSegments, getAttractions, formatDuration, segmentDistanceLabel } from "../helpers";

function IconChevronRight() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 18l6-6-6-6" />
    </svg>
  );
}

export default function ItinerarySection({ plan }) {
  const segments = getRouteSegments(plan);
  const attractions = getAttractions(plan);

  // Group attractions by day
  const attractionsByDay = {};
  for (const attr of attractions) {
    const key = attr.day ?? "?";
    if (!attractionsByDay[key]) attractionsByDay[key] = [];
    attractionsByDay[key].push(attr.name);
  }

  if (!segments.length) {
    return (
      <div className="empty-state">
        Itinerary details will appear once your route is generated.
      </div>
    );
  }

  return (
    <div className="itinerary-list" id="section-itinerary">
      {segments.map((seg, i) => {
        const dayNum = seg.day || i + 1;
        const label = seg.day_label || `Day ${dayNum}`;
        const dayAttractions = attractionsByDay[dayNum] || [];
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
              {(distance || dayAttractions.length > 0) && (
                <div className="itinerary-meta">
                  {distance && <span className="itinerary-distance">{distance}</span>}
                  {distance && dayAttractions.length > 0 && <span className="itinerary-dot-sep" />}
                  {dayAttractions.length > 0 && (
                    <span className="itinerary-attrs">{dayAttractions.join(", ")}</span>
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

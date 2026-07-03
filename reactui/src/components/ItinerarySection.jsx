import { getRouteSegments, getAttractions, formatDuration, segmentDistanceLabel } from "../helpers";

const PLACE_ICONS = ["🏰","🏔️","🌊","🌿","🕌","🗿","🏖️","🌄","🏛️","🌺"];

function placeIcon(index) {
  return PLACE_ICONS[index % PLACE_ICONS.length];
}

function IconChevronRight() {
  return (
    <svg viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" stroke="currentColor" fill="none">
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
        const duration = formatDuration(seg.segment_duration_seconds);
        const distance = segmentDistanceLabel(seg);

        return (
          <div key={`day-${dayNum}-${i}`} className="itinerary-row">
            {/* Thumbnail */}
            <div className="itinerary-thumb" aria-hidden="true">
              {placeIcon(i)}
            </div>

            {/* Info */}
            <div className="itinerary-info">
              <div className="itinerary-day">Day {dayNum}</div>
              <div className="itinerary-label">{label}</div>
              <div className="itinerary-attractions">
                {dayAttractions.length > 0
                  ? dayAttractions.slice(0, 2).join(" · ")
                  : [duration, distance].filter(Boolean).join(" · ") || "Route segment"}
              </div>
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

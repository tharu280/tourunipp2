import { useEffect, useMemo } from "react";
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import { divIcon } from "leaflet";
import "leaflet/dist/leaflet.css";

const DEFAULT_CENTER = [7.8731, 80.7718];

function validPoint(target) {
  const latitude = Number(target?.latitude);
  const longitude = Number(target?.longitude);
  return Number.isFinite(latitude) && Number.isFinite(longitude)
    ? [latitude, longitude]
    : null;
}

function FitJourney({ points }) {
  const map = useMap();
  useEffect(() => {
    if (points.length > 1) map.fitBounds(points, { padding: [32, 32], maxZoom: 12 });
    else if (points.length === 1) map.setView(points[0], 13);
  }, [map, points]);
  return null;
}

function markerIcon({ state, label }) {
  return divIcon({
    className: `mood-route-marker mood-route-marker-${state}`,
    html: `<span>${label}</span>`,
    iconSize: [38, 38],
    iconAnchor: [19, 19],
  });
}

export default function MoodJourneyMap({ targets, activeIndex, checkins, emotionEmoji }) {
  const mappedTargets = useMemo(
    () => targets.map((target, index) => ({ target, index, point: validPoint(target) })).filter((item) => item.point),
    [targets],
  );
  const checkinByTarget = useMemo(() => {
    const index = new Map();
    checkins.forEach((checkin) => {
      if (checkin?.attraction_id) index.set(`id:${checkin.attraction_id}`, checkin);
      if (checkin?.attraction_name) {
        index.set(`name:${String(checkin.attraction_name).trim().toLowerCase()}`, checkin);
      }
    });
    return index;
  }, [checkins]);
  const points = useMemo(() => mappedTargets.map((item) => item.point), [mappedTargets]);
  const center = points[0] || DEFAULT_CENTER;

  if (!mappedTargets.length) {
    return <div className="mood-journey-map-empty">Checkpoint coordinates are unavailable for this route.</div>;
  }

  return (
    <div className="mood-journey-map" aria-label="Simulated mood checkpoint route">
      <MapContainer
        center={center}
        zoom={9}
        scrollWheelZoom={false}
        zoomControl={false}
        attributionControl={false}
        style={{ height: "100%", width: "100%" }}
      >
        <FitJourney points={points} />
        <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
        {points.length > 1 && (
          <Polyline positions={points} pathOptions={{ color: "#45d7aa", weight: 3, opacity: 0.72, dashArray: "7 8" }} />
        )}
        {mappedTargets.map(({ target, index, point }) => {
          const saved = checkinByTarget.get(`id:${target.attraction_id}`)
            || checkinByTarget.get(`name:${String(target.attraction_name || "").trim().toLowerCase()}`);
          const state = index === activeIndex ? "current" : saved ? "visited" : "future";
          const label = saved ? emotionEmoji(saved.emotion_label) : index + 1;
          return (
            <Marker key={target.attraction_id || `${target.day}-${target.order}`} position={point} icon={markerIcon({ state, label })}>
              <Tooltip direction="top" offset={[0, -18]}>
                <strong>{target.attraction_name}</strong><br />
                Day {target.day}{saved ? ` · ${saved.emotion_label}` : index === activeIndex ? " · current checkpoint" : " · upcoming"}
              </Tooltip>
            </Marker>
          );
        })}
      </MapContainer>
      <div className="mood-map-caption">
        <strong>Mood checkpoint route</strong>
        <span>Demo progression follows planned attractions, not live GPS.</span>
      </div>
    </div>
  );
}

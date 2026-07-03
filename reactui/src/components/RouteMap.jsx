import { useEffect, useMemo } from "react";
import { MapContainer, TileLayer, Marker, Polyline, Popup, CircleMarker, useMap } from "react-leaflet";
import { divIcon } from "leaflet";
import "leaflet/dist/leaflet.css";
import { getPolyline, getStops } from "../helpers";

const SRI_LANKA_CENTER = [7.8731, 80.7718];

function FitRoute({ points }) {
  const map = useMap();
  useEffect(() => {
    if (points.length > 1) {
      map.fitBounds(points, { padding: [24, 24], maxZoom: 10 });
    }
  }, [map, points]);
  return null;
}

function pressureColor(level, score) {
  const normalized = String(level || "").toLowerCase();
  const numeric = Number(score);
  if (normalized === "high" || numeric >= 68) return "#EF4444";
  if (normalized === "medium" || normalized === "moderate" || numeric >= 36) return "#F59E0B";
  return "#10B981";
}

export default function RouteMap({ plan }) {
  const polyline = useMemo(() => getPolyline(plan), [plan]);
  const stops = useMemo(() => getStops(plan), [plan]);
  const pressurePoints = useMemo(
    () =>
      (
        plan?.crowd?.attraction_pressure ||
        plan?.crowd_signals?.attraction_pressure ||
        []
      ).slice(0, 12),
    [plan]
  );
  const center = polyline[0] || SRI_LANKA_CENTER;

  const pinIcon = divIcon({
    className: "map-pin",
    html: "",
    iconSize: [12, 12],
    iconAnchor: [6, 6],
  });

  return (
    <div className="map-card" id="section-map" aria-label="Route map">
      <MapContainer
        center={center}
        zoom={8}
        scrollWheelZoom={false}
        zoomControl={false}
        attributionControl={false}
        style={{ height: "100%", width: "100%" }}
      >
        <FitRoute points={polyline} />
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          attribution='© OpenStreetMap © CARTO'
        />

        {polyline.length > 1 && (
          <Polyline
            positions={polyline}
            pathOptions={{ color: "#075F55", weight: 3, opacity: 0.9 }}
          />
        )}

        {stops.map((stop, i) => (
          <Marker
            key={`stop-${i}`}
            position={[stop.point.lat, stop.point.lng]}
            icon={pinIcon}
          >
            <Popup>{stop.name}</Popup>
          </Marker>
        ))}

        {/* Crowd pressure circles */}
        {pressurePoints.map((item, i) => {
            const lat = item?.location?.lat || item?.lat;
            const lng = item?.location?.lng || item?.lng;
            if (!lat || !lng) return null;
            const color = pressureColor(item.pressure_level || item.level, item.pressure_score || item.score);
            return (
              <CircleMarker
                key={`crowd-${i}`}
                center={[lat, lng]}
                radius={7}
                pathOptions={{
                  color,
                  fillColor: color,
                  fillOpacity: 0.28,
                  weight: 1.5,
                }}
              >
                <Popup>
                  <strong>{item.name || item.attraction_name || "Crowd signal"}</strong>
                  <br />
                  {item.pressure_level || item.level || "pressure"} · {item.pressure_score ?? item.score ?? "—"}
                </Popup>
              </CircleMarker>
            );
          })}
      </MapContainer>
    </div>
  );
}

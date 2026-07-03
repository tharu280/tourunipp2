import { useMemo } from "react";
import { MapContainer, TileLayer, Marker, Polyline, Popup, CircleMarker } from "react-leaflet";
import { divIcon } from "leaflet";
import "leaflet/dist/leaflet.css";
import { getPolyline, getStops } from "../helpers";

const SRI_LANKA_CENTER = [7.8731, 80.7718];

export default function RouteMap({ plan }) {
  const polyline = useMemo(() => getPolyline(plan), [plan]);
  const stops = useMemo(() => getStops(plan), [plan]);
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
        {(plan?.crowd_signals?.attraction_pressure || [])
          .slice(0, 6)
          .map((item, i) => {
            const lat = item?.location?.lat || item?.lat;
            const lng = item?.location?.lng || item?.lng;
            if (!lat || !lng) return null;
            return (
              <CircleMarker
                key={`crowd-${i}`}
                center={[lat, lng]}
                radius={8}
                pathOptions={{
                  color: "#075F55",
                  fillColor: "#EF4444",
                  fillOpacity: 0.35,
                  weight: 1.5,
                }}
              >
                <Popup>{item.name || item.attraction_name || "Crowd signal"}</Popup>
              </CircleMarker>
            );
          })}
      </MapContainer>
    </div>
  );
}

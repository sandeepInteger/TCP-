import { useEffect, useMemo } from "react";
import {
  MapContainer,
  TileLayer,
  LayersControl,
  CircleMarker,
  Marker,
  Polyline,
  Polygon,
  Popup,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6"];
// Leaflet's default line weight is 3px — 80% thinner than that is 0.6px.
const LINE_WEIGHT = 0.6;

function colorFor(idx) {
  return COLORS[idx % COLORS.length];
}

function FitBounds({ bounds }) {
  const map = useMap();
  useEffect(() => {
    if (bounds.length > 0) {
      map.fitBounds(bounds, { padding: [30, 30] });
    }
  }, [bounds, map]);
  return null;
}

function FlyToSelected({ latLng }) {
  const map = useMap();
  useEffect(() => {
    if (latLng) {
      map.flyTo(latLng, Math.max(map.getZoom(), 18), { duration: 0.6 });
    }
  }, [latLng, map]);
  return null;
}

export default function MapPreview({ result, selectedPoint }) {
  const allLatLngs = useMemo(
    () =>
      result.features.flatMap((f) => f.points.map((p) => [p.lat, p.lon])),
    [result]
  );

  const selectedLatLng = useMemo(() => {
    if (!selectedPoint) return null;
    const point = result.features[selectedPoint.featureIdx]?.points[selectedPoint.pointIdx];
    return point ? [point.lat, point.lon] : null;
  }, [result, selectedPoint]);

  if (allLatLngs.length === 0) {
    return <p className="map-empty">No coordinates to display.</p>;
  }

  return (
    <MapContainer center={allLatLngs[0]} zoom={16} className="map-preview">
      <LayersControl position="topright">
        <LayersControl.BaseLayer checked name="High-Res (NAIP, US)">
          <TileLayer
            attribution="Source: Esri, USDA FSA (NAIP, 60cm-1m resolution)"
            url="https://naip.maptiles.arcgis.com/arcgis/rest/services/NAIP/MapServer/tile/{z}/{y}/{x}"
            maxZoom={20}
            maxNativeZoom={18}
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Satellite (worldwide)">
          <TileLayer
            attribution="Tiles &copy; Esri"
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            maxZoom={19}
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Streets">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
        </LayersControl.BaseLayer>
      </LayersControl>
      <FitBounds bounds={allLatLngs} />
      {result.features.map((feature, idx) => {
        const latLngs = feature.points.map((p) => [p.lat, p.lon]);
        const color = colorFor(idx);

        if (feature.geometry_type === "Point") {
          const iconSrc = feature.icon?.data_uri ?? feature.icon?.href;
          const icon = iconSrc
            ? L.icon({
                iconUrl: iconSrc,
                iconSize: [24, 24],
                iconAnchor: [12, 12],
              })
            : null;

          return latLngs.map((ll, i) =>
            icon ? (
              <Marker key={`${idx}-${i}`} position={ll} icon={icon}>
                <Popup>{feature.name || "(unnamed)"}</Popup>
              </Marker>
            ) : (
              <CircleMarker key={`${idx}-${i}`} center={ll} radius={7} color={color}>
                <Popup>{feature.name || "(unnamed)"}</Popup>
              </CircleMarker>
            )
          );
        }
        if (feature.geometry_type === "Polygon") {
          return (
            <Polygon key={idx} positions={latLngs} color={color} weight={LINE_WEIGHT}>
              <Popup>{feature.name || "(unnamed)"}</Popup>
            </Polygon>
          );
        }
        return (
          <Polyline key={idx} positions={latLngs} color={color} weight={LINE_WEIGHT}>
            <Popup>{feature.name || "(unnamed)"}</Popup>
          </Polyline>
        );
      })}
      {selectedLatLng && (
        <CircleMarker
          center={selectedLatLng}
          radius={16}
          pathOptions={{ color: "#ffd400", weight: 3, fillOpacity: 0 }}
        />
      )}
      <FlyToSelected latLng={selectedLatLng} />
    </MapContainer>
  );
}

import { useEffect, useMemo, useState } from "react";
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

// Small drag handle rendered on each vertex of an editable line — see
// the "vertex-handle" CSS class in App.css for its actual look.
const VERTEX_ICON = L.divIcon({ className: "vertex-handle", iconSize: [10, 10], iconAnchor: [5, 5] });

function colorFor(idx) {
  return COLORS[idx % COLORS.length];
}

// Fits a Catmull-Rom spline through the real vertices and samples it
// densely for display only — a rendering aid for source data that's
// digitized with few vertices on a curve, not a source of new position
// data. The actual points (and their drag handles) are untouched, so
// dragging a vertex and the exported DXF still use the real, un-smoothed
// coordinates.
function smoothPath(points, segmentsPerSpan = 8) {
  if (points.length < 3) return points;
  const at = (i) => points[Math.max(0, Math.min(points.length - 1, i))];
  const smoothed = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [p0, p1, p2, p3] = [at(i - 1), at(i), at(i + 1), at(i + 2)];
    const steps = i === points.length - 2 ? segmentsPerSpan + 1 : segmentsPerSpan;
    for (let s = 0; s < steps; s++) {
      const t = s / segmentsPerSpan;
      const t2 = t * t;
      const t3 = t2 * t;
      smoothed.push([catmullRom(p0[0], p1[0], p2[0], p3[0], t, t2, t3), catmullRom(p0[1], p1[1], p2[1], p3[1], t, t2, t3)]);
    }
  }
  return smoothed;
}

function catmullRom(v0, v1, v2, v3, t, t2, t3) {
  return 0.5 * (2 * v1 + (-v0 + v2) * t + (2 * v0 - 5 * v1 + 4 * v2 - v3) * t2 + (-v0 + 3 * v1 - 3 * v2 + v3) * t3);
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

export default function MapPreview({ result, selectedPoint, editableFrom = Infinity, onPointDrag }) {
  const [smooth, setSmooth] = useState(false);

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
    <div className="map-preview-wrap">
      <label className="map-smooth-toggle" title="Draws a smoothed curve through the real vertices for display only — the underlying points, drag handles, and exported DXF are unaffected.">
        <input type="checkbox" checked={smooth} onChange={(e) => setSmooth(e.target.checked)} />
        Smooth curves
      </label>
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
              <Polygon key={idx} positions={smooth ? smoothPath(latLngs) : latLngs} color={color} weight={LINE_WEIGHT}>
                <Popup>{feature.name || "(unnamed)"}</Popup>
              </Polygon>
            );
          }
          const isEditable = idx >= editableFrom;
          return [
            <Polyline key={idx} positions={smooth ? smoothPath(latLngs) : latLngs} color={color} weight={LINE_WEIGHT}>
              <Popup>{feature.name || "(unnamed)"}</Popup>
            </Polyline>,
            ...(isEditable
              ? latLngs.map((ll, i) => (
                  <Marker
                    key={`vertex-${idx}-${i}`}
                    position={ll}
                    icon={VERTEX_ICON}
                    draggable
                    eventHandlers={{
                      dragend: (e) => {
                        const { lat, lng } = e.target.getLatLng();
                        onPointDrag?.(idx, i, lat, lng);
                      },
                    }}
                  />
                ))
              : []),
          ];
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
    </div>
  );
}

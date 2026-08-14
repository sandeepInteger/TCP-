import { useState } from "react";

function fmt(n) {
  return Number(n).toFixed(3);
}

function formatFeatureType(feature) {
  if (!feature.feature_type) return null;
  const label = feature.feature_type
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  return feature.speed_mph != null ? `${label} — ${feature.speed_mph} MPH` : label;
}

export default function ResultsTable({
  result,
  selectedPoint,
  onSelectPoint,
  dimensionsBySpeed,
  layerAttributes,
  featureAssignments,
  onAssignmentChange,
}) {
  const [expanded, setExpanded] = useState(() => new Set());

  const toggle = (idx) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  };

  return (
    <div className="results-table">
      <div className="results-meta">
        <span>
          <strong>{result.filename}</strong>
        </span>
        <span>{result.feature_count} feature(s)</span>
        <span>
          {result.source_crs} &rarr; {result.target_crs}
        </span>
      </div>

      <table>
        <thead>
          <tr>
            <th></th>
            <th>Icon</th>
            <th>Name</th>
            <th>Type</th>
            <th>Geometry</th>
            <th>Points</th>
            <th>Layer</th>
          </tr>
        </thead>
        <tbody>
          {result.features.map((feature, idx) => (
            <FeatureRows
              key={idx}
              feature={feature}
              idx={idx}
              isExpanded={expanded.has(idx)}
              onToggle={() => toggle(idx)}
              selectedPoint={selectedPoint}
              onSelectPoint={onSelectPoint}
              dimensions={feature.speed_mph != null ? dimensionsBySpeed?.[feature.speed_mph] : null}
              layerAttributes={layerAttributes}
              assignment={featureAssignments?.[idx]}
              onAssignmentChange={(attribute) => onAssignmentChange?.(idx, attribute)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function IconThumb({ icon }) {
  const [failed, setFailed] = useState(false);
  const src = icon?.data_uri ?? icon?.href;

  if (!src || failed) {
    return <span className="icon-thumb-empty" title={icon?.href}>—</span>;
  }

  return <img className="icon-thumb" src={src} alt="" title={icon.href} onError={() => setFailed(true)} />;
}

function DimensionsPanel({ dimensions }) {
  if (!dimensions) return null;
  if (dimensions.error) {
    return <p className="dimensions-error">Dimension lookup failed: {dimensions.error}</p>;
  }
  const d = dimensions.data;
  const rows = [
    ["Buffer", d.buffer_length],
    ["Taper", d.taper_length],
    ["Sign A", d.sign_spacing_A],
    ["Sign B", d.sign_spacing_B],
    ["Sign C", d.sign_spacing_C],
    ["Cone (taper)", d.cone_spacing_taper],
    ["Cone (tangent)", d.cone_spacing_tangent],
  ];
  return (
    <div className="dimensions-panel">
      {rows.map(([label, value]) => (
        <span key={label} className="dimensions-chip">
          <strong>{label}:</strong> {value != null ? `${value} ft` : "—"}
        </span>
      ))}
    </div>
  );
}

function FeatureRows({
  feature,
  idx,
  isExpanded,
  onToggle,
  selectedPoint,
  onSelectPoint,
  dimensions,
  layerAttributes,
  assignment,
  onAssignmentChange,
}) {
  const isFeatureSelected = selectedPoint?.featureIdx === idx;

  const handleRowClick = () => {
    onToggle();
    if (feature.points.length > 0) {
      onSelectPoint?.({ featureIdx: idx, pointIdx: 0 });
    }
  };

  return (
    <>
      <tr className={`feature-row ${isFeatureSelected ? "feature-row-selected" : ""}`} onClick={handleRowClick}>
        <td>{isExpanded ? "▾" : "▸"}</td>
        <td>
          <IconThumb icon={feature.icon} />
        </td>
        <td>{feature.name || <em>(unnamed)</em>}</td>
        <td>
          {formatFeatureType(feature) ? (
            <span className="badge badge-feature-type">{formatFeatureType(feature)}</span>
          ) : (
            <span className="icon-thumb-empty">—</span>
          )}
        </td>
        <td>
          <span className={`badge badge-${feature.geometry_type.toLowerCase()}`}>
            {feature.geometry_type}
          </span>
        </td>
        <td>{feature.points.length}</td>
        <td onClick={(e) => e.stopPropagation()}>
          <select
            className="layer-select"
            value={assignment?.attribute ?? ""}
            onChange={(e) => onAssignmentChange?.(e.target.value)}
          >
            <option value="">— none —</option>
            {layerAttributes?.map((attr) => (
              <option key={attr} value={attr}>
                {attr}
              </option>
            ))}
          </select>
        </td>
      </tr>
      {isExpanded && (
        <tr className="points-row">
          <td></td>
          <td colSpan={6}>
            <DimensionsPanel dimensions={dimensions} />
            <table className="points-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Lon</th>
                  <th>Lat</th>
                  <th>X</th>
                  <th>Y</th>
                </tr>
              </thead>
              <tbody>
                {feature.points.map((p, i) => {
                  const isPointSelected = isFeatureSelected && selectedPoint?.pointIdx === i;
                  return (
                    <tr
                      key={i}
                      className={isPointSelected ? "point-row-selected" : ""}
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectPoint?.({ featureIdx: idx, pointIdx: i });
                      }}
                    >
                      <td>{i + 1}</td>
                      <td>{fmt(p.lon)}</td>
                      <td>{fmt(p.lat)}</td>
                      <td>{fmt(p.x)}</td>
                      <td>{fmt(p.y)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}

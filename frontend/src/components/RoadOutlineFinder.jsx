import { useEffect, useState } from "react";

export default function RoadOutlineFinder({ onSearch, onConfirm, prefill, defaultLengthFt, defaultDimensions }) {
  const [lon, setLon] = useState("");
  const [lat, setLat] = useState("");
  const [roadNameHint, setRoadNameHint] = useState("");
  const [lengthFt, setLengthFt] = useState(200);
  const [lengthTouched, setLengthTouched] = useState(false);
  const [widthFt, setWidthFt] = useState("");
  const [dims, setDims] = useState(null);
  const [dimsTouched, setDimsTouched] = useState(false);

  // Auto-fills Length from the job's computed Buffer+Taper+Sign A/B/C as
  // soon as it's available — e.g. typing a coordinate straight from a work
  // order, with no row ever selected in the table. Stops once the user
  // edits the field themselves, so it never overwrites an intentional
  // value with a stale or unrelated default.
  useEffect(() => {
    if (!lengthTouched && defaultLengthFt != null) {
      setLengthFt(defaultLengthFt);
    }
  }, [defaultLengthFt, lengthTouched]);

  // Same idea as Length, but for the actual Buffer/Taper/Sign/Cone values
  // used to place the TCP zones — so the zones get drawn automatically
  // using the job's own computed dimensions, with no separate input
  // needed here. "Use selected point" locks this to that point's specific
  // dimensions instead (see useSelectedPoint below).
  useEffect(() => {
    if (!dimsTouched && defaultDimensions != null) {
      setDims(defaultDimensions);
    }
  }, [defaultDimensions, dimsTouched]);

  const [candidates, setCandidates] = useState(null);
  const [selectedName, setSelectedName] = useState(null);

  const [searching, setSearching] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState(null);
  const [lastResult, setLastResult] = useState(null);

  const useSelectedPoint = () => {
    if (!prefill) return;
    setLon(String(prefill.lon));
    setLat(String(prefill.lat));
    // lengthFt is the pre-summed Buffer+Taper+Sign A/B/C for the selected
    // point's speed (see App.jsx's prefillPoint) — only set when that sum
    // is actually available, so an unrelated point doesn't clobber
    // whatever length the user already typed.
    if (prefill.lengthFt != null) {
      setLengthFt(prefill.lengthFt);
      setLengthTouched(true);
    }
    if (prefill.dims != null) {
      setDims(prefill.dims);
      setDimsTouched(true);
    }
  };

  const handleSearch = async () => {
    setError(null);
    setLastResult(null);
    setCandidates(null);
    setSelectedName(null);
    setSearching(true);
    try {
      const data = await onSearch({ lon: Number(lon), lat: Number(lat), roadNameHint });
      setCandidates(data.candidates);
      if (data.candidates.length > 0) setSelectedName(data.candidates[0].name);
    } catch (err) {
      setError(err.message);
    } finally {
      setSearching(false);
    }
  };

  const handleConfirm = async () => {
    setError(null);
    setConfirming(true);
    try {
      const data = await onConfirm({
        lon: Number(lon),
        lat: Number(lat),
        lengthFt: Number(lengthFt),
        roadName: selectedName,
        widthFt: widthFt === "" ? undefined : Number(widthFt),
        dims,
      });
      setLastResult(data);
      setCandidates(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setConfirming(false);
    }
  };

  return (
    <div className="road-outline-finder">
      <div className="road-outline-header">
        <h3>Find road outline from a coordinate</h3>
        {prefill && (
          <button className="btn-secondary" type="button" onClick={useSelectedPoint}>
            Use selected point
          </button>
        )}
      </div>
      <div className="road-outline-inputs">
        <label>
          <span>Longitude</span>
          <input type="number" step="any" value={lon} onChange={(e) => setLon(e.target.value)} placeholder="-121.4944" />
        </label>
        <label>
          <span>Latitude</span>
          <input type="number" step="any" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="38.5816" />
        </label>
        <label>
          <span>Expected road name (optional)</span>
          <input
            type="text"
            value={roadNameHint}
            onChange={(e) => setRoadNameHint(e.target.value)}
            placeholder="e.g. Frontage Rd"
          />
        </label>
        <button className="btn-primary" type="button" onClick={handleSearch} disabled={searching || lon === "" || lat === ""}>
          {searching ? "Searching..." : "Search nearby roads"}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {candidates && candidates.length > 0 && (
        <div className="road-outline-candidates">
          <p className="road-outline-candidates-hint">
            {candidates.length} road{candidates.length > 1 ? "s" : ""} found nearby — confirm which one is correct
            before drawing anything:
          </p>
          <ul>
            {candidates.map((c) => (
              <li key={c.name ?? "(unnamed)"}>
                <label>
                  <input
                    type="radio"
                    name="road-candidate"
                    checked={selectedName === c.name}
                    onChange={() => setSelectedName(c.name)}
                  />
                  <span className="road-outline-candidate-name">{c.name || "(unnamed road)"}</span>
                  <span className="road-outline-candidate-distance">{c.offset_ft.toFixed(1)} ft away</span>
                </label>
              </li>
            ))}
          </ul>
          <div className="road-outline-confirm-row">
            <label>
              <span>Length (ft)</span>
              <input
                type="number"
                min="0"
                step="1"
                value={lengthFt}
                onChange={(e) => {
                  setLengthFt(e.target.value);
                  setLengthTouched(true);
                }}
              />
            </label>
            <label>
              <span>Road width (ft, optional)</span>
              <input
                type="number"
                min="0"
                step="1"
                value={widthFt}
                onChange={(e) => setWidthFt(e.target.value)}
                placeholder="e.g. 30"
              />
            </label>
            <button className="btn-primary" type="button" onClick={handleConfirm} disabled={confirming || !selectedName}>
              {confirming ? "Building outline..." : "Use this road"}
            </button>
          </div>
        </div>
      )}

      {lastResult && (
        <p className="road-outline-summary">
          Snapped to <strong>{lastResult.road_name || "(unnamed road)"}</strong>, {lastResult.offset_ft.toFixed(1)} ft
          from the given point, on the <strong>{lastResult.side}</strong> side — extended{" "}
          <strong>{lastResult.direction}</strong>.{" "}
          {lastResult.buffer_zone
            ? "Road outline, edges, buffer/taper zones, signs, cones, and your work point all added as new features below — assign each a layer to include it in the DXF."
            : lastResult.left_edge
              ? "Centerline plus left/right edges added as new features below — assign each a layer to include it in the DXF."
              : "Added as a new feature below — assign it a layer to include it in the DXF."}
        </p>
      )}
    </div>
  );
}

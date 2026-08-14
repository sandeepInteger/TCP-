import { useEffect, useMemo, useState } from "react";
import UploadPanel from "./components/UploadPanel";
import ResultsTable from "./components/ResultsTable";
import MapPreview from "./components/MapPreview";
import SetupControls from "./components/SetupControls";
import RoadOutlineFinder from "./components/RoadOutlineFinder";
import ThemeToggle from "./components/ThemeToggle";
import {
  uploadKmlFile,
  fetchSetupTypes,
  getDimensions,
  fetchLayerAttributes,
  generateDxf,
  findRoadCandidates,
  findRoadOutline,
} from "./api/client";
import "./App.css";

const FALLBACK_SETUP_TYPES = ["merge", "shift", "shoulder"];
const FALLBACK_LAYER_ATTRIBUTES = [
  "CENTER_LINE",
  "LANE_DASH",
  "SIDEWALK",
  "DRIVEWAY",
  "STRIPING",
  "PAINTED_MEDIAN",
  "RAISED_MEDIAN",
  "EX_ARROW",
  "CURB",
];

// A dims object is only usable for zone placement once Buffer, Taper,
// and Sign A/B/C all have real values — e.g. 20 mph leaves these blank
// in the reference table, so there's nothing to place stations from.
function completeDimensions(dims) {
  if (!dims) return undefined;
  const parts = [dims.buffer_length, dims.taper_length, dims.sign_spacing_A, dims.sign_spacing_B, dims.sign_spacing_C];
  return parts.every((v) => v != null) ? dims : undefined;
}

// Buffer + Taper + Sign A/B/C is the total advance-warning distance
// upstream of the work point (see geometry_engine.centerline.
// place_tcp_stations), plus a fixed 100 ft margin on top — summed here so
// the user doesn't have to add these up (or remember the extra margin) by
// hand before typing a length. Cone spacing is deliberately excluded from
// the sum itself: it's the gap *between* cones inside the taper/tangent
// zones already counted, not extra distance.
const EXTRA_LENGTH_MARGIN_FT = 100;

function sumAdvanceWarningFt(dims) {
  const d = completeDimensions(dims);
  if (!d) return undefined;
  return d.buffer_length + d.taper_length + d.sign_spacing_A + d.sign_spacing_B + d.sign_spacing_C + EXTRA_LENGTH_MARGIN_FT;
}

// Reasonable starting guess per geometry type, since nothing in the KMZ
// itself says "this line is a curb vs. a centerline" — the user can
// override per feature in the table before generating a DXF.
function defaultAssignment(feature) {
  if (feature.geometry_type === "LineString") return { attribute: "CENTER_LINE", closed: false };
  if (feature.geometry_type === "Polygon") return { attribute: "PAINTED_MEDIAN", closed: true };
  return { attribute: "", closed: false };
}

function App() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [pendingResult, setPendingResult] = useState(null);
  const [selectedPoint, setSelectedPoint] = useState(null);

  const [setupTypes, setSetupTypes] = useState(FALLBACK_SETUP_TYPES);
  const [setupType, setSetupType] = useState("shift");
  const [workAreaWidthFt, setWorkAreaWidthFt] = useState(12);
  const [dimensionsBySpeed, setDimensionsBySpeed] = useState({});

  const [layerAttributes, setLayerAttributes] = useState(FALLBACK_LAYER_ATTRIBUTES);
  const [featureAssignments, setFeatureAssignments] = useState([]);
  const [dxfError, setDxfError] = useState(null);

  // Road-outline features (looked up from an external road source, see
  // /api/road-outline) are kept separate from `result`/`featureAssignments`
  // rather than merged into them directly — result's own useEffect resets
  // featureAssignments to defaults on every change, which would wipe out
  // manual layer assignments already made on uploaded KMZ features every
  // time a new road outline is added. viewResult/viewAssignments below
  // combine the two only for rendering/download.
  const [roadOutlineFeatures, setRoadOutlineFeatures] = useState([]);
  const [roadOutlineAssignments, setRoadOutlineAssignments] = useState([]);

  useEffect(() => {
    fetchSetupTypes()
      .then((types) => {
        if (types?.length) setSetupTypes(types);
      })
      .catch(() => {
        // Fall back to the hardcoded list already in state — the dropdown
        // still works, it just can't reflect a future new setup type.
      });
    fetchLayerAttributes()
      .then((attrs) => {
        if (attrs?.length) setLayerAttributes(attrs);
      })
      .catch(() => {
        // Same fallback reasoning as setup types above.
      });
  }, []);

  useEffect(() => {
    setFeatureAssignments(result ? result.features.map(defaultAssignment) : []);
  }, [result]);

  useEffect(() => {
    if (!result) {
      setDimensionsBySpeed({});
      return;
    }
    const speeds = [
      ...new Set(
        result.features
          .filter((f) => f.feature_type === "speed_limit_sign" && f.speed_mph != null)
          .map((f) => f.speed_mph)
      ),
    ];
    if (speeds.length === 0) {
      setDimensionsBySpeed({});
      return;
    }

    let cancelled = false;
    Promise.all(
      speeds.map((speed) =>
        getDimensions(speed, setupType, workAreaWidthFt)
          .then((data) => [speed, { data, error: null }])
          .catch((err) => [speed, { data: null, error: err.message }])
      )
    ).then((entries) => {
      if (!cancelled) setDimensionsBySpeed(Object.fromEntries(entries));
    });

    return () => {
      cancelled = true;
    };
  }, [result, setupType, workAreaWidthFt]);

  // What's actually rendered/downloaded: the uploaded KMZ's features plus
  // any road-outline features found so far, so both flow through the same
  // table/map/DXF-download path without ResultsTable or MapPreview needing
  // to know two kinds of feature exist.
  const viewResult = useMemo(() => {
    if (!result && roadOutlineFeatures.length === 0) return null;
    const base = result ?? {
      filename: "road-outline",
      source_crs: roadOutlineFeatures[0]?.source_crs ?? "EPSG:4326",
      target_crs: roadOutlineFeatures[0]?.target_crs ?? "EPSG:3435",
      features: [],
    };
    const features = [...base.features, ...roadOutlineFeatures];
    return { ...base, features, feature_count: features.length };
  }, [result, roadOutlineFeatures]);

  const viewAssignments = useMemo(
    () => [...featureAssignments, ...roadOutlineAssignments],
    [featureAssignments, roadOutlineAssignments]
  );

  const uploadedFeatureCount = result?.features.length ?? 0;

  const handleSearchRoadCandidates = ({ lon, lat, roadNameHint }) =>
    findRoadCandidates({ lon, lat, roadNameHint });

  const handleFindRoadOutline = async ({ lon, lat, lengthFt, roadName, widthFt, dims }) => {
    const data = await findRoadOutline({ lon, lat, lengthFt, roadName, widthFt, dims });
    const label = data.road_name || "nearest road";
    const baseFeature = {
      icon: null,
      speed_mph: null,
      source_crs: data.source_crs,
      target_crs: data.target_crs,
    };

    const newFeatures = [
      { ...baseFeature, name: `Road outline — ${label}`, geometry_type: "LineString", points: data.points, feature_type: "road_outline" },
    ];
    const newAssignments = [{ attribute: "CENTER_LINE", closed: false }];

    if (data.left_edge && data.right_edge) {
      newFeatures.push(
        { ...baseFeature, name: `Left edge — ${label}`, geometry_type: "LineString", points: data.left_edge, feature_type: "road_edge" },
        { ...baseFeature, name: `Right edge — ${label}`, geometry_type: "LineString", points: data.right_edge, feature_type: "road_edge" }
      );
      newAssignments.push({ attribute: "CURB", closed: false }, { attribute: "CURB", closed: false });
    }

    if (data.buffer_zone) {
      newFeatures.push({ ...baseFeature, name: "Buffer zone", geometry_type: "LineString", points: data.buffer_zone, feature_type: "buffer_zone" });
      newAssignments.push({ attribute: "BUFFER_ZONE", closed: false });
    }
    if (data.taper_zone) {
      newFeatures.push({ ...baseFeature, name: "Taper zone", geometry_type: "LineString", points: data.taper_zone, feature_type: "taper_zone" });
      newAssignments.push({ attribute: "TAPER_ZONE", closed: false });
    }
    ["sign_1", "sign_2", "sign_3"].forEach((key, i) => {
      if (data[key]) {
        newFeatures.push({
          ...baseFeature,
          name: `Sign ${String.fromCharCode(65 + i)}`,
          geometry_type: "Point",
          points: [data[key]],
          feature_type: "sign",
        });
        newAssignments.push({ attribute: "SIGN", closed: false });
      }
    });
    (data.cones_tangent ?? []).forEach((pt, i) => {
      newFeatures.push({ ...baseFeature, name: `Cone (tangent) ${i + 1}`, geometry_type: "Point", points: [pt], feature_type: "cone" });
      newAssignments.push({ attribute: "CONE", closed: false });
    });
    (data.cones_taper ?? []).forEach((pt, i) => {
      newFeatures.push({ ...baseFeature, name: `Cone (taper) ${i + 1}`, geometry_type: "Point", points: [pt], feature_type: "cone" });
      newAssignments.push({ attribute: "CONE", closed: false });
    });
    if (data.input_point) {
      newFeatures.push({ ...baseFeature, name: "Work point", geometry_type: "Point", points: [data.input_point], feature_type: "work_point" });
      newAssignments.push({ attribute: "WORK_POINT", closed: false });
    }

    setRoadOutlineFeatures((prev) => [...prev, ...newFeatures]);
    setRoadOutlineAssignments((prev) => [...prev, ...newAssignments]);
    return data;
  };

  const handleFileSelected = async (file) => {
    setLoading(true);
    setError(null);
    setPendingResult(null);
    try {
      const data = await uploadKmlFile(file);
      setPendingResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleContinue = () => {
    if (!pendingResult) return;
    setResult(pendingResult);
    setPendingResult(null);
    setSelectedPoint(null);
  };

  const handleReset = () => {
    setResult(null);
    setSelectedPoint(null);
    setRoadOutlineFeatures([]);
    setRoadOutlineAssignments([]);
  };

  const handleAssignmentChange = (idx, attribute) => {
    if (idx < uploadedFeatureCount) {
      setFeatureAssignments((prev) =>
        prev.map((a, i) => (i === idx ? { ...a, attribute } : a))
      );
    } else {
      const roadIdx = idx - uploadedFeatureCount;
      setRoadOutlineAssignments((prev) =>
        prev.map((a, i) => (i === roadIdx ? { ...a, attribute } : a))
      );
    }
  };

  const handleDownloadDxf = async () => {
    setDxfError(null);
    const dxfFeatures = viewResult.features
      .map((feature, idx) => ({ feature, assignment: viewAssignments[idx] }))
      .filter(({ assignment }) => assignment?.attribute)
      .map(({ feature, assignment }) => ({
        attribute: assignment.attribute,
        points: feature.points.map((p) => [p.x, p.y]),
        closed: assignment.closed,
      }));

    if (dxfFeatures.length === 0) {
      setDxfError("Assign at least one feature to a layer (see the Layer column) before generating a DXF.");
      return;
    }

    try {
      const blob = await generateDxf(dxfFeatures);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${viewResult.filename.replace(/\.[^.]+$/, "")}.dxf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDxfError(err.message);
    }
  };

  const prefillPoint = useMemo(() => {
    if (!selectedPoint || !viewResult) return null;
    const feature = viewResult.features[selectedPoint.featureIdx];
    const point = feature?.points[selectedPoint.pointIdx];
    if (!point) return null;

    const dims = feature?.speed_mph != null ? dimensionsBySpeed[feature.speed_mph]?.data : null;
    return { lon: point.lon, lat: point.lat, lengthFt: sumAdvanceWarningFt(dims), dims: completeDimensions(dims) };
  }, [selectedPoint, viewResult, dimensionsBySpeed]);

  // Falls back to whichever speed's dimensions are available first, so
  // the Length field (and the Buffer/Taper/Sign/Cone zone placement) starts
  // pre-filled even if the user never selects a specific row/point — e.g.
  // typing a coordinate straight from a work order rather than clicking
  // through the table.
  const defaultDimensions = useMemo(() => {
    for (const entry of Object.values(dimensionsBySpeed)) {
      const dims = completeDimensions(entry?.data);
      if (dims) return dims;
    }
    return undefined;
  }, [dimensionsBySpeed]);

  const defaultLengthFt = useMemo(() => sumAdvanceWarningFt(defaultDimensions), [defaultDimensions]);

  if (!viewResult) {
    return (
      <div className="upload-screen">
        <div className="theme-toggle-floating">
          <ThemeToggle />
        </div>
        <div className="upload-screen-inner">
          <UploadPanel
            onFileSelected={handleFileSelected}
            loading={loading}
            ready={pendingResult != null}
            onContinue={handleContinue}
          />
          {error && <div className="error-banner">{error}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-shell">
      <nav className="navbar">
        <div className="navbar-brand">
          <span className="navbar-brand-title">Traffic Control Plan</span>
          <span className="navbar-brand-filename">{viewResult.filename}</span>
        </div>
        <div className="navbar-actions">
          <button className="btn-primary" onClick={handleDownloadDxf}>
            Download DXF
          </button>
          <button className="btn-secondary" onClick={handleReset}>
            Upload another file
          </button>
          <ThemeToggle />
        </div>
      </nav>

      <div className="workspace-body">
        <aside className="workspace-sidebar">
          {error && <div className="error-banner">{error}</div>}
          {dxfError && <div className="error-banner">{dxfError}</div>}

          <SetupControls
            setupTypes={setupTypes}
            setupType={setupType}
            onSetupTypeChange={setSetupType}
            workAreaWidthFt={workAreaWidthFt}
            onWidthChange={setWorkAreaWidthFt}
          />

          <RoadOutlineFinder
            onSearch={handleSearchRoadCandidates}
            onConfirm={handleFindRoadOutline}
            prefill={prefillPoint}
            defaultLengthFt={defaultLengthFt}
            defaultDimensions={defaultDimensions}
          />

          <ResultsTable
            result={viewResult}
            selectedPoint={selectedPoint}
            onSelectPoint={setSelectedPoint}
            dimensionsBySpeed={dimensionsBySpeed}
            layerAttributes={layerAttributes}
            featureAssignments={viewAssignments}
            onAssignmentChange={handleAssignmentChange}
          />
        </aside>

        <main className="workspace-map">
          <MapPreview result={viewResult} selectedPoint={selectedPoint} />
        </main>
      </div>
    </div>
  );
}

export default App;

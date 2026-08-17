const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export async function uploadKmlFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Upload failed (${response.status})`);
  }

  return response.json();
}

export async function fetchSetupTypes() {
  const response = await fetch(`${API_BASE}/api/setup-types`);
  if (!response.ok) throw new Error(`Failed to load setup types (${response.status})`);
  const body = await response.json();
  return body.setup_types;
}

export async function getDimensions(speedMph, setupType, workAreaWidthFt) {
  const response = await fetch(`${API_BASE}/api/dimensions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      speed_mph: speedMph,
      setup_type: setupType,
      work_area_width_ft: workAreaWidthFt,
    }),
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.detail ?? `Dimension lookup failed (${response.status})`);
  }
  return body;
}

export async function fetchLayerAttributes() {
  const response = await fetch(`${API_BASE}/api/layer-attributes`);
  if (!response.ok) throw new Error(`Failed to load layer attributes (${response.status})`);
  const body = await response.json();
  return body.attributes;
}

export async function findRoadCandidates({ lon, lat, roadNameHint }) {
  const response = await fetch(`${API_BASE}/api/road-outline/candidates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lon,
      lat,
      road_name_hint: roadNameHint || undefined,
    }),
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.detail ?? `Road search failed (${response.status})`);
  }
  return body;
}

export async function findRoadOutline({ lon, lat, lengthFt = 200, roadName, widthFt, dims }) {
  const response = await fetch(`${API_BASE}/api/road-outline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lon,
      lat,
      length_ft: lengthFt,
      road_name: roadName ?? undefined,
      width_ft: widthFt || undefined,
      buffer_ft: dims?.buffer_length ?? undefined,
      taper_ft: dims?.taper_length ?? undefined,
      sign_a_ft: dims?.sign_spacing_A ?? undefined,
      sign_b_ft: dims?.sign_spacing_B ?? undefined,
      sign_c_ft: dims?.sign_spacing_C ?? undefined,
      cone_spacing_tangent_ft: dims?.cone_spacing_tangent ?? undefined,
      cone_spacing_taper_ft: dims?.cone_spacing_taper ?? undefined,
    }),
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.detail ?? `Road outline lookup failed (${response.status})`);
  }
  return body;
}

export async function transformPoint({ lon, lat }) {
  const response = await fetch(`${API_BASE}/api/transform-point`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lon, lat }),
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.detail ?? `Point transform failed (${response.status})`);
  }
  return body;
}

export async function generateDxf(features) {
  const response = await fetch(`${API_BASE}/api/generate-dxf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ features }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `DXF generation failed (${response.status})`);
  }
  return response.blob();
}

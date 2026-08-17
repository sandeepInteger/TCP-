"""REST API wrapping the Stage 1 coordinate pipeline (KML/KMZ parse + transform).

Kept as a thin layer over coord_transform/ on purpose: the parsing and
transform logic stays independently testable (see tests/test_transform.py),
this module only adds HTTP upload handling and JSON shaping for the UI.
"""

import base64
import io
import mimetypes
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cad_generator.dxf_writer import UnknownAttributeError, add_feature, load_layer_config, new_document
from coord_transform.kml_parser import parse_placemarks
from coord_transform.transformer import CoordinateTransformer, load_crs_config
from feature_rules.classify import classify_icon
from feature_rules.speed_limit import extract_speed_mph
from geometry_engine.centerline import (
    DegenerateOffsetError,
    InsufficientLengthError,
    nearest_line_and_point,
    offset_edges,
    place_tcp_stations,
    points_at_intervals,
    side_of_point,
    trim_polyline_around,
    zone_between,
)
from road_lookup.service import RoadLookupError, fetch_nearby_roads, load_road_source_config
from tcp_rules.dimensions import (
    TAPER_COLUMN_BY_SETUP,
    UnsupportedSetupTypeError,
    UnsupportedSpeedError,
    get_dimensions,
)

ALLOWED_SUFFIXES = {".kml", ".kmz"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

app = FastAPI(title="TCP Drawing Automation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    config = load_crs_config()
    return {"status": "ok", "source_crs": config["source_crs"], "target_crs": config["target_crs"]}


class DimensionsRequest(BaseModel):
    speed_mph: int
    setup_type: str
    work_area_width_ft: float = 12.0


@app.get("/api/setup-types")
def setup_types():
    """The setup types get_dimensions() supports — for populating the UI's
    dropdown. Only merge/shift/shoulder have a defined taper in
    tcp-dimensions-reference.md; flagger/closure setups use a different
    lookup (strand length, not taper) not implemented yet."""
    return {"setup_types": sorted(TAPER_COLUMN_BY_SETUP)}


@app.post("/api/dimensions")
def dimensions(req: DimensionsRequest):
    try:
        return get_dimensions(req.speed_mph, req.setup_type, req.work_area_width_ft)
    except (UnsupportedSpeedError, UnsupportedSetupTypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


class DxfFeatureIn(BaseModel):
    attribute: str
    points: list[list[float]]
    closed: bool = False


class GenerateDxfRequest(BaseModel):
    features: list[DxfFeatureIn]


@app.get("/api/layer-attributes")
def layer_attributes():
    """The feature attributes layer_standards.yaml defines — for populating
    the UI's per-feature layer-assignment dropdown."""
    return {"attributes": sorted(load_layer_config())}


@app.post("/api/generate-dxf")
def generate_dxf_endpoint(req: GenerateDxfRequest):
    if not req.features:
        raise HTTPException(400, "No features with an assigned layer to draw.")

    layer_config = load_layer_config()
    doc = new_document(layer_config)
    for feature in req.features:
        try:
            add_feature(
                doc,
                [tuple(p) for p in feature.points],
                feature.attribute,
                closed=feature.closed,
                layer_config=layer_config,
            )
        except (UnknownAttributeError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    stream = io.StringIO()
    doc.write(stream)
    dxf_bytes = stream.getvalue().encode("utf-8")

    return Response(
        content=dxf_bytes,
        media_type="application/dxf",
        headers={"Content-Disposition": "attachment; filename=tcp_drawing.dxf"},
    )


def _icon_payload(pm):
    """Shape a Placemark's icon info for JSON: a renderable data URI when the
    icon was bundled inside the KMZ, otherwise the raw href (e.g. a remote
    URL) for the frontend to use or ignore, or None if there's no icon."""
    if pm.icon_bytes is not None:
        mime_type, _ = mimetypes.guess_type(pm.icon_href or "")
        mime_type = mime_type or "image/png"
        data_uri = f"data:{mime_type};base64,{base64.b64encode(pm.icon_bytes).decode('ascii')}"
        return {"href": pm.icon_href, "data_uri": data_uri}
    if pm.icon_href:
        return {"href": pm.icon_href, "data_uri": None}
    return None


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, f"Unsupported file type '{suffix}'. Upload a .kml or .kmz file.")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large (max 20 MB).")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    try:
        try:
            placemarks = parse_placemarks(tmp_path)
        except Exception as exc:
            raise HTTPException(400, f"Could not parse file: {exc}") from exc

        transformer = CoordinateTransformer()

        features = []
        for pm in placemarks:
            points = []
            for coord in pm.coordinates:
                lon, lat = coord[0], coord[1]
                x, y = transformer.to_xy(lon, lat)
                points.append({"lon": lon, "lat": lat, "x": x, "y": y})

            feature_type = classify_icon(pm.icon_href)
            speed_mph = extract_speed_mph(pm.name) if feature_type == "speed_limit_sign" else None

            features.append(
                {
                    "name": pm.name,
                    "geometry_type": pm.geometry_type,
                    "points": points,
                    "icon": _icon_payload(pm),
                    "feature_type": feature_type,
                    "speed_mph": speed_mph,
                }
            )

        return {
            "filename": file.filename,
            "source_crs": transformer.source_crs,
            "target_crs": transformer.target_crs,
            "feature_count": len(features),
            "features": features,
        }
    finally:
        tmp_path.unlink(missing_ok=True)


class TransformPointRequest(BaseModel):
    lon: float
    lat: float


@app.post("/api/transform-point")
def transform_point(req: TransformPointRequest):
    """Re-projects a single lon/lat into the job's target X/Y — used when
    the UI lets the user drag a map vertex to correct it against imagery
    (e.g. a road-outline point that landed off the actual curve), so the
    dragged point's DXF coordinates stay in sync with its map position."""
    transformer = CoordinateTransformer()
    x, y = transformer.to_xy(req.lon, req.lat)
    return {
        "lon": req.lon,
        "lat": req.lat,
        "x": x,
        "y": y,
        "source_crs": transformer.source_crs,
        "target_crs": transformer.target_crs,
    }


class RoadCandidatesRequest(BaseModel):
    lon: float
    lat: float
    search_radius_ft: float | None = None
    road_name_hint: str | None = None


@app.post("/api/road-outline/candidates")
def road_outline_candidates(req: RoadCandidatesRequest):
    """List every distinct road found within search_radius_ft of (lon, lat),
    with how far off each one the point is — for confirming which road is
    actually intended before drawing anything. Necessary wherever two roads
    run close together (e.g. a highway and its frontage road at a ramp),
    where "just snap to whatever's nearest" silently picks the wrong one.

    If road_name_hint is given, candidates whose name contains it (case
    insensitive) are listed first, ahead of closer-but-unmatched roads —
    a name the requester already knows is a stronger signal than raw
    distance alone.
    """
    config = load_road_source_config()
    search_radius_ft = req.search_radius_ft or config.get("default_search_radius_ft", 150)
    generalize_degrees = config.get("candidate_search_generalize_degrees")

    try:
        roads = fetch_nearby_roads(
            req.lon, req.lat, search_radius_ft, config=config, generalize_degrees=generalize_degrees
        )
    except RoadLookupError as exc:
        raise HTTPException(502, str(exc)) from exc

    transformer = CoordinateTransformer()
    point_xy = transformer.to_xy(req.lon, req.lat)

    closest_offset_by_name = {}
    for road in roads:
        for part in road["parts"]:
            line_xy = [transformer.to_xy(lon, lat) for lon, lat in part]
            if len(line_xy) < 2:
                continue
            _, _, _, _, distance = nearest_line_and_point([line_xy], point_xy)
            name = road["name"]
            if name not in closest_offset_by_name or distance < closest_offset_by_name[name]:
                closest_offset_by_name[name] = distance

    if not closest_offset_by_name:
        raise HTTPException(404, f"No road found within {search_radius_ft} ft of this point.")

    hint = (req.road_name_hint or "").strip().lower()

    def sort_key(item):
        name, distance = item
        name_matches_hint = bool(hint) and bool(name) and hint in name.lower()
        return (0 if name_matches_hint else 1, distance)

    ranked = sorted(closest_offset_by_name.items(), key=sort_key)
    return {"candidates": [{"name": name, "offset_ft": distance} for name, distance in ranked]}


class RoadOutlineRequest(BaseModel):
    lon: float
    lat: float
    length_ft: float = 200.0
    search_radius_ft: float | None = None
    road_name: str | None = None
    width_ft: float | None = None
    buffer_ft: float | None = None
    taper_ft: float | None = None
    sign_a_ft: float | None = None
    sign_b_ft: float | None = None
    sign_c_ft: float | None = None
    cone_spacing_tangent_ft: float | None = None
    cone_spacing_taper_ft: float | None = None


@app.post("/api/road-outline")
def road_outline(req: RoadOutlineRequest):
    """Snap (lon, lat) onto a road from the external lookup configured in
    config/road_source.yaml, then trim that road's traced shape to
    length_ft around the snap point — the automated stand-in for a
    hand-traced centerline.

    Which direction length_ft extends is decided automatically, not asked
    for: if (lon, lat) falls on the right side of the road (relative to
    how the source data orders that road's points), the outline extends
    upstream (backward through that point order) only; if it falls on
    the left, downstream (forward) only. This is a fixed rule from the
    field, not a geometric default — see geometry_engine.centerline.
    side_of_point for the left/right convention it relies on.

    If road_name is given (normally the name the requester picked from
    /api/road-outline/candidates), only roads with that exact name are
    considered — otherwise this falls back to whichever nearby road is
    geometrically closest, which is a real risk wherever two roads run
    close together (see road_outline_candidates's docstring).

    The response always includes input_point — (lon, lat) as given, in
    the same {lon, lat, x, y} shape as every other point here — so the
    caller can draw the actual work point itself, not just the snapped
    location on the road.

    If width_ft is given, the response also includes left_edge/right_edge:
    the two roadway edges, each offset width_ft/2 from the centerline.
    width_ft is taken as given, not measured — no GIS source checked so
    far (Caltrans, OpenStreetMap, county road layers) carries pavement
    width for most local roads, and an imagery-based measurement attempt
    proved unreliable on curves and near other close-by pavement (see
    road_lookup/imagery_width.py's docstring) — so this is deliberately a
    known, human-provided value, not an automated guess.

    If buffer_ft/taper_ft/sign_a_ft/sign_b_ft/sign_c_ft are all given, the
    response also includes the actual TCP advance-warning layout, walked
    from (lon, lat) in the same direction the outline itself extends
    (side-based, per above — not a second, independent direction choice):
    buffer_zone and taper_zone (each a real line segment along the road),
    sign_1/sign_2/sign_3 (single points). cone_spacing_tangent_ft and
    cone_spacing_taper_ft are each independently optional on top of that,
    adding cones_tangent/cones_taper — points spaced through the buffer
    and taper zones respectively.
    """
    config = load_road_source_config()
    search_radius_ft = req.search_radius_ft or config.get("default_search_radius_ft", 150)

    try:
        roads = fetch_nearby_roads(
            req.lon, req.lat, search_radius_ft, config=config, road_name_filter=req.road_name
        )
    except RoadLookupError as exc:
        raise HTTPException(502, str(exc)) from exc

    transformer = CoordinateTransformer()

    lines_xy = []
    line_names = []
    for road in roads:
        for part in road["parts"]:
            lines_xy.append([transformer.to_xy(lon, lat) for lon, lat in part])
            line_names.append(road["name"])

    if not lines_xy:
        detail = (
            f"No road named {req.road_name!r} found within {search_radius_ft} ft of this point."
            if req.road_name is not None
            else f"No road found within {search_radius_ft} ft of this point."
        )
        raise HTTPException(404, detail)

    point_xy = transformer.to_xy(req.lon, req.lat)
    line_index, _segment_index, _t, snapped_xy, offset_ft = nearest_line_and_point(lines_xy, point_xy)

    side = side_of_point(lines_xy[line_index], point_xy)
    direction = "upstream" if side == "right" else "downstream"
    upstream_ft = req.length_ft if direction == "upstream" else 0.0
    downstream_ft = req.length_ft if direction == "downstream" else 0.0

    outline_xy = trim_polyline_around(lines_xy[line_index], point_xy, upstream_ft, downstream_ft)

    def to_point_dicts(xy_list):
        result = []
        for x, y in xy_list:
            lon, lat = transformer.to_lonlat(x, y)
            result.append({"lon": lon, "lat": lat, "x": x, "y": y})
        return result

    points = to_point_dicts(outline_xy)
    snapped_lon, snapped_lat = transformer.to_lonlat(*snapped_xy)

    response = {
        "road_name": line_names[line_index],
        "offset_ft": offset_ft,
        "side": side,
        "direction": direction,
        "snapped": {"lon": snapped_lon, "lat": snapped_lat, "x": snapped_xy[0], "y": snapped_xy[1]},
        "input_point": {"lon": req.lon, "lat": req.lat, "x": point_xy[0], "y": point_xy[1]},
        "source_crs": transformer.source_crs,
        "target_crs": transformer.target_crs,
        "points": points,
    }

    if req.width_ft is not None:
        try:
            left_xy, right_xy = offset_edges(outline_xy, req.width_ft)
        except DegenerateOffsetError as exc:
            raise HTTPException(400, str(exc)) from exc
        response["left_edge"] = to_point_dicts(left_xy)
        response["right_edge"] = to_point_dicts(right_xy)

    zone_inputs = (req.buffer_ft, req.taper_ft, req.sign_a_ft, req.sign_b_ft, req.sign_c_ft)
    if all(v is not None for v in zone_inputs):
        direction_int = 1 if direction == "downstream" else -1
        line_xy = lines_xy[line_index]

        try:
            stations = place_tcp_stations(
                line_xy,
                point_xy,
                direction_int,
                buffer_ft=req.buffer_ft,
                taper_ft=req.taper_ft,
                sign_a_ft=req.sign_a_ft,
                sign_b_ft=req.sign_b_ft,
                sign_c_ft=req.sign_c_ft,
            )
        except InsufficientLengthError as exc:
            raise HTTPException(
                400,
                f"The road doesn't extend far enough {direction} to fit the full TCP layout: {exc}",
            ) from exc

        buffer_zone_xy = zone_between(line_xy, point_xy, direction_int, 0, req.buffer_ft)
        taper_zone_xy = zone_between(
            line_xy, point_xy, direction_int, req.buffer_ft, req.buffer_ft + req.taper_ft
        )

        response["buffer_zone"] = to_point_dicts(buffer_zone_xy)
        response["taper_zone"] = to_point_dicts(taper_zone_xy)
        response["sign_1"] = to_point_dicts([stations["sign_1"]])[0]
        response["sign_2"] = to_point_dicts([stations["sign_2"]])[0]
        response["sign_3"] = to_point_dicts([stations["sign_3"]])[0]

        if req.cone_spacing_tangent_ft is not None:
            cones_tangent_xy = points_at_intervals(
                line_xy, point_xy, direction_int, 0, req.buffer_ft, req.cone_spacing_tangent_ft
            )
            response["cones_tangent"] = to_point_dicts(cones_tangent_xy)

        if req.cone_spacing_taper_ft is not None:
            cones_taper_xy = points_at_intervals(
                line_xy,
                point_xy,
                direction_int,
                req.buffer_ft,
                req.buffer_ft + req.taper_ft,
                req.cone_spacing_taper_ft,
            )
            response["cones_taper"] = to_point_dicts(cones_taper_xy)

    return response

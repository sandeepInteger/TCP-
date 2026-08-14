"""Look up real road-centerline geometry from an external GIS service, so a
work-area point can be snapped onto the actual road instead of relying on a
hand trace. Config-driven (config/road_source.yaml) so a different state's
GIS REST endpoint is a config edit, not a code change — same pattern as
crs_config.yaml / layer_standards.yaml.

Uses only the standard library for the HTTP call (urllib) rather than
adding a new dependency for what's a single GET request.
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "road_source.yaml"


class RoadLookupError(RuntimeError):
    """Raised when the external road-data request fails or the service
    itself reports an error — kept distinct from "no road found nearby"
    (an empty result), since one is a service/config problem and the
    other is a legitimate answer.
    """


# Some routes in this dataset (state highways in particular) are stored as
# one un-clipped feature spanning the route's entire length rather than
# just the segment near the query point — a point query that happens to
# intersect one can come back tens of megabytes and take over a minute to
# fully download, even though only a few nearby vertices are ever used.
# Capping the read means that case fails fast with a clear error instead
# of hanging the request or downloading geometry that's discarded anyway.
MAX_RESPONSE_BYTES = 2_000_000


def load_road_source_config(config_path=DEFAULT_CONFIG_PATH):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def fetch_nearby_roads(lon, lat, search_radius_ft, config=None, generalize_degrees=None, road_name_filter=None):
    """Query the configured ArcGIS REST FeatureServer for road centerlines
    within search_radius_ft of (lon, lat).

    generalize_degrees, if given, asks the server to simplify (generalize)
    the returned geometry to that tolerance (in degrees, since no outSR is
    set — roughly 0.00001 deg per foot at mid latitudes) via
    maxAllowableOffset. Only pass this for uses that don't need exact
    geometry (e.g. listing nearby road names and rough distances) — it
    measurably degrades position accuracy, so never use it for geometry
    that actually gets drawn/trimmed and exported.

    road_name_filter, if given, restricts the query server-side (via a
    `where` clause on name_field) to just that one road's records. Without
    this, fetching a specific known road still downloads every OTHER road
    in the radius too — including, at some locations, a state highway
    stored as one un-clipped feature spanning its entire length (seen at
    7MB+ in testing) — even though it's irrelevant to the one road actually
    wanted.

    Returns a list of {"name": str | None, "parts": [[(lon, lat), ...], ...]}.
    "parts" is a list because a single road can come back as a
    MultiLineString — split into several disconnected pieces (e.g. broken
    at intersections in the source data) — each treated as its own
    candidate line for snapping.
    """
    if config is None:
        config = load_road_source_config()
    query_url = config["query_url"]

    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": str(search_radius_ft),
        "units": "esriSRUnit_Foot",
        "outFields": "*",
        "f": "geojson",
    }
    if generalize_degrees is not None:
        params["maxAllowableOffset"] = str(generalize_degrees)
    if road_name_filter is not None:
        name_field = config.get("name_field")
        escaped = road_name_filter.replace("'", "''")
        params["where"] = f"{name_field} = '{escaped}'"
    url = f"{query_url}?{urllib.parse.urlencode(params)}"

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
    except Exception as exc:
        raise RoadLookupError(f"Road lookup request failed: {exc}") from exc

    if len(raw) > MAX_RESPONSE_BYTES:
        raise RoadLookupError(
            f"Road lookup response exceeded {MAX_RESPONSE_BYTES:,} bytes — likely a "
            "full, un-clipped route geometry (e.g. a state highway) rather than a "
            "local road segment. Try a smaller search_radius_ft, or a point further "
            "from a state highway."
        )

    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RoadLookupError(f"Road lookup response was not valid JSON: {exc}") from exc

    if isinstance(body, dict) and "error" in body:
        raise RoadLookupError(f"Road lookup service error: {body['error']}")

    name_field = config.get("name_field")
    roads = []
    for feature in body.get("features", []):
        geometry = feature.get("geometry") or {}
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates") or []

        if geometry_type == "LineString":
            parts = [coordinates]
        elif geometry_type == "MultiLineString":
            parts = coordinates
        else:
            continue

        name = feature.get("properties", {}).get(name_field) if name_field else None
        roads.append(
            {
                "name": name,
                "parts": [[(pt[0], pt[1]) for pt in part] for part in parts if len(part) >= 2],
            }
        )

    return roads

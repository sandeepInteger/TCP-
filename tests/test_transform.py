"""Stage 1 validation: KML/KMZ parsing + coordinate transform.

Expected X/Y values below were independently computed with pyproj against
EPSG:2227 (NAD83 / California Zone 3, US Survey Feet — the target_crs in
config/crs_config.yaml, covering the Bay Area / Central Coast job sites
this pipeline is currently configured for). If target_crs changes,
regenerate expected values for the new CRS.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coord_transform.kml_parser import parse_placemarks
from coord_transform.transformer import CoordinateTransformer

FIXTURES = Path(__file__).resolve().parent / "fixtures"

KNOWN_POINTS = {
    "Golden Gate Bridge, San Francisco CA": (5990283.754, 2127045.518),
    "San Francisco City Hall": (6007018.850, 2111910.386),
    "San Jose City Hall": (6158655.059, 1948598.418),
}

TOLERANCE_FEET = 0.01


def _check_known_points(placemarks, transformer):
    checked = 0
    for pm in placemarks:
        if pm.name not in KNOWN_POINTS or not pm.coordinates:
            continue
        lon, lat = pm.coordinates[0][0], pm.coordinates[0][1]
        x, y = transformer.to_xy(lon, lat)
        exp_x, exp_y = KNOWN_POINTS[pm.name]
        dist = math.hypot(x - exp_x, y - exp_y)
        assert dist <= TOLERANCE_FEET, (
            f"{pm.name}: got ({x:.3f}, {y:.3f}), expected ({exp_x:.3f}, {exp_y:.3f}), "
            f"off by {dist:.3f} ft"
        )
        checked += 1
    assert checked == len(KNOWN_POINTS), (
        f"expected to validate {len(KNOWN_POINTS)} known points, only found {checked}"
    )


def test_kml_known_points():
    placemarks = parse_placemarks(FIXTURES / "known_points.kml")
    transformer = CoordinateTransformer()
    _check_known_points(placemarks, transformer)


def test_kmz_known_points():
    placemarks = parse_placemarks(FIXTURES / "known_points.kmz")
    transformer = CoordinateTransformer()
    _check_known_points(placemarks, transformer)


def test_linestring_parsed_as_multiple_points():
    placemarks = parse_placemarks(FIXTURES / "known_points.kml")
    road = next(pm for pm in placemarks if pm.name == "Sample Road Centerline")
    assert len(road.coordinates) == 3


def test_linestring_transforms_to_ordered_polyline_points():
    placemarks = parse_placemarks(FIXTURES / "known_points.kml")
    road = next(pm for pm in placemarks if pm.name == "Sample Road Centerline")
    transformer = CoordinateTransformer()
    xy_points = transformer.transform_points(road.coordinates)
    assert len(xy_points) == 3
    # Sanity check: consecutive vertices should be tens/hundreds of feet
    # apart, not degenerate (0,0) or wildly discontinuous.
    for (x1, y1), (x2, y2) in zip(xy_points, xy_points[1:]):
        dist = math.hypot(x2 - x1, y2 - y1)
        assert 1 < dist < 3000, f"unexpected segment length {dist:.3f} ft"


if __name__ == "__main__":
    test_kml_known_points()
    test_kmz_known_points()
    test_linestring_parsed_as_multiple_points()
    test_linestring_transforms_to_ordered_polyline_points()
    print("All Stage 1 (coordinate transform) tests passed.")

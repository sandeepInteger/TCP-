"""End-to-end demo: KML icon+name -> classification -> speed -> dimensions
-> centerline stations.

Proves the independently-tested stages (kml_parser, feature_rules,
tcp_rules, geometry_engine) actually connect the way the pipeline diagrams
in tcp-automation-plan.md and tcp-dimensions-reference.md say they should,
on a single realistic input: a placemark with a car icon named "25 MPH".
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coord_transform.kml_parser import parse_placemarks
from feature_rules.classify import classify_icon
from feature_rules.speed_limit import extract_speed_mph
from geometry_engine.centerline import place_tcp_stations
from tcp_rules.dimensions import get_dimensions

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_speed_limit_sign_drives_dimension_lookup():
    placemarks = parse_placemarks(FIXTURES / "icons_sample.kmz")
    sign = next(pm for pm in placemarks if pm.name == "25 MPH")

    feature_type = classify_icon(sign.icon_href)
    assert feature_type == "speed_limit_sign"

    speed_mph = extract_speed_mph(sign.name)
    assert speed_mph == 25

    dims = get_dimensions(speed_mph=speed_mph, setup_type="shift", work_area_width_ft=12)
    assert dims["buffer_length"] == 158
    assert dims["taper_length"] == 65
    assert dims["sign_spacing_A"] == 100


def test_full_pipeline_places_stations_on_centerline():
    placemarks = parse_placemarks(FIXTURES / "icons_sample.kmz")
    sign = next(pm for pm in placemarks if pm.name == "25 MPH")
    speed_mph = extract_speed_mph(sign.name)
    dims = get_dimensions(speed_mph=speed_mph, setup_type="shift", work_area_width_ft=12)

    # Synthetic centerline standing in for a real traced road (already in
    # feet, per config/crs_config.yaml) — long enough to fit every station.
    centerline = [(0, 0), (2000, 0)]
    work_area_point = (0, 0)

    stations = place_tcp_stations(
        centerline,
        work_area_point,
        direction=1,
        buffer_ft=dims["buffer_length"],
        taper_ft=dims["taper_length"],
        sign_a_ft=dims["sign_spacing_A"],
        sign_b_ft=dims["sign_spacing_B"],
        sign_c_ft=dims["sign_spacing_C"],
    )

    # 158 (buffer) -> 223 (+65 taper) -> 323 (+100 A) -> 423 (+100 B) -> 523 (+100 C)
    assert math.isclose(stations["buffer_end"][0], 158, abs_tol=1e-6)
    assert math.isclose(stations["taper_start"][0], 223, abs_tol=1e-6)
    assert math.isclose(stations["sign_1"][0], 323, abs_tol=1e-6)
    assert math.isclose(stations["sign_2"][0], 423, abs_tol=1e-6)
    assert math.isclose(stations["sign_3"][0], 523, abs_tol=1e-6)


if __name__ == "__main__":
    test_speed_limit_sign_drives_dimension_lookup()
    test_full_pipeline_places_stations_on_centerline()
    print("All pipeline integration tests passed.")

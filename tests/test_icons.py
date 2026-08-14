"""Icon resolution: KML Style/StyleMap -> per-placemark icon href + bytes.

Survey KMZs commonly encode feature type (pole, chamber, speed-limit sign,
etc.) as a distinct icon rather than as plain text, so this is validated
as its own concern, separate from the coordinate transform in test_transform.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coord_transform.kml_parser import parse_placemarks

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _by_name(placemarks, name):
    return next(pm for pm in placemarks if pm.name == name)


def test_icon_via_direct_styleurl_kml():
    placemarks = parse_placemarks(FIXTURES / "icons_sample.kml")
    pm = _by_name(placemarks, "Pole via direct styleUrl")
    assert pm.icon_href == "files/pole_icon.png"
    # Plain .kml has no bundled asset to resolve, so bytes stay None.
    assert pm.icon_bytes is None


def test_icon_via_stylemap_indirection():
    placemarks = parse_placemarks(FIXTURES / "icons_sample.kml")
    pm = _by_name(placemarks, "Pole via StyleMap styleUrl")
    assert pm.icon_href == "files/pole_icon.png"


def test_icon_via_inline_style():
    placemarks = parse_placemarks(FIXTURES / "icons_sample.kml")
    pm = _by_name(placemarks, "Speed Limit 35 (inline style)")
    assert pm.icon_href == "files/pole_icon.png"


def test_placemark_without_style_has_no_icon():
    placemarks = parse_placemarks(FIXTURES / "icons_sample.kml")
    pm = _by_name(placemarks, "No icon at all")
    assert pm.icon_href is None
    assert pm.icon_bytes is None


def test_remote_icon_href_kept_but_not_fetched():
    placemarks = parse_placemarks(FIXTURES / "icons_sample.kml")
    pm = _by_name(placemarks, "Remote stock icon")
    assert pm.icon_href == "http://maps.google.com/mapfiles/kml/shapes/road_shield3.png"
    assert pm.icon_bytes is None


def test_kmz_bundled_icon_bytes_match_source_file():
    placemarks = parse_placemarks(FIXTURES / "icons_sample.kmz")
    pm = _by_name(placemarks, "Pole via direct styleUrl")
    assert pm.icon_href == "files/pole_icon.png"
    expected_bytes = (FIXTURES / "pole_icon.png").read_bytes()
    assert pm.icon_bytes == expected_bytes


def test_kmz_stylemap_icon_bytes_also_resolve():
    placemarks = parse_placemarks(FIXTURES / "icons_sample.kmz")
    pm = _by_name(placemarks, "Pole via StyleMap styleUrl")
    expected_bytes = (FIXTURES / "pole_icon.png").read_bytes()
    assert pm.icon_bytes == expected_bytes


if __name__ == "__main__":
    test_icon_via_direct_styleurl_kml()
    test_icon_via_stylemap_indirection()
    test_icon_via_inline_style()
    test_placemark_without_style_has_no_icon()
    test_remote_icon_href_kept_but_not_fetched()
    test_kmz_bundled_icon_bytes_match_source_file()
    test_kmz_stylemap_icon_bytes_also_resolve()
    print("All icon resolution tests passed.")

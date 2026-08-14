"""AutoCAD Generator validation: Feature Database records -> DXF entities.

Writes a real .dxf to a temp file and reads it back with ezdxf, so this
checks what AutoCAD would actually see on disk, not just in-memory state.
"""

import os
import sys
import tempfile
from pathlib import Path

import ezdxf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cad_generator.dxf_writer import (
    UnknownAttributeError,
    add_feature,
    generate_dxf,
    load_layer_config,
    new_document,
)


def _tmp_dxf_path():
    # mkstemp returns an *open* OS-level file descriptor as well as the
    # path — on Windows the file can't be deleted later while that
    # descriptor is still open, so close it immediately; only the path is
    # needed here since generate_dxf() does its own writing.
    fd, path = tempfile.mkstemp(suffix=".dxf")
    os.close(fd)
    return Path(path)


def test_new_document_defines_every_configured_layer():
    config = load_layer_config()
    doc = new_document(config)
    layer_names = {layer.dxf.name for layer in doc.layers}
    for rule in config.values():
        assert rule["layer"] in layer_names


def test_layer_color_linetype_lineweight_match_config():
    config = load_layer_config()
    doc = new_document(config)
    curb_layer = doc.layers.get("TCP_CURB")
    assert curb_layer.color == config["CURB"]["color"]
    assert curb_layer.dxf.linetype == config["CURB"]["linetype"]
    assert curb_layer.dxf.lineweight == config["CURB"]["lineweight"]


def test_linestring_feature_becomes_open_lwpolyline_on_correct_layer():
    doc = new_document()
    points = [(0, 0), (100, 0), (200, 50)]
    entity = add_feature(doc, points, "CENTER_LINE")
    assert entity.dxftype() == "LWPOLYLINE"
    assert entity.dxf.layer == "TCP_CENTERLINE"
    assert entity.closed is False
    assert [(p[0], p[1]) for p in entity.get_points()] == points


def test_polygon_feature_becomes_closed_lwpolyline():
    doc = new_document()
    points = [(10, 0), (20, 0), (20, 5), (10, 5)]
    entity = add_feature(doc, points, "PAINTED_MEDIAN", closed=True)
    assert entity.dxftype() == "LWPOLYLINE"
    assert entity.closed is True


def test_single_point_feature_becomes_circle_marker():
    doc = new_document()
    entity = add_feature(doc, [(50, 50)], "EX_ARROW")
    assert entity.dxftype() == "CIRCLE"
    assert entity.dxf.layer == "TCP_ARROW"
    assert tuple(entity.dxf.center)[:2] == (50, 50)


def test_unknown_attribute_raises_instead_of_silently_defaulting():
    doc = new_document()
    try:
        add_feature(doc, [(0, 0), (1, 1)], "BICYCLE_LANE")
        assert False, "expected UnknownAttributeError"
    except UnknownAttributeError:
        pass


def test_empty_points_raises():
    doc = new_document()
    try:
        add_feature(doc, [], "CURB")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_generate_dxf_writes_a_readable_file_with_all_features():
    features = [
        {"attribute": "CENTER_LINE", "points": [(0, 0), (100, 0), (200, 50)]},
        {"attribute": "CURB", "points": [(0, 10), (100, 10), (200, 60)]},
        {
            "attribute": "PAINTED_MEDIAN",
            "points": [(10, 0), (20, 0), (20, 5), (10, 5)],
            "closed": True,
        },
    ]
    path = _tmp_dxf_path()
    try:
        generate_dxf(features, path)
        assert path.exists()

        readback = ezdxf.readfile(path)
        msp = readback.modelspace()
        entities = list(msp)
        assert len(entities) == 3

        by_layer = {e.dxf.layer: e for e in entities}
        assert set(by_layer) == {"TCP_CENTERLINE", "TCP_CURB", "TCP_PAINTED_MEDIAN"}
        assert by_layer["TCP_PAINTED_MEDIAN"].closed is True
        assert by_layer["TCP_CENTERLINE"].closed is False
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    test_new_document_defines_every_configured_layer()
    test_layer_color_linetype_lineweight_match_config()
    test_linestring_feature_becomes_open_lwpolyline_on_correct_layer()
    test_polygon_feature_becomes_closed_lwpolyline()
    test_single_point_feature_becomes_circle_marker()
    test_unknown_attribute_raises_instead_of_silently_defaulting()
    test_empty_points_raises()
    test_generate_dxf_writes_a_readable_file_with_all_features()
    print("All AutoCAD Generator (DXF writer) tests passed.")

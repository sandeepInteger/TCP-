"""AutoCAD Generator stage from tcp-automation-plan.md: takes Feature
Database records (attribute + coordinates, already in feet — see
config/crs_config.yaml) and writes a .dxf file with the correct layer,
color, linetype, and lineweight per config/layer_standards.yaml.

Deliberately targets DXF, not .dwg: DXF is an open, fully-documented format
that AutoCAD reads/writes natively, and ezdxf (pure Python, MIT licensed)
can write it without needing AutoCAD installed. There is no reliable free
way to write native .dwg directly — that requires either Autodesk's own SDK
or driving a licensed copy of AutoCAD via COM automation. The standard next
step to get an actual .dwg from the file this module produces is a batch
conversion pass (e.g. the free ODA File Converter), kept as a separate
concern from drawing generation.
"""

from pathlib import Path

import ezdxf
from ezdxf.tools.standards import setup_linetypes
import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "layer_standards.yaml"

# A bare POINT entity is effectively invisible in AutoCAD without PDMODE
# set, so single-point features (signs, poles, etc.) are drawn as a small
# circle instead — this is also how engineers commonly mark point features
# by hand in a TCP drawing.
POINT_MARKER_RADIUS_FT = 1.5


class UnknownAttributeError(ValueError):
    """Raised when a feature's attribute isn't in layer_standards.yaml.

    Deliberately not a silent fallback to a default layer — a feature
    drawn on the wrong layer in a traffic control plan is a real error,
    not a cosmetic one, so it must be surfaced, not guessed past.
    """


def load_layer_config(config_path=DEFAULT_CONFIG_PATH):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def new_document(layer_config=None):
    """Create a new DXF document with every configured layer defined
    (name, color, linetype, lineweight) and the standard linetype library
    loaded, so DASHED/CENTER/etc. are available for layers that need them.
    """
    if layer_config is None:
        layer_config = load_layer_config()

    doc = ezdxf.new("R2010")
    setup_linetypes(doc)

    for attribute, rule in layer_config.items():
        doc.layers.add(
            name=rule["layer"],
            color=rule["color"],
            linetype=rule["linetype"],
            lineweight=rule["lineweight"],
        )

    return doc


def add_feature(doc, points, attribute, closed=False, layer_config=None):
    """Add one feature's geometry to doc, on the layer configured for
    `attribute`. points is a list of (x, y) tuples in feet.

    A single-point feature is drawn as a small circle (see
    POINT_MARKER_RADIUS_FT); two or more points become an LWPOLYLINE,
    closed if `closed` is True (e.g. a painted/raised median boundary).

    Raises UnknownAttributeError if `attribute` isn't in the layer config.
    """
    if layer_config is None:
        layer_config = load_layer_config()
    if attribute not in layer_config:
        raise UnknownAttributeError(
            f"attribute {attribute!r} has no entry in layer_standards.yaml "
            f"(known: {sorted(layer_config)})"
        )
    if not points:
        raise ValueError("feature has no points to draw")

    layer_name = layer_config[attribute]["layer"]
    msp = doc.modelspace()

    if len(points) == 1:
        return msp.add_circle(points[0], POINT_MARKER_RADIUS_FT, dxfattribs={"layer": layer_name})

    return msp.add_lwpolyline(points, close=closed, dxfattribs={"layer": layer_name})


def save_document(doc, path):
    doc.saveas(path)


def generate_dxf(features, output_path, layer_config=None):
    """Build a full DXF from a list of Feature Database records and save it.

    Each feature is a dict: {"attribute": str, "points": [(x, y), ...],
    "closed": bool (optional, default False)}.
    """
    if layer_config is None:
        layer_config = load_layer_config()

    doc = new_document(layer_config)
    for feature in features:
        add_feature(
            doc,
            feature["points"],
            feature["attribute"],
            closed=feature.get("closed", False),
            layer_config=layer_config,
        )
    save_document(doc, output_path)
    return doc

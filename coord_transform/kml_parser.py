"""Parse Placemark coordinates out of a KML or KMZ file.

Deliberately avoids fastkml/simplekml: KML is plain namespaced XML, and a
raw ElementTree walk keeps this module dependency-light and easy to reason
about when a survey vendor's KMZ doesn't conform strictly to the OGC schema.
"""

from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree
import zipfile

KML_NS = "http://www.opengis.net/kml/2.2"


@dataclass
class Placemark:
    name: str
    # (lon, lat) or (lon, lat, alt) tuples, in KML's native lon-first order.
    coordinates: list = field(default_factory=list)
    # "Point" | "LineString" | "Polygon" | "Unknown" (e.g. MultiGeometry).
    geometry_type: str = "Unknown"
    # Raw <Icon><href> string from the placemark's style, e.g. "files/pole.png"
    # or an absolute URL. None if the placemark has no icon style at all.
    icon_href: str = None
    # Icon image bytes, populated only when icon_href is a relative path that
    # resolves to a file bundled inside the KMZ (survey tools embed custom
    # per-feature-type icons this way; absolute URLs are left for the caller
    # to fetch, since that's a network concern, not a parsing one).
    icon_bytes: bytes = None


def _open_kml_source(path):
    """Return (kml_text, resolve_asset, archive).

    resolve_asset(rel_href) -> bytes | None looks up a file referenced by an
    Icon href relative to where the KML lives: inside the KMZ zip for a
    .kmz, or next to the file on disk for a bare .kml. archive is the open
    ZipFile (or None for .kml) — callers must close it when done.
    """
    path = Path(path)
    if path.suffix.lower() == ".kmz":
        archive = zipfile.ZipFile(path)
        kml_names = [n for n in archive.namelist() if n.lower().endswith(".kml")]
        if not kml_names:
            archive.close()
            raise ValueError(f"No .kml entry found inside {path}")
        # KMZ convention: doc.kml at the archive root is the main document.
        kml_names.sort(key=lambda n: (n.lower() != "doc.kml", n))
        main_kml_name = kml_names[0]
        kml_text = archive.read(main_kml_name).decode("utf-8")

        def resolve_asset(rel_href):
            # Icon hrefs are relative to the .kml entry's own folder within
            # the archive, which is usually (but not always) the zip root.
            base_dir = Path(main_kml_name).parent
            candidate = str((base_dir / rel_href)).replace("\\", "/")
            for name in archive.namelist():
                if name.replace("\\", "/") in (rel_href, candidate):
                    return archive.read(name)
            return None

        return kml_text, resolve_asset, archive

    kml_text = path.read_text(encoding="utf-8")

    def resolve_asset(rel_href):
        candidate = path.parent / rel_href
        return candidate.read_bytes() if candidate.exists() else None

    return kml_text, resolve_asset, None


def _parse_coordinates_text(text):
    points = []
    for chunk in text.split():
        parts = chunk.split(",")
        if len(parts) < 2:
            continue
        lon, lat = float(parts[0]), float(parts[1])
        alt = float(parts[2]) if len(parts) > 2 else None
        points.append((lon, lat, alt) if alt is not None else (lon, lat))
    return points


def _extract_geometry(pm, ns):
    """Return (geometry_type, coords_points) for a Placemark's first geometry.

    Point and LineString are handled directly. Polygon uses only the outer
    boundary (outerBoundaryIs) so a donut-shaped median doesn't get its hole
    merged into the same point list as the outer edge. MultiGeometry and any
    other case fall back to grabbing every <coordinates> tag under the
    Placemark, tagged "Unknown".
    """
    point_el = pm.find("kml:Point", ns)
    if point_el is not None:
        coords_el = point_el.find("kml:coordinates", ns)
        text = coords_el.text if coords_el is not None else None
        return "Point", (_parse_coordinates_text(text) if text else [])

    line_el = pm.find("kml:LineString", ns)
    if line_el is not None:
        coords_el = line_el.find("kml:coordinates", ns)
        text = coords_el.text if coords_el is not None else None
        return "LineString", (_parse_coordinates_text(text) if text else [])

    poly_el = pm.find("kml:Polygon", ns)
    if poly_el is not None:
        coords_el = poly_el.find("kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", ns)
        text = coords_el.text if coords_el is not None else None
        return "Polygon", (_parse_coordinates_text(text) if text else [])

    coords_points = []
    for coords_el in pm.iter(f"{{{KML_NS}}}coordinates"):
        if coords_el.text:
            coords_points.extend(_parse_coordinates_text(coords_el.text))
    return "Unknown", coords_points


def _parse_icon_styles(root, ns):
    """Map "#style_id" -> icon href, for every <Style id> with an IconStyle.

    Also resolves <StyleMap> "normal" pairs one level deep, since Google
    Earth exports a Placemark's styleUrl pointing at a StyleMap (separate
    normal/highlight styles) far more often than at a bare Style.
    """
    icon_by_style_ref = {}
    for style_el in root.iter(f"{{{KML_NS}}}Style"):
        style_id = style_el.get("id")
        icon_el = style_el.find("kml:IconStyle/kml:Icon/kml:href", ns)
        if style_id and icon_el is not None and icon_el.text:
            icon_by_style_ref[f"#{style_id}"] = icon_el.text.strip()

    for stylemap_el in root.iter(f"{{{KML_NS}}}StyleMap"):
        style_id = stylemap_el.get("id")
        if not style_id:
            continue
        for pair in stylemap_el.findall("kml:Pair", ns):
            key_el = pair.find("kml:key", ns)
            url_el = pair.find("kml:styleUrl", ns)
            if (
                key_el is not None
                and key_el.text == "normal"
                and url_el is not None
                and url_el.text
                and url_el.text.strip() in icon_by_style_ref
            ):
                icon_by_style_ref[f"#{style_id}"] = icon_by_style_ref[url_el.text.strip()]

    return icon_by_style_ref


def _resolve_icon_href(pm, ns, icon_by_style_ref):
    inline_icon_el = pm.find("kml:Style/kml:IconStyle/kml:Icon/kml:href", ns)
    if inline_icon_el is not None and inline_icon_el.text:
        return inline_icon_el.text.strip()

    style_url_el = pm.find("kml:styleUrl", ns)
    if style_url_el is not None and style_url_el.text:
        return icon_by_style_ref.get(style_url_el.text.strip())

    return None


def parse_placemarks(path):
    """Return every Placemark in the KML/KMZ as a list of Placemark records.

    Handles Point, LineString, and Polygon (outer boundary only) geometries,
    which covers surveyed points and traced road/feature lines. Also
    resolves each Placemark's icon: survey tools commonly use a distinct
    icon per feature type (e.g. a pole vs. a speed-limit sign), which is
    a much stronger classification signal than geometry alone.
    """
    kml_text, resolve_asset, archive = _open_kml_source(path)
    try:
        root = ElementTree.fromstring(kml_text)
        ns = {"kml": KML_NS}
        icon_by_style_ref = _parse_icon_styles(root, ns)
        placemarks = []

        for pm in root.iter(f"{{{KML_NS}}}Placemark"):
            name_el = pm.find("kml:name", ns)
            name = name_el.text.strip() if name_el is not None and name_el.text else ""

            geometry_type, coords_points = _extract_geometry(pm, ns)

            icon_href = _resolve_icon_href(pm, ns, icon_by_style_ref)
            icon_bytes = None
            if icon_href and not icon_href.lower().startswith(("http://", "https://")):
                icon_bytes = resolve_asset(icon_href)

            placemarks.append(
                Placemark(
                    name=name,
                    coordinates=coords_points,
                    geometry_type=geometry_type,
                    icon_href=icon_href,
                    icon_bytes=icon_bytes,
                )
            )

        return placemarks
    finally:
        if archive is not None:
            archive.close()

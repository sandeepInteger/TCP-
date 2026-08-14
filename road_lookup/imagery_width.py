"""Estimate a road's paved width directly from aerial imagery.

Exists because no GIS attribute source checked so far (Caltrans All Roads,
OpenStreetMap, a county's official Roads layer) carries pavement width for
most local roads — only geometry and classification codes. This measures
it instead of looking it up: fetch the same aerial imagery the frontend's
MapPreview already shows, then at several points along the road, walk
outward perpendicular to it counting pixels until the pavement's color
gives out.

This is a heuristic, not a certified measurement. It cannot see through
tree canopy that visually covers the road in the imagery — a real,
unavoidable limit of any image-based method, not something a better color
rule fixes. Sampling several cross-sections and taking the median is what
makes it usable despite that: a single tree shadow or parked car at one
spot doesn't have to spoil the estimate, as long as most sampled points
have a clear view.
"""

import math
import urllib.request
from io import BytesIO

from PIL import Image

TILE_SIZE = 256
IMAGERY_URL_TEMPLATE = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
METERS_TO_FEET = 3.280839895


class ImageryWidthError(RuntimeError):
    """Raised when imagery can't be fetched at all — distinct from a
    successful fetch that simply couldn't measure a clear width (which
    returns None rather than raising, since "inconclusive" is a normal,
    expected outcome, not an error).
    """


def _lonlat_to_tile_frac(lon, lat, zoom):
    lat_rad = math.radians(lat)
    n = 2**zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def _ground_resolution_ft_per_px(lat, zoom):
    meters_per_px = 156543.03392804097 * math.cos(math.radians(lat)) / (2**zoom)
    return meters_per_px * METERS_TO_FEET


def _fetch_tile(z, x, y):
    url = IMAGERY_URL_TEMPLATE.format(z=z, y=y, x=x)
    req = urllib.request.Request(url, headers={"User-Agent": "tcp-automation/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        return Image.open(BytesIO(data)).convert("RGB")
    except Exception as exc:
        raise ImageryWidthError(f"Failed to fetch imagery tile ({z}/{x}/{y}): {exc}") from exc


def _fetch_mosaic(lon, lat, zoom, radius_tiles):
    """Fetch a (2*radius_tiles+1)^2 grid of tiles centered on (lon, lat).

    Returns (mosaic_image, center_px, center_py) — center_px/py are the
    mosaic-local pixel coordinates of (lon, lat) itself.
    """
    xf, yf = _lonlat_to_tile_frac(lon, lat, zoom)
    cx, cy = int(xf), int(yf)
    span = 2 * radius_tiles + 1

    mosaic = Image.new("RGB", (TILE_SIZE * span, TILE_SIZE * span))
    for dx in range(-radius_tiles, radius_tiles + 1):
        for dy in range(-radius_tiles, radius_tiles + 1):
            tile = _fetch_tile(zoom, cx + dx, cy + dy)
            mosaic.paste(tile, ((dx + radius_tiles) * TILE_SIZE, (dy + radius_tiles) * TILE_SIZE))

    center_px = (xf - (cx - radius_tiles)) * TILE_SIZE
    center_py = (yf - (cy - radius_tiles)) * TILE_SIZE
    return mosaic, center_px, center_py


SATURATION_THRESHOLD = 0.22


def _is_excluded(rgb):
    """True if this pixel is clearly NOT pavement, using color saturation
    rather than hand-picked hues. Pavement — including tree-shadow-darkened
    asphalt and white/yellow lane markings — is consistently low-saturation
    (its channels are close to each other, gray-to-white). Dirt/tan
    shoulder, green vegetation, and teal water are all clearly-saturated
    colors by comparison, so one threshold catches all three instead of
    needing a separate rule per surface type.

    An earlier version only excluded green/blue hues specifically, which
    let a measurement "leak" straight across an unexcluded tan dirt median
    onto an adjacent road — saturation catches that case too.
    """
    r, g, b = rgb
    hi, lo = max(r, g, b), min(r, g, b)
    if hi == 0:
        return False
    saturation = (hi - lo) / hi
    return saturation > SATURATION_THRESHOLD


def _measure_cross_section(mosaic, px, py, bearing_rad, ft_per_px, max_half_width_ft):
    """Walk outward from (px, py) perpendicular to bearing_rad in both
    directions, one pixel at a time, until an excluded (non-pavement)
    color is hit or max_half_width_ft is reached. Returns the total width
    in feet, or None if (px, py) itself isn't on a pavement-like pixel
    (meaning this sample point wasn't actually over the road in the image).
    """
    width, height = mosaic.size
    if not (0 <= int(px) < width and 0 <= int(py) < height):
        return None
    if _is_excluded(mosaic.getpixel((int(px), int(py)))):
        return None

    # Perpendicular direction to the road's bearing.
    perp = bearing_rad + math.pi / 2
    dx, dy = math.sin(perp), -math.cos(perp)
    max_steps = int(max_half_width_ft / ft_per_px)

    def extent(sign):
        for step in range(1, max_steps + 1):
            x = px + sign * dx * step
            y = py + sign * dy * step
            if not (0 <= int(x) < width and 0 <= int(y) < height):
                return (step - 1) * ft_per_px
            if _is_excluded(mosaic.getpixel((int(x), int(y)))):
                return (step - 1) * ft_per_px
        return max_steps * ft_per_px

    return extent(1) + extent(-1)


def estimate_road_width_ft(
    line_xy_to_lonlat,
    anchor_lonlat,
    sample_offsets_ft=(-60, -30, 0, 30, 60),
    zoom=20,
    max_half_width_ft=60,
):
    """Estimate paved width (feet) near anchor_lonlat by sampling several
    cross-sections along the road at sample_offsets_ft from it.

    line_xy_to_lonlat is a list of (lon, lat, bearing_rad) for each sample
    point — the caller (which already has the centerline and a coordinate
    transformer) computes these, since this module has no notion of the
    project's CRS.

    Returns (width_ft, num_samples_used) — width_ft is the median of
    whichever samples got a clear reading, or None if none did (e.g. the
    road is entirely tree-covered in the available imagery at every
    sampled point).
    """
    lon, lat = anchor_lonlat
    radius_tiles = 2  # generous enough to cover every sample_offsets_ft point at zoom 20
    mosaic, center_px, center_py = _fetch_mosaic(lon, lat, zoom, radius_tiles)
    ft_per_px = _ground_resolution_ft_per_px(lat, zoom)

    widths = []
    for sample_lon, sample_lat, bearing_rad in line_xy_to_lonlat:
        xf, yf = _lonlat_to_tile_frac(sample_lon, sample_lat, zoom)
        anchor_xf, anchor_yf = _lonlat_to_tile_frac(lon, lat, zoom)
        px = center_px + (xf - anchor_xf) * TILE_SIZE
        py = center_py + (yf - anchor_yf) * TILE_SIZE
        width = _measure_cross_section(mosaic, px, py, bearing_rad, ft_per_px, max_half_width_ft)
        if width is not None:
            widths.append(width)

    if not widths:
        return None, 0

    widths.sort()
    mid = len(widths) // 2
    median = widths[mid] if len(widths) % 2 == 1 else (widths[mid - 1] + widths[mid]) / 2
    return median, len(widths)

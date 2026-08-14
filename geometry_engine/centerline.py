"""Walk a fixed distance along a traced centerline polyline.

This is the "Geometry Engine" stage from tcp-automation-plan.md: once the
Setup Selection Engine and dimension lookup (tcp-setup-selection-rules.md,
tcp-dimensions-reference.md) produce required lengths (buffer, taper, sign
spacing A/B/C), this module answers "where exactly is that point, measured
along the real traced road geometry" — not a straight-line offset, which
would cut across curves and land in the wrong place.

Distances in and out of this module are in whatever unit the input points
are in. The TCP dimension tables are all in feet, so callers must pass
centerline points from a feet-based projected CRS (see config/crs_config.yaml)
— this module itself is unit-agnostic and does no conversion.
"""

import math

from shapely.geometry import LineString


class InsufficientLengthError(Exception):
    """Raised when the centerline runs out before the requested distance is covered."""

    def __init__(self, requested, available):
        self.requested = requested
        self.available = available
        super().__init__(
            f"Centerline only extends {available:.2f} in this direction, "
            f"but {requested:.2f} was requested."
        )


def _segment_length(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def nearest_point_on_line(points, target):
    """Project target onto the polyline; return (segment_index, t, snapped_point).

    segment_index is the index of the segment's start vertex (points[i] -> points[i+1]).
    t in [0, 1] is how far along that segment the projection falls.
    Used so the walk can start from a work-area point that isn't necessarily
    an exact vertex of the traced centerline.
    """
    if len(points) < 2:
        raise ValueError("centerline needs at least 2 points")

    best = None
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq == 0:
            t = 0.0
        else:
            t = ((target[0] - a[0]) * dx + (target[1] - a[1]) * dy) / seg_len_sq
            t = max(0.0, min(1.0, t))
        proj = (a[0] + t * dx, a[1] + t * dy)
        dist = math.hypot(target[0] - proj[0], target[1] - proj[1])
        if best is None or dist < best[0]:
            best = (dist, i, t, proj)

    _, segment_index, t, snapped_point = best
    return segment_index, t, snapped_point


def side_of_point(points, target):
    """Return "left" or "right": which side of the centerline `target`
    falls on, relative to the direction `points` is ordered in (index 0 ->
    last). Same left/right convention as offset_edges (positive offset =
    left) — verified against Shapely's offset_curve directly, since that's
    the other place this codebase's notion of "left"/"right" comes from.

    Uses the segment nearest target (via nearest_point_on_line) to get a
    local direction vector, then the sign of the 2D cross product between
    that direction and the vector to target: positive means target is to
    the left of the direction of travel, negative means right.
    """
    segment_index, _t, _point = nearest_point_on_line(points, target)
    ax, ay = points[segment_index]
    bx, by = points[segment_index + 1]
    dx, dy = bx - ax, by - ay
    px, py = target
    cross = dx * (py - ay) - dy * (px - ax)
    return "right" if cross < 0 else "left"


def nearest_line_and_point(lines, target):
    """Given several candidate polylines (e.g. every nearby road returned by
    a lookup, or a MultiLineString's separate disconnected parts), return
    (line_index, segment_index, t, snapped_point, distance) for whichever
    line's nearest_point_on_line result is globally closest to target.

    Lines with fewer than 2 points are skipped (not enough to project onto).
    Raises ValueError if none of the lines have at least 2 points.
    """
    best = None
    for line_index, line in enumerate(lines):
        if len(line) < 2:
            continue
        segment_index, t, point = nearest_point_on_line(line, target)
        distance = math.hypot(target[0] - point[0], target[1] - point[1])
        if best is None or distance < best[4]:
            best = (line_index, segment_index, t, point, distance)

    if best is None:
        raise ValueError("no candidate line with at least 2 points")
    return best


class PolylineWalker:
    """Stateful walker along a centerline in a fixed direction.

    Repeated .advance(distance) calls move further along the line,
    continuing from wherever the previous call left off. This matches how
    TCP dimensions stack: buffer, then taper, then sign A, then B, then C,
    each measured from where the previous one ended — not all from the
    original start point.
    """

    def __init__(self, points, start_point, direction=1):
        if direction not in (1, -1):
            raise ValueError("direction must be 1 (toward line end) or -1 (toward line start)")
        self._points = points
        self._direction = direction
        segment_index, t, snapped_point = nearest_point_on_line(points, start_point)
        self._segment_index = segment_index
        self._t = t
        self.position = snapped_point

    def advance(self, distance):
        """Move `distance` further in this walker's direction; return the new point.

        Raises InsufficientLengthError if the centerline ends before the
        full distance is covered — this must not be silently truncated,
        since a short taper or missing sign is a safety issue, not a
        cosmetic one.
        """
        if distance < 0:
            raise ValueError("distance must be non-negative")

        points = self._points
        segment_index = self._segment_index
        t = self._t
        remaining = distance

        while remaining > 0:
            a, b = points[segment_index], points[segment_index + 1]
            seg_len = _segment_length(a, b)

            if self._direction == 1:
                remaining_on_segment = (1 - t) * seg_len
                if remaining <= remaining_on_segment:
                    t += remaining / seg_len if seg_len else 0.0
                    remaining = 0
                else:
                    remaining -= remaining_on_segment
                    segment_index += 1
                    t = 0.0
                    if segment_index >= len(points) - 1:
                        raise InsufficientLengthError(distance, distance - remaining)
            else:
                remaining_on_segment = t * seg_len
                if remaining <= remaining_on_segment:
                    t -= remaining / seg_len if seg_len else 0.0
                    remaining = 0
                else:
                    remaining -= remaining_on_segment
                    segment_index -= 1
                    t = 1.0
                    if segment_index < 0:
                        raise InsufficientLengthError(distance, distance - remaining)

        self._segment_index = segment_index
        self._t = t
        a, b = points[segment_index], points[segment_index + 1]
        self.position = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        return self.position


def _cumulative_stations(points):
    """Return a list the same length as points: cumulative distance from
    points[0] to each vertex. This is what lets "200 ft along the road"
    be answered without walking segment-by-segment from scratch each time.
    """
    stations = [0.0]
    for i in range(len(points) - 1):
        stations.append(stations[-1] + _segment_length(points[i], points[i + 1]))
    return stations


def _point_at_station(points, stations, target_station):
    target_station = max(0.0, min(stations[-1], target_station))
    for i in range(1, len(stations)):
        if stations[i] >= target_station:
            seg_len = stations[i] - stations[i - 1]
            frac = 0.0 if seg_len == 0 else (target_station - stations[i - 1]) / seg_len
            a, b = points[i - 1], points[i]
            return (a[0] + frac * (b[0] - a[0]), a[1] + frac * (b[1] - a[1]))
    return points[-1]


def trim_polyline_around(points, target, upstream_ft, downstream_ft):
    """Return the stretch of `points` within upstream_ft (toward the start
    of the list) and downstream_ft (toward the end) of the point on the
    centerline nearest `target` — e.g. a road line looked up from an
    external source, trimmed to the stretch actually needed around a
    work-area point. Every real intermediate vertex is kept, not just the
    two endpoints, so a curved road stays curved in the result.

    Distances are clamped to the centerline's actual extent rather than
    raising — returning a shorter-than-requested outline is correct here
    (this produces a polyline to draw, not a single definite station like
    PolylineWalker.advance), so it's on the caller to check the result
    covers what's needed.
    """
    segment_index, t, _ = nearest_point_on_line(points, target)
    stations = _cumulative_stations(points)
    anchor_station = stations[segment_index] + t * _segment_length(
        points[segment_index], points[segment_index + 1]
    )

    lo = max(0.0, anchor_station - upstream_ft)
    hi = min(stations[-1], anchor_station + downstream_ft)

    trimmed = [_point_at_station(points, stations, lo)]
    for i, station in enumerate(stations):
        if lo < station < hi:
            trimmed.append(points[i])
    trimmed.append(_point_at_station(points, stations, hi))
    return trimmed


class DegenerateOffsetError(Exception):
    """Raised when offsetting the centerline produces something other than
    a single continuous line — e.g. width_ft is so large relative to a
    tight curve's radius that the offset curve crosses itself and splits.
    Not silently picking one piece, since which piece would even be "the"
    edge in that case is ambiguous.
    """


def offset_edges(points, width_ft):
    """Return (left_edge, right_edge): the two edges of a roadway width_ft
    wide, each offset width_ft/2 from centerline `points`, on either side.

    "Left"/"right" are relative to the direction points are ordered in
    (index 0 -> last) — the side a driver's left/right hand would be on
    while traveling that direction. Uses Shapely's offset_curve, which —
    unlike naively offsetting each segment's perpendicular by hand — stays
    correct through bends: no self-intersection on a curve's inside, no
    gap on its outside.
    """
    line = LineString(points)
    half = width_ft / 2

    left_curve = line.offset_curve(half)
    right_curve = line.offset_curve(-half)

    # A too-tight curve relative to the offset distance can come back as
    # either a MultiLineString (split into pieces) or an empty LineString
    # (collapsed entirely) — both are degenerate, not usable edges.
    if (
        left_curve.geom_type != "LineString"
        or right_curve.geom_type != "LineString"
        or left_curve.is_empty
        or right_curve.is_empty
    ):
        raise DegenerateOffsetError(
            f"Offsetting by {half} ft split or collapsed the centerline — "
            "width_ft is likely too large for how tightly this road curves."
        )

    return list(left_curve.coords), list(right_curve.coords)


def zone_between(points, anchor, direction, start_ft, end_ft):
    """Return the sub-path of `points` from start_ft to end_ft feet from
    the point on the centerline nearest `anchor`, walking in `direction`
    (1 toward the end of the points list, -1 toward the start) — draws an
    actual zone (e.g. the buffer or taper stretch) as a real polyline
    segment, not just its two endpoint stations. Every real intermediate
    vertex is kept, so a curved road stays curved, matching
    trim_polyline_around's behavior.

    The result is always ordered from the start_ft end to the end_ft end
    (i.e. from nearer anchor to farther), regardless of direction.
    """
    if direction not in (1, -1):
        raise ValueError("direction must be 1 (toward line end) or -1 (toward line start)")

    segment_index, t, _ = nearest_point_on_line(points, anchor)
    stations = _cumulative_stations(points)
    anchor_station = stations[segment_index] + t * _segment_length(
        points[segment_index], points[segment_index + 1]
    )

    station_start = anchor_station + direction * start_ft
    station_end = anchor_station + direction * end_ft
    lo, hi = min(station_start, station_end), max(station_start, station_end)
    lo = max(0.0, lo)
    hi = min(stations[-1], hi)

    result = [_point_at_station(points, stations, lo)]
    for i, station in enumerate(stations):
        if lo < station < hi:
            result.append(points[i])
    result.append(_point_at_station(points, stations, hi))

    if direction == -1:
        result.reverse()
    return result


def points_at_intervals(points, anchor, direction, start_ft, end_ft, spacing_ft):
    """Return points spaced spacing_ft apart from start_ft to end_ft feet
    from the point on the centerline nearest `anchor`, walking in
    `direction` — for placing cones at regular intervals within a zone.

    Includes a point at start_ft; the last point falls at the largest
    multiple of spacing_ft from start_ft that doesn't exceed end_ft (not
    forced to land exactly on end_ft).
    """
    if direction not in (1, -1):
        raise ValueError("direction must be 1 (toward line end) or -1 (toward line start)")
    if spacing_ft <= 0:
        raise ValueError("spacing_ft must be positive")

    segment_index, t, _ = nearest_point_on_line(points, anchor)
    stations = _cumulative_stations(points)
    anchor_station = stations[segment_index] + t * _segment_length(
        points[segment_index], points[segment_index + 1]
    )

    result = []
    dist = start_ft
    while dist <= end_ft + 1e-9:
        station = max(0.0, min(stations[-1], anchor_station + direction * dist))
        result.append(_point_at_station(points, stations, station))
        dist += spacing_ft
    return result


def place_tcp_stations(points, work_area_point, direction, buffer_ft, taper_ft, sign_a_ft, sign_b_ft, sign_c_ft):
    """Walk from the work area along the centerline, placing the buffer end,
    taper start, and advance warning sign 1/2/3 positions in sequence — the
    exact layout from tcp-dimensions-reference.md:

        work area -> buffer -> taper -> sign 1 (A) -> sign 2 (B) -> sign 3 (C)

    direction is 1 to walk toward the end of the points list, -1 toward the
    start; the caller must resolve which of those is "upstream" for this
    road, since that depends on traffic direction, not on geometry alone.

    Raises InsufficientLengthError if the traced centerline doesn't extend
    far enough in the given direction to fit every station.
    """
    walker = PolylineWalker(points, work_area_point, direction)
    return {
        "buffer_end": walker.advance(buffer_ft),
        "taper_start": walker.advance(taper_ft),
        "sign_1": walker.advance(sign_a_ft),
        "sign_2": walker.advance(sign_b_ft),
        "sign_3": walker.advance(sign_c_ft),
    }

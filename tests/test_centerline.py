"""Geometry Engine validation: walking a fixed distance along a centerline.

Uses synthetic polylines with hand-computed distances (a straight line, a
right-angle bend) so every expected value here is independently verifiable
by hand, not just self-consistent with the implementation.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geometry_engine.centerline import (
    DegenerateOffsetError,
    InsufficientLengthError,
    PolylineWalker,
    nearest_line_and_point,
    nearest_point_on_line,
    offset_edges,
    place_tcp_stations,
    points_at_intervals,
    side_of_point,
    trim_polyline_around,
    zone_between,
)


def test_nearest_point_on_exact_vertex():
    line = [(0, 0), (100, 0), (200, 0)]
    segment_index, t, point = nearest_point_on_line(line, (100, 0))
    assert point == (100, 0)
    assert t in (0.0, 1.0)
    assert segment_index in (0, 1)


def test_nearest_point_projects_off_line_point():
    line = [(0, 0), (100, 0)]
    # 30 ft east, 40 ft off the line perpendicular — projection should land at (30, 0).
    segment_index, t, point = nearest_point_on_line(line, (30, 40))
    assert segment_index == 0
    assert math.isclose(point[0], 30, abs_tol=1e-9)
    assert math.isclose(point[1], 0, abs_tol=1e-9)
    assert math.isclose(t, 0.3, abs_tol=1e-9)


def test_walk_forward_on_straight_line():
    line = [(0, 0), (1000, 0)]
    walker = PolylineWalker(line, (0, 0), direction=1)
    point = walker.advance(257)
    assert math.isclose(point[0], 257, abs_tol=1e-6)
    assert math.isclose(point[1], 0, abs_tol=1e-6)


def test_walk_backward_on_straight_line():
    line = [(0, 0), (1000, 0)]
    walker = PolylineWalker(line, (1000, 0), direction=-1)
    point = walker.advance(300)
    assert math.isclose(point[0], 700, abs_tol=1e-6)
    assert math.isclose(point[1], 0, abs_tol=1e-6)


def test_walk_accumulates_across_multiple_advance_calls():
    line = [(0, 0), (1000, 0)]
    walker = PolylineWalker(line, (0, 0), direction=1)
    walker.advance(100)
    walker.advance(150)
    point = walker.advance(50)
    # 100 + 150 + 50 = 300 ft from the start.
    assert math.isclose(point[0], 300, abs_tol=1e-6)


def test_walk_crosses_a_bend():
    # Right-angle bend: (0,0) -> (100,0) -> (100,100). Walking 150 ft forward
    # from the start covers the first 100 ft leg, then 50 ft up the second leg.
    line = [(0, 0), (100, 0), (100, 100)]
    walker = PolylineWalker(line, (0, 0), direction=1)
    point = walker.advance(150)
    assert math.isclose(point[0], 100, abs_tol=1e-6)
    assert math.isclose(point[1], 50, abs_tol=1e-6)


def test_walk_backward_crosses_a_bend():
    line = [(0, 0), (100, 0), (100, 100)]
    walker = PolylineWalker(line, (100, 100), direction=-1)
    point = walker.advance(150)
    assert math.isclose(point[0], 50, abs_tol=1e-6)
    assert math.isclose(point[1], 0, abs_tol=1e-6)


def test_walk_from_midline_point_not_on_a_vertex():
    line = [(0, 0), (1000, 0)]
    # Start 40 ft off the line at x=200 — should snap to (200, 0) first.
    walker = PolylineWalker(line, (200, 40), direction=1)
    assert math.isclose(walker.position[0], 200, abs_tol=1e-6)
    point = walker.advance(50)
    assert math.isclose(point[0], 250, abs_tol=1e-6)


def test_insufficient_length_raises_with_available_distance():
    line = [(0, 0), (100, 0)]
    walker = PolylineWalker(line, (0, 0), direction=1)
    try:
        walker.advance(500)
        assert False, "expected InsufficientLengthError"
    except InsufficientLengthError as exc:
        assert math.isclose(exc.available, 100, abs_tol=1e-6)
        assert exc.requested == 500


def test_zone_between_forward_on_straight_line():
    line = [(0, 0), (1000, 0)]
    zone = zone_between(line, anchor=(0, 0), direction=1, start_ft=50, end_ft=150)
    assert zone == [(50, 0), (150, 0)]


def test_zone_between_backward_orders_from_anchor_side():
    line = [(0, 0), (1000, 0)]
    # anchor at station 500; direction=-1, start_ft=50 -> station 450,
    # end_ft=150 -> station 350. Result should run 450 -> 350 (near-anchor
    # end first), not 350 -> 450.
    zone = zone_between(line, anchor=(500, 0), direction=-1, start_ft=50, end_ft=150)
    assert zone == [(450, 0), (350, 0)]


def test_zone_between_keeps_intermediate_vertex_across_a_bend():
    line = [(0, 0), (100, 0), (100, 100)]
    zone = zone_between(line, anchor=(0, 0), direction=1, start_ft=50, end_ft=150)
    assert zone == [(50, 0), (100, 0), (100, 50)]


def test_points_at_intervals_on_straight_line():
    line = [(0, 0), (1000, 0)]
    points = points_at_intervals(line, anchor=(0, 0), direction=1, start_ft=0, end_ft=100, spacing_ft=25)
    assert points == [(0, 0), (25, 0), (50, 0), (75, 0), (100, 0)]


def test_points_at_intervals_does_not_overshoot_end_ft():
    line = [(0, 0), (1000, 0)]
    # 30 ft spacing from 0 to 100 -> stations 0, 30, 60, 90 (120 would overshoot).
    points = points_at_intervals(line, anchor=(0, 0), direction=1, start_ft=0, end_ft=100, spacing_ft=30)
    assert points == [(0, 0), (30, 0), (60, 0), (90, 0)]


def test_place_tcp_stations_matches_dimensions_reference_layout():
    # Single Shift, 35 mph worked example from tcp-dimensions-reference.md:
    # buffer 257, taper 125, A/B/C all 200 -> total upstream length 725 ft.
    line = [(0, 0), (2000, 0)]
    stations = place_tcp_stations(
        line,
        work_area_point=(0, 0),
        direction=1,
        buffer_ft=257,
        taper_ft=125,
        sign_a_ft=200,
        sign_b_ft=200,
        sign_c_ft=200,
    )
    assert math.isclose(stations["buffer_end"][0], 257, abs_tol=1e-6)
    assert math.isclose(stations["taper_start"][0], 382, abs_tol=1e-6)
    assert math.isclose(stations["sign_1"][0], 582, abs_tol=1e-6)
    assert math.isclose(stations["sign_2"][0], 782, abs_tol=1e-6)
    assert math.isclose(stations["sign_3"][0], 982, abs_tol=1e-6)


def test_nearest_line_and_point_picks_the_closer_of_two_lines():
    lines = [
        [(0, 0), (100, 0)],  # 40 ft away from (50, 40)
        [(0, 50), (100, 50)],  # 10 ft away from (50, 40)
    ]
    line_index, segment_index, t, point, distance = nearest_line_and_point(lines, (50, 40))
    assert line_index == 1
    assert math.isclose(distance, 10, abs_tol=1e-9)
    assert math.isclose(point[1], 50, abs_tol=1e-9)


def test_trim_polyline_around_straight_line():
    line = [(0, 0), (1000, 0)]
    trimmed = trim_polyline_around(line, target=(400, 0), upstream_ft=200, downstream_ft=200)
    assert trimmed[0] == (200, 0)
    assert trimmed[-1] == (600, 0)


def test_trim_polyline_around_keeps_intermediate_vertices_across_a_bend():
    # Bend at (100, 0); anchor at (50, 0), so the 100 ft downstream trim
    # should cross the bend and keep the (100, 0) vertex in between.
    line = [(0, 0), (100, 0), (100, 100)]
    trimmed = trim_polyline_around(line, target=(50, 0), upstream_ft=50, downstream_ft=100)
    assert trimmed[0] == (0, 0)
    assert (100, 0) in trimmed
    assert trimmed[-1] == (100, 50)


def test_trim_polyline_around_clamps_at_line_ends():
    line = [(0, 0), (100, 0)]
    trimmed = trim_polyline_around(line, target=(20, 0), upstream_ft=500, downstream_ft=500)
    assert trimmed[0] == (0, 0)
    assert trimmed[-1] == (100, 0)


def test_side_of_point_matches_offset_edges_left_right_convention():
    # Same line offset_edges is tested against: heading east, (0,0)->(100,0).
    line = [(0, 0), (100, 0)]
    # A point above the line (+y) sits on offset_edges' "left" edge side.
    assert side_of_point(line, (50, 10)) == "left"
    # A point below the line (-y) sits on its "right" edge side.
    assert side_of_point(line, (50, -10)) == "right"


def test_offset_edges_straight_line():
    line = [(0, 0), (100, 0)]
    left, right = offset_edges(line, width_ft=20)
    assert [(round(x, 6), round(y, 6)) for x, y in left] == [(0.0, 10.0), (100.0, 10.0)]
    assert [(round(x, 6), round(y, 6)) for x, y in right] == [(0.0, -10.0), (100.0, -10.0)]


def test_offset_edges_preserves_a_gentle_bend():
    line = [(0, 0), (100, 0), (100, 100)]
    left, right = offset_edges(line, width_ft=20)
    # Both edges should have at least 3 points (the bend survives, not
    # collapsed into a single straight chord end-to-end).
    assert len(left) >= 3
    assert len(right) >= 3


def test_offset_edges_raises_on_a_curve_too_tight_for_the_width():
    # A hairpin bend far tighter than the requested width can offset cleanly.
    line = [(0, 0), (10, 0), (10, 1), (0, 1)]
    try:
        offset_edges(line, width_ft=200)
        assert False, "expected DegenerateOffsetError"
    except DegenerateOffsetError:
        pass


def test_place_tcp_stations_raises_when_centerline_too_short():
    line = [(0, 0), (100, 0)]
    try:
        place_tcp_stations(
            line,
            work_area_point=(0, 0),
            direction=1,
            buffer_ft=257,
            taper_ft=125,
            sign_a_ft=200,
            sign_b_ft=200,
            sign_c_ft=200,
        )
        assert False, "expected InsufficientLengthError"
    except InsufficientLengthError:
        pass


if __name__ == "__main__":
    test_nearest_point_on_exact_vertex()
    test_nearest_point_projects_off_line_point()
    test_walk_forward_on_straight_line()
    test_walk_backward_on_straight_line()
    test_walk_accumulates_across_multiple_advance_calls()
    test_walk_crosses_a_bend()
    test_nearest_line_and_point_picks_the_closer_of_two_lines()
    test_trim_polyline_around_straight_line()
    test_trim_polyline_around_keeps_intermediate_vertices_across_a_bend()
    test_trim_polyline_around_clamps_at_line_ends()
    test_side_of_point_matches_offset_edges_left_right_convention()
    test_offset_edges_straight_line()
    test_offset_edges_preserves_a_gentle_bend()
    test_offset_edges_raises_on_a_curve_too_tight_for_the_width()
    test_zone_between_forward_on_straight_line()
    test_zone_between_backward_orders_from_anchor_side()
    test_zone_between_keeps_intermediate_vertex_across_a_bend()
    test_points_at_intervals_on_straight_line()
    test_points_at_intervals_does_not_overshoot_end_ft()
    test_walk_backward_crosses_a_bend()
    test_walk_from_midline_point_not_on_a_vertex()
    test_insufficient_length_raises_with_available_distance()
    test_place_tcp_stations_matches_dimensions_reference_layout()
    test_place_tcp_stations_raises_when_centerline_too_short()
    print("All Geometry Engine (walk-along-centerline) tests passed.")

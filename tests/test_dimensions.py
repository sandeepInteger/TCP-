"""Dimension Lookup validation against tcp-dimensions-reference.md.

Expected values are transcribed by hand from the doc's Master Table and
worked example, so this checks the lookup table against its own source
document, not just internal self-consistency.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tcp_rules.dimensions import UnsupportedSetupTypeError, UnsupportedSpeedError, get_dimensions


def test_worked_example_single_shift_35mph_12ft_width():
    # Matches the "Worked example" in tcp-dimensions-reference.md exactly.
    dims = get_dimensions(speed_mph=35, setup_type="shift", work_area_width_ft=12)
    assert dims["buffer_length"] == 257
    assert dims["taper_length"] == 125
    assert dims["sign_spacing_A"] == 200
    assert dims["sign_spacing_B"] == 200
    assert dims["sign_spacing_C"] == 200
    assert dims["cone_spacing_taper"] == 35
    assert dims["cone_spacing_tangent"] == 70


def test_master_table_lookup_25mph_merge():
    dims = get_dimensions(speed_mph=25, setup_type="merge", work_area_width_ft=12)
    assert dims["taper_length"] == 125
    assert dims["buffer_length"] == 158
    assert dims["sign_spacing_A"] == 100


def test_master_table_lookup_shoulder_taper_column():
    dims = get_dimensions(speed_mph=40, setup_type="shoulder", work_area_width_ft=12)
    assert dims["taper_length"] == 107


def test_20mph_row_has_blank_cells_as_none():
    dims = get_dimensions(speed_mph=20, setup_type="merge", work_area_width_ft=12)
    assert dims["taper_length"] == 80
    assert dims["buffer_length"] is None
    assert dims["sign_spacing_A"] is None
    assert dims["cone_spacing_taper"] is None


def test_width_at_exactly_12ft_uses_table_not_formula():
    # Boundary case: <= 12 must use the table, not the formula.
    dims = get_dimensions(speed_mph=35, setup_type="shift", work_area_width_ft=12)
    assert dims["taper_length"] == 125


def test_formula_taper_below_40mph_uses_quadratic_form():
    # L = W * S^2 / 60, then /2 for shift. W=20, S=35 -> L=408.333, shift=204.1667.
    dims = get_dimensions(speed_mph=35, setup_type="shift", work_area_width_ft=20)
    expected_L = 20 * 35**2 / 60
    assert math.isclose(dims["taper_length"], expected_L / 2, rel_tol=1e-9)


def test_formula_taper_at_45mph_switches_to_linear_form():
    # The doc explicitly calls out the discontinuity between 40 and 45 mph:
    # L = W * S (linear) once speed >= 45, not the quadratic form.
    dims = get_dimensions(speed_mph=45, setup_type="merge", work_area_width_ft=20)
    expected_L = 20 * 45
    assert math.isclose(dims["taper_length"], expected_L, rel_tol=1e-9)


def test_formula_taper_scales_by_setup_type():
    merge = get_dimensions(speed_mph=45, setup_type="merge", work_area_width_ft=20)
    shift = get_dimensions(speed_mph=45, setup_type="shift", work_area_width_ft=20)
    shoulder = get_dimensions(speed_mph=45, setup_type="shoulder", work_area_width_ft=20)
    assert math.isclose(shift["taper_length"], merge["taper_length"] / 2, rel_tol=1e-9)
    assert math.isclose(shoulder["taper_length"], merge["taper_length"] / 3, rel_tol=1e-9)


def test_sign_spacing_and_buffer_unaffected_by_width_formula():
    # Sign spacing/buffer always come from the table, even when width > 12
    # triggers the taper formula.
    narrow = get_dimensions(speed_mph=35, setup_type="shift", work_area_width_ft=12)
    wide = get_dimensions(speed_mph=35, setup_type="shift", work_area_width_ft=40)
    assert narrow["sign_spacing_A"] == wide["sign_spacing_A"] == 200
    assert narrow["buffer_length"] == wide["buffer_length"] == 257
    assert narrow["taper_length"] != wide["taper_length"]


def test_unsupported_speed_raises():
    try:
        get_dimensions(speed_mph=43, setup_type="merge", work_area_width_ft=12)
        assert False, "expected UnsupportedSpeedError"
    except UnsupportedSpeedError:
        pass


def test_unsupported_setup_type_raises():
    try:
        get_dimensions(speed_mph=35, setup_type="flagger", work_area_width_ft=12)
        assert False, "expected UnsupportedSetupTypeError"
    except UnsupportedSetupTypeError:
        pass


if __name__ == "__main__":
    test_worked_example_single_shift_35mph_12ft_width()
    test_master_table_lookup_25mph_merge()
    test_master_table_lookup_shoulder_taper_column()
    test_20mph_row_has_blank_cells_as_none()
    test_width_at_exactly_12ft_uses_table_not_formula()
    test_formula_taper_below_40mph_uses_quadratic_form()
    test_formula_taper_at_45mph_switches_to_linear_form()
    test_formula_taper_scales_by_setup_type()
    test_sign_spacing_and_buffer_unaffected_by_width_formula()
    test_unsupported_speed_raises()
    test_unsupported_setup_type_raises()
    print("All Dimension Lookup tests passed.")

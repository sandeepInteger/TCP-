"""Dimension Lookup stage from tcp-dimensions-reference.md.

Converts (speed, setup_type, work_area_width) into the actual feet to draw
for sign spacing, taper, buffer, and cone spacing. MASTER_TABLE below is
transcribed directly from that doc's "12 ft Offset Width" table — the
authoritative MUTCD/Caltrans-derived source for this pipeline. The taper
formula only overrides taper_length, and only when work area width > 12 ft;
sign spacing, buffer, and cone spacing always come from the table.
"""

TAPER_COLUMN_BY_SETUP = {
    "merge": "merge_taper",
    "shift": "shift_taper",
    "shoulder": "shoulder_taper",
}

TAPER_DIVISOR_BY_SETUP = {
    "merge": 1,
    "shift": 2,
    "shoulder": 3,
}

# Keyed by speed_mph. None marks a cell the reference table leaves blank ("—") —
# the 20 mph row has no defined sign spacing/buffer/cone values.
MASTER_TABLE = {
    20: {"sign_a": None, "sign_b": None, "sign_c": None, "merge_taper": 80, "shift_taper": 40, "shoulder_taper": 27, "buffer": None, "cone_taper": None, "cone_tangent": None},
    25: {"sign_a": 100, "sign_b": 100, "sign_c": 100, "merge_taper": 125, "shift_taper": 65, "shoulder_taper": 42, "buffer": 158, "cone_taper": 25, "cone_tangent": 50},
    30: {"sign_a": 150, "sign_b": 150, "sign_c": 150, "merge_taper": 180, "shift_taper": 90, "shoulder_taper": 60, "buffer": 205, "cone_taper": 30, "cone_tangent": 60},
    35: {"sign_a": 200, "sign_b": 200, "sign_c": 200, "merge_taper": 245, "shift_taper": 125, "shoulder_taper": 82, "buffer": 257, "cone_taper": 35, "cone_tangent": 70},
    40: {"sign_a": 250, "sign_b": 250, "sign_c": 250, "merge_taper": 320, "shift_taper": 160, "shoulder_taper": 107, "buffer": 315, "cone_taper": 40, "cone_tangent": 80},
    45: {"sign_a": 300, "sign_b": 300, "sign_c": 300, "merge_taper": 540, "shift_taper": 270, "shoulder_taper": 180, "buffer": 378, "cone_taper": 45, "cone_tangent": 90},
    50: {"sign_a": 350, "sign_b": 350, "sign_c": 350, "merge_taper": 600, "shift_taper": 300, "shoulder_taper": 200, "buffer": 446, "cone_taper": 50, "cone_tangent": 100},
    55: {"sign_a": 350, "sign_b": 350, "sign_c": 350, "merge_taper": 660, "shift_taper": 330, "shoulder_taper": 220, "buffer": 520, "cone_taper": 50, "cone_tangent": 100},
    60: {"sign_a": 350, "sign_b": 350, "sign_c": 350, "merge_taper": 720, "shift_taper": 360, "shoulder_taper": 240, "buffer": 598, "cone_taper": 50, "cone_tangent": 100},
    65: {"sign_a": 350, "sign_b": 350, "sign_c": 350, "merge_taper": 780, "shift_taper": 390, "shoulder_taper": 260, "buffer": 682, "cone_taper": 50, "cone_tangent": 100},
    70: {"sign_a": 350, "sign_b": 350, "sign_c": 350, "merge_taper": 840, "shift_taper": 420, "shoulder_taper": 280, "buffer": 771, "cone_taper": 50, "cone_tangent": 100},
}


class UnsupportedSpeedError(ValueError):
    pass


class UnsupportedSetupTypeError(ValueError):
    pass


def _formula_taper_length(work_area_width_ft, speed_mph):
    if speed_mph <= 40:
        return work_area_width_ft * speed_mph**2 / 60
    return work_area_width_ft * speed_mph


def get_dimensions(speed_mph, setup_type, work_area_width_ft):
    """Return sign spacing, taper, buffer, and cone spacing for this setup.

    Returns a dict with sign_spacing_A/B/C, taper_length, buffer_length,
    cone_spacing_taper, cone_spacing_tangent (feet, or None where the
    reference table has no defined value for this speed — e.g. 20 mph).

    setup_type must be "merge", "shift", or "shoulder" — the only setups
    tcp-dimensions-reference.md defines a taper for. Other setup types
    (flagger, hard/soft closure) use different lookups not covered here.

    Rules (from the doc's lookup function contract):
      - work_area_width_ft <= 12: taper_length comes straight from the table.
      - work_area_width_ft > 12: taper_length is computed via the speed-
        dependent formula, then divided by 1 (merge), 2 (shift), or 3 (shoulder).
      - sign spacing, buffer, and cone spacing always come from the table,
        regardless of work area width.
    """
    if setup_type not in TAPER_COLUMN_BY_SETUP:
        raise UnsupportedSetupTypeError(
            f"setup_type must be one of {sorted(TAPER_COLUMN_BY_SETUP)}, got {setup_type!r}"
        )
    if speed_mph not in MASTER_TABLE:
        raise UnsupportedSpeedError(
            f"speed_mph must be one of {sorted(MASTER_TABLE)}, got {speed_mph!r}"
        )

    row = MASTER_TABLE[speed_mph]
    taper_column = TAPER_COLUMN_BY_SETUP[setup_type]

    if work_area_width_ft <= 12:
        taper_length = row[taper_column]
    else:
        full_taper = _formula_taper_length(work_area_width_ft, speed_mph)
        taper_length = full_taper / TAPER_DIVISOR_BY_SETUP[setup_type]

    return {
        "sign_spacing_A": row["sign_a"],
        "sign_spacing_B": row["sign_b"],
        "sign_spacing_C": row["sign_c"],
        "taper_length": taper_length,
        "buffer_length": row["buffer"],
        "cone_spacing_taper": row["cone_taper"],
        "cone_spacing_tangent": row["cone_tangent"],
    }

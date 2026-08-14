"""Category B classification: icon -> feature type, and name text -> speed.

These are deliberately simple, config-driven rules (see
config/feature_classification.yaml) rather than inference — Category B
features need a human-confirmed mapping per tcp-automation-plan.md, not a
clever guess the pipeline is trusted to get right unsupervised.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from feature_rules.classify import classify_icon
from feature_rules.speed_limit import extract_speed_mph


def test_classify_car_icon_as_speed_limit_sign():
    assert classify_icon("files/car-24.png") == "speed_limit_sign"


def test_classify_is_case_insensitive():
    assert classify_icon("files/CAR-ICON.PNG") == "speed_limit_sign"


def test_classify_matches_other_configured_keywords():
    assert classify_icon("http://example.com/icons/taxi-cab.png") == "speed_limit_sign"


def test_classify_unrelated_icon_returns_none():
    assert classify_icon("files/pole_icon.png") is None


def test_classify_missing_icon_returns_none():
    assert classify_icon(None) is None
    assert classify_icon("") is None


def test_extract_speed_from_simple_mph_label():
    assert extract_speed_mph("25 MPH") == 25


def test_extract_speed_case_insensitive_no_space():
    assert extract_speed_mph("35mph") == 35


def test_extract_speed_from_speed_limit_phrase():
    assert extract_speed_mph("SPEED LIMIT 35 ZONE") == 35


def test_extract_speed_from_speed_limit_colon_phrase():
    assert extract_speed_mph("Speed Limit: 45") == 45


def test_extract_speed_returns_none_when_no_pattern():
    assert extract_speed_mph("Pole 42") is None


def test_extract_speed_returns_none_for_empty_name():
    assert extract_speed_mph("") is None
    assert extract_speed_mph(None) is None


if __name__ == "__main__":
    test_classify_car_icon_as_speed_limit_sign()
    test_classify_is_case_insensitive()
    test_classify_matches_other_configured_keywords()
    test_classify_unrelated_icon_returns_none()
    test_classify_missing_icon_returns_none()
    test_extract_speed_from_simple_mph_label()
    test_extract_speed_case_insensitive_no_space()
    test_extract_speed_from_speed_limit_phrase()
    test_extract_speed_from_speed_limit_colon_phrase()
    test_extract_speed_returns_none_when_no_pattern()
    test_extract_speed_returns_none_for_empty_name()
    print("All feature classification / speed extraction tests passed.")

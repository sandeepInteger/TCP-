"""Extract a numeric speed limit from a speed-limit-sign placemark's name.

Survey KMZs encode the speed limit as label text (e.g. "25 MPH",
"SPEED LIMIT 35 ZONE") rather than as a structured attribute, so this is
regex-based text extraction, not a lookup.
"""

import re

_PATTERNS = [
    re.compile(r"(\d{2,3})\s*mph", re.IGNORECASE),
    re.compile(r"speed\s*limit\D{0,10}(\d{2,3})", re.IGNORECASE),
]


def extract_speed_mph(name):
    """Return the integer speed limit parsed from `name`, or None if no
    recognizable speed pattern is found."""
    if not name:
        return None
    for pattern in _PATTERNS:
        match = pattern.search(name)
        if match:
            return int(match.group(1))
    return None

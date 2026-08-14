"""Classify a placemark's icon into a feature-type category.

Category B from tcp-automation-plan.md: raw KMZ geometry/icon data alone
never says "this is a speed limit sign" — that mapping has to come from
config, not code, so a different survey vendor's icon set only needs a
config edit in feature_classification.yaml, not a code change.
"""

from pathlib import Path
import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "feature_classification.yaml"


def load_classification_config(config_path=DEFAULT_CONFIG_PATH):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def classify_icon(icon_href, config=None):
    """Return the matching feature-type category name for an icon href
    (e.g. "speed_limit_sign"), or None if it doesn't match any configured
    category. Matching is a case-insensitive substring check against each
    category's keyword list — deliberately simple, since Category B features
    need a human to confirm the mapping is right for a given vendor's icons,
    not a clever inference the pipeline is trusted to get right unsupervised.
    """
    if not icon_href:
        return None
    if config is None:
        config = load_classification_config()

    href_lower = icon_href.lower()
    for category, rule in config.items():
        keywords = rule.get("icon_href_keywords", [])
        if any(keyword.lower() in href_lower for keyword in keywords):
            return category
    return None

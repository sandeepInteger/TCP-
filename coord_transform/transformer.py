"""Transform WGS84 lat/lon (from KML) into the projected X/Y AutoCAD needs.

The target CRS is read from config/crs_config.yaml, never hard-coded, so the
correct State Plane / UTM zone can be swapped in per job without touching code.
"""

from pathlib import Path
import yaml
from pyproj import Transformer

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "crs_config.yaml"


def load_crs_config(config_path=DEFAULT_CONFIG_PATH):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class CoordinateTransformer:
    def __init__(self, config_path=DEFAULT_CONFIG_PATH):
        config = load_crs_config(config_path)
        self.source_crs = config["source_crs"]
        self.target_crs = config["target_crs"]
        # always_xy=True keeps input/output as (lon, lat) -> (x, y),
        # matching KML's coordinate order instead of the CRS axis order.
        self._transformer = Transformer.from_crs(
            self.source_crs, self.target_crs, always_xy=True
        )
        self._inverse_transformer = Transformer.from_crs(
            self.target_crs, self.source_crs, always_xy=True
        )

    def to_xy(self, lon, lat):
        x, y = self._transformer.transform(lon, lat)
        return x, y

    def to_lonlat(self, x, y):
        lon, lat = self._inverse_transformer.transform(x, y)
        return lon, lat

    def transform_points(self, points):
        """points: iterable of (lon, lat[, alt]) -> list of (x, y)."""
        return [self.to_xy(p[0], p[1]) for p in points]

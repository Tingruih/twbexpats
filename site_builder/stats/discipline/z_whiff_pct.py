"""Z-Whiff% — whiffs on in-zone pitches / in-zone swings."""

from ...util.numbers import ratio
from ..core.pitches import is_whiff


def compute_z_whiff_pct(agg: dict):
    zone_whiffs = sum(1 for p in agg["in_zone"] if is_whiff(p))
    return ratio(zone_whiffs, len(agg["in_zone_swings"]))

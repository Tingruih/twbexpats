"""Z-Swing% — swings at in-zone pitches / in-zone pitches."""

from ...util.numbers import ratio


def compute_z_swing_pct(agg: dict):
    return ratio(len(agg["in_zone_swings"]), len(agg["in_zone"]))

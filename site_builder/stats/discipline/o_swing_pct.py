"""O-Swing% (Chase%) — swings at out-of-zone pitches / out-of-zone pitches."""

from ...util.numbers import ratio


def compute_o_swing_pct(agg: dict):
    return ratio(len(agg["out_zone_swings"]), len(agg["out_zone"]))

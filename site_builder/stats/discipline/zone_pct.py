"""Zone% — in-zone pitches / pitches with zone data."""

from ...util.numbers import ratio


def compute_zone_pct(agg: dict):
    return ratio(len(agg["in_zone"]), len(agg["in_zone"]) + len(agg["out_zone"]))

"""Whiff% — swinging strikes / swings."""

from ...util.numbers import ratio


def compute_whiff_pct(agg: dict):
    return ratio(len(agg["whiffs"]), len(agg["swings"]))

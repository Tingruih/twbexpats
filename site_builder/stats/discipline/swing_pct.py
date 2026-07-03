"""Swing% — swings / total pitches."""

from ...util.numbers import ratio


def compute_swing_pct(agg: dict):
    return ratio(len(agg["swings"]), agg["total"])

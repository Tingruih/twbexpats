"""SwStr% — swinging strikes / total pitches."""

from ...util.numbers import ratio


def compute_swstr_pct(agg: dict):
    return ratio(len(agg["whiffs"]), agg["total"])

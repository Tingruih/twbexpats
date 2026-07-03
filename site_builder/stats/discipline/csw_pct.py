"""CSW% — (called strikes + whiffs) / total pitches."""

from ...util.numbers import ratio


def compute_csw_pct(agg: dict):
    return ratio(len(agg["called"]) + len(agg["whiffs"]), agg["total"])

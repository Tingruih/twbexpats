"""ERA — earned run average: ER × 27 / outs."""

from ..core.innings import per_nine


def compute_era(earned_runs, outs):
    return per_nine(earned_runs, outs)

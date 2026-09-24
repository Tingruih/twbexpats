"""HR/9 — home runs allowed per nine innings: HR × 27 / outs."""

from ..core.innings import per_nine


def compute_hr_per_9(hr_allowed, outs):
    return per_nine(hr_allowed, outs)

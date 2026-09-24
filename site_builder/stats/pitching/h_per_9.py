"""H/9 — hits allowed per nine innings: H × 27 / outs."""

from ..core.innings import per_nine


def compute_h_per_9(hits_allowed, outs):
    return per_nine(hits_allowed, outs)

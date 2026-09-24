"""BB/9 — walks per nine innings: BB × 27 / outs."""

from ..core.innings import per_nine


def compute_bb_per_9(bb, outs):
    return per_nine(bb, outs)

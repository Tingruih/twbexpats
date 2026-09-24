"""K/9 — strikeouts per nine innings: SO × 27 / outs."""

from ..core.innings import per_nine


def compute_k_per_9(so, outs):
    return per_nine(so, outs)

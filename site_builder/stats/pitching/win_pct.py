"""Win% — W / (W + L), baseball-formatted string."""

from ..core.formatting import fmt_avg


def compute_win_pct(wins, losses):
    if wins is None or losses is None:
        return None
    total = wins + losses
    if total <= 0:
        return None
    return fmt_avg(wins / total)

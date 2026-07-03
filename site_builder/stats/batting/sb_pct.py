"""SB% — stolen-base success rate: SB / (SB + CS), baseball-formatted string."""

from ..core.formatting import fmt_avg


def compute_sb_pct(sb, cs):
    if sb is None or cs is None:
        return None
    total = sb + cs
    if total <= 0:
        return None
    return fmt_avg(sb / total)

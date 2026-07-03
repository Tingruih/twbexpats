"""Strike% — strikes / total pitches, baseball-formatted string."""

from ..core.formatting import fmt_avg


def compute_strike_pct(strikes, pitches):
    if strikes is None or not pitches or pitches <= 0:
        return None
    return fmt_avg(strikes / pitches)

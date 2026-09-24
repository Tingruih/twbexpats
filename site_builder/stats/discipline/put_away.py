"""Put Away% — strikeouts on two-strike pitches / total two-strike pitches.

Single implementation shared by the arsenal, outcome, and batter
vs-pitch-type tables (previously three copies of the same loop).
"""

from ...constants import STRIKEOUT_EVENTS
from ...util.numbers import ratio


def compute_put_away(pitches: list[dict]):
    """Return ``(put_away_pct, two_strike_count)`` for a pitch list."""
    two_strike = [p for p in pitches if p.get("pre_strikes") == 2]
    two_strike_strikeouts = sum(
        1 for p in two_strike
        if p.get("is_pa_final") and p.get("pa_event") in STRIKEOUT_EVENTS
    )
    return ratio(two_strike_strikeouts, len(two_strike)), len(two_strike)

"""Pitch-level Strike% — (strikes + balls in play) / pitches.

Distinct from ``stats.pitching.strike_pct`` (season counting-stat version):
this one classifies individual cached pitches.
"""

from ...util.numbers import ratio


def compute_pitch_strike_pct(pitches: list[dict]):
    strikes = sum(1 for p in pitches if p.get("is_strike") or p.get("is_in_play"))
    return ratio(strikes, len(pitches))

"""Batter-side splits — all/L/R versions of the pitcher pitch-type tables."""

from ...constants import BAT_SIDE_SPLITS
from .arsenal import compute_pitch_arsenal
from .outcomes import compute_pitch_outcomes
from .splits import compute_pitch_splits
from .usage_by_count import compute_pitch_usage_by_count


def compute_pitcher_bat_side_splits(pitches: list[dict]) -> dict[str, dict]:
    """Build all/L/R batter-side pitch-type tables for pitchers."""
    return compute_pitch_splits(
        pitches,
        BAT_SIDE_SPLITS,
        split_field="bat_side",
        table_fns={
            "pitch_arsenal": compute_pitch_arsenal,
            "pitch_outcomes": compute_pitch_outcomes,
            "pitch_usage_by_count": compute_pitch_usage_by_count,
        },
    )

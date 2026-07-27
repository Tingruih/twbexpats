"""Batter-side splits — all/L/R versions of the pitcher pitch-type tables."""

from ...constants import BAT_SIDE_SPLITS
from .arsenal import combine_pitch_arsenal, compute_pitch_arsenal
from .outcomes import combine_pitch_outcomes, compute_pitch_outcomes
from .splits import combine_pitch_splits, compute_pitch_splits
from .usage_by_count import (
    combine_pitch_usage_by_count,
    compute_pitch_usage_by_count,
)


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


def combine_pitcher_bat_side_splits(entries: list[dict]) -> dict:
    """Combine all/L/R batter-side pitch table splits across levels."""
    return combine_pitch_splits(
        entries,
        BAT_SIDE_SPLITS,
        sc_field="pitcher_bat_side_splits",
        table_fns={
            "pitch_arsenal": ([], combine_pitch_arsenal),
            "pitch_outcomes": ([], combine_pitch_outcomes),
            "pitch_usage_by_count": ({}, combine_pitch_usage_by_count),
        },
    )

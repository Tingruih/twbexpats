"""Batter-side splits — all/L/R versions of the pitcher pitch-type tables."""

from ...constants import BAT_SIDE_SPLITS
from .arsenal import combine_pitch_arsenal, compute_pitch_arsenal
from .outcomes import combine_pitch_outcomes, compute_pitch_outcomes
from .usage_by_count import (
    combine_pitch_usage_by_count,
    compute_pitch_usage_by_count,
)


def compute_pitcher_bat_side_splits(pitches: list[dict]) -> dict[str, dict]:
    """Build all/L/R batter-side pitch-type tables for pitchers."""
    splits: dict[str, dict] = {}
    for key, label in BAT_SIDE_SPLITS:
        if key == "all":
            split_pitches = pitches
        else:
            split_pitches = [p for p in pitches if p.get("bat_side") == key]

        splits[key] = {
            "key": key,
            "label": label,
            "pitch_arsenal": compute_pitch_arsenal(split_pitches),
            "pitch_outcomes": compute_pitch_outcomes(split_pitches),
            "pitch_usage_by_count": compute_pitch_usage_by_count(split_pitches),
        }
    return splits


def combine_pitcher_bat_side_splits(entries: list[dict]) -> dict:
    """Combine all/L/R batter-side pitch table splits across levels."""
    splits: dict[str, dict] = {}
    for key, label in BAT_SIDE_SPLITS:
        split_entries = []
        for e in entries:
            if e.get("sport_level") == "_combined":
                continue
            sc = e.get("sc") or {}
            split = (sc.get("pitcher_bat_side_splits") or {}).get(key)
            if split is None and key == "all":
                # Older payloads predate the splits field; fall back to the
                # top-level tables which are equivalent to the "all" split.
                split = {
                    "pitch_arsenal": sc.get("pitch_arsenal") or [],
                    "pitch_outcomes": sc.get("pitch_outcomes") or [],
                    "pitch_usage_by_count": sc.get("pitch_usage_by_count") or {},
                }
            if split is not None:
                split_entries.append({
                    "sport_level": e.get("sport_level"),
                    "sc": split,
                })

        splits[key] = {
            "key": key,
            "label": label,
            "pitch_arsenal": combine_pitch_arsenal(split_entries),
            "pitch_outcomes": combine_pitch_outcomes(split_entries),
            "pitch_usage_by_count": combine_pitch_usage_by_count(split_entries),
        }
    return splits

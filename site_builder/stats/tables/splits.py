"""Shared all/L/R split builder — used for both the pitcher's batter-side
splits and the batter's pitcher-hand splits (same shape: filter pitches by
one field into named buckets, then run the same set of table functions over
each bucket)."""


def compute_pitch_splits(pitches: list[dict], split_specs, split_field: str, table_fns: dict) -> dict[str, dict]:
    """Build all/L/R (or similar) splits of a set of per-pitch-type tables.

    Args:
        pitches: full pitch list for one player-level.
        split_specs: iterable of (key, label) pairs, e.g. BAT_SIDE_SPLITS.
        split_field: pitch dict field to filter on for non-"all" keys.
        table_fns: {result_key: compute_fn(pitches) -> table}.
    """
    splits: dict[str, dict] = {}
    for key, label in split_specs:
        if key == "all":
            split_pitches = pitches
        else:
            split_pitches = [p for p in pitches if p.get(split_field) == key]

        splits[key] = {
            "key": key,
            "label": label,
            **{result_key: fn(split_pitches) for result_key, fn in table_fns.items()},
        }
    return splits

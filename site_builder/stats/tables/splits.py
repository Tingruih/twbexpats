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


def combine_pitch_splits(entries: list[dict], split_specs, sc_field: str, table_fns: dict) -> dict:
    """Combine all/L/R splits across levels.

    Args:
        entries: [{sport_level, sc}] per-level entries.
        split_specs: iterable of (key, label) pairs.
        sc_field: key inside each level's ``sc`` dict holding the pre-computed splits dict.
        table_fns: {result_key: (empty_default, combine_fn)}.
    """
    splits: dict[str, dict] = {}
    for key, label in split_specs:
        split_entries = []
        for e in entries:
            if e.get("sport_level") == "_combined":
                continue
            sc = e.get("sc") or {}
            split = (sc.get(sc_field) or {}).get(key)
            if split is None and key == "all":
                # Older payloads predate the splits field; fall back to the
                # top-level tables which are equivalent to the "all" split.
                split = {
                    result_key: sc.get(result_key) or default
                    for result_key, (default, _fn) in table_fns.items()
                }
            if split is not None:
                split_entries.append({
                    "sport_level": e.get("sport_level"),
                    "sc": split,
                })

        splits[key] = {
            "key": key,
            "label": label,
            **{
                result_key: fn(split_entries)
                for result_key, (_default, fn) in table_fns.items()
            },
        }
    return splits

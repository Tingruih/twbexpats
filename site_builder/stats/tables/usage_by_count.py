"""Pitch usage by count table — pitch mix per ball-strike count bucket.

Two flavours share the same bucket/cross-tab machinery: a per-pitch-type
breakdown (pitcher arsenal tables) and a per-pitch-group breakdown (batter
fastball/breaking/offspeed tables, see ``PITCH_TYPE_GROUPS``).
"""

from ...constants import (
    COUNT_USAGE_BUCKETS,
    PITCH_GROUP_LABELS,
    PITCH_GROUP_ORDER,
    PITCH_TYPE_TO_GROUP,
)
from ...util.numbers import ratio
from ..core.pitches import filter_known_pitch_events, pre_count_tuple


def _compute_usage_by_count(pitches: list[dict], key_fn, ordered_keys=None) -> dict:
    """Shared count-bucket cross-tab for both breakdown flavours.

    ``key_fn(p)`` returns ``(key, name)`` for a pitch, or ``None`` to drop it.
    ``ordered_keys`` fixes the row order (used for the 3 pitch-groups);
    when omitted, rows are ordered by total pitch count descending.
    """
    keyed = []
    names: dict[str, str] = {}
    counts: dict[str, int] = {}
    for p in pitches:
        r = key_fn(p)
        if r is None:
            continue
        key, name = r
        keyed.append((key, p))
        counts[key] = counts.get(key, 0) + 1
        names.setdefault(key, name)

    if not counts:
        return {"pitch_types": [], "rows": []}

    if ordered_keys is None:
        ordered = sorted(counts, key=lambda k: counts[k], reverse=True)
    else:
        ordered = [k for k in ordered_keys if k in counts]

    pitch_types = [
        {"type": k, "name": names[k], "count": counts[k]} for k in ordered
    ]

    rows = []
    for bucket in COUNT_USAGE_BUCKETS:
        count_set = bucket["counts"]
        bucket_keys = [key for key, p in keyed if pre_count_tuple(p) in count_set]
        bucket_total = len(bucket_keys)
        bucket_counts = {k: 0 for k in ordered}
        for k in bucket_keys:
            if k in bucket_counts:
                bucket_counts[k] += 1

        rows.append({
            "key": bucket["key"],
            "label": bucket["label"],
            "counts_label": bucket["counts_label"],
            "pitches": bucket_total,
            "pitch_types": [
                {
                    "type": k,
                    "name": names[k],
                    "count": bucket_counts[k],
                    "pct": ratio(bucket_counts[k], bucket_total),
                }
                for k in ordered
            ],
        })

    return {"pitch_types": pitch_types, "rows": rows}


def compute_pitch_usage_by_count(pitches: list[dict]) -> dict:
    """Pitch-type usage percentages for common ball-strike count buckets."""
    pitches = filter_known_pitch_events(pitches)

    def key_fn(p):
        ptype = p.get("pitch_type") or "UN"
        return ptype, p.get("pitch_name") or ptype

    return _compute_usage_by_count(pitches, key_fn)


def compute_pitch_group_usage_by_count(pitches: list[dict]) -> dict:
    """Same breakdown as compute_pitch_usage_by_count, rolled up into the
    fastball / breaking / offspeed super-categories (PITCH_TYPE_GROUPS)."""

    def key_fn(p):
        ptype = p.get("pitch_type") or "UN"
        group = PITCH_TYPE_TO_GROUP.get(ptype)
        if group is None:
            return None
        return group, PITCH_GROUP_LABELS[group]

    return _compute_usage_by_count(pitches, key_fn, ordered_keys=PITCH_GROUP_ORDER)

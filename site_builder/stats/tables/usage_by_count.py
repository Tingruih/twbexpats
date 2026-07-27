"""Pitch usage by count table — pitch mix per ball-strike count bucket.

Two flavours share the same bucket/cross-tab machinery: a per-pitch-type
breakdown (pitcher arsenal tables) and a per-pitch-group breakdown (batter
fastball/breaking/offspeed tables, see ``PITCH_TYPE_GROUPS``).
"""

from ...constants import (
    BATTER_PLINKO_SKIP_TYPES,
    COMBINED_COUNT_USAGE_BUCKETS,
    COUNT_USAGE_BUCKETS,
    PITCH_TYPE_GROUPS,
    PITCH_TYPE_TO_GROUP,
)
from ...util.numbers import ratio
from ..core.pitches import (
    filter_known_pitch_events,
    is_unknown_pitch_type,
    pre_count_tuple,
)

PITCH_GROUP_LABELS: dict[str, str] = {
    key: label for key, label, _codes in PITCH_TYPE_GROUPS
}
PITCH_GROUP_ORDER: list[str] = [key for key, _label, _codes in PITCH_TYPE_GROUPS]


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


def _combine_usage_by_count(entries: list[dict], sc_key: str, ordered_keys=None) -> dict:
    """Shared cross-level combiner for both breakdown flavours."""
    names: dict[str, str] = {}
    totals_by_key: dict[str, int] = {}
    bucket_data = {
        key: {"pitches": 0, "counts": {}} for key, _, _ in COMBINED_COUNT_USAGE_BUCKETS
    }

    for e in entries:
        if e.get("sport_level") == "_combined":
            continue
        usage = ((e.get("sc") or {}).get(sc_key) or {})
        for pt in usage.get("pitch_types") or []:
            k = pt.get("type") or "UN"
            if is_unknown_pitch_type(k, pt.get("name")):
                continue
            names[k] = pt.get("name") or k
            totals_by_key[k] = totals_by_key.get(k, 0) + (pt.get("count") or 0)

        for row in usage.get("rows") or []:
            key = row.get("key")
            if key not in bucket_data:
                continue
            bucket = bucket_data[key]
            bucket["pitches"] += row.get("pitches") or 0
            for pt in row.get("pitch_types") or []:
                k = pt.get("type") or "UN"
                if is_unknown_pitch_type(k, pt.get("name")):
                    continue
                names.setdefault(k, pt.get("name") or k)
                bucket["counts"][k] = bucket["counts"].get(k, 0) + (pt.get("count") or 0)
                if key == "all" and k not in totals_by_key:
                    totals_by_key[k] = totals_by_key.get(k, 0) + (pt.get("count") or 0)

    if not totals_by_key:
        return {"pitch_types": [], "rows": []}

    if ordered_keys is None:
        ordered = sorted(totals_by_key, key=lambda k: totals_by_key[k], reverse=True)
    else:
        ordered = [k for k in ordered_keys if k in totals_by_key]

    pitch_types = [
        {"type": k, "name": names.get(k, k), "count": totals_by_key[k]} for k in ordered
    ]

    rows = []
    for key, label, counts_label in COMBINED_COUNT_USAGE_BUCKETS:
        bucket = bucket_data[key]
        total = bucket["pitches"]
        rows.append({
            "key": key,
            "label": label,
            "counts_label": counts_label,
            "pitches": total,
            "pitch_types": [
                {
                    "type": k,
                    "name": names.get(k, k),
                    "count": bucket["counts"].get(k, 0),
                    "pct": ratio(bucket["counts"].get(k, 0), total, digits=4),
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


def combine_pitch_usage_by_count(entries: list[dict]) -> dict:
    """Combine per-level count-bucket pitch usage by summing raw counts."""
    return _combine_usage_by_count(entries, sc_key="pitch_usage_by_count")


def compute_pitch_group_usage_by_count(pitches: list[dict]) -> dict:
    """Same breakdown as compute_pitch_usage_by_count, rolled up into the
    fastball / breaking / offspeed super-categories (PITCH_TYPE_GROUPS)."""

    def key_fn(p):
        ptype = p.get("pitch_type") or "UN"
        if ptype in BATTER_PLINKO_SKIP_TYPES:
            return None
        group = PITCH_TYPE_TO_GROUP.get(ptype)
        if group is None:
            return None
        return group, PITCH_GROUP_LABELS[group]

    return _compute_usage_by_count(pitches, key_fn, ordered_keys=PITCH_GROUP_ORDER)


def combine_pitch_group_usage_by_count(entries: list[dict]) -> dict:
    """Combine per-level count-bucket pitch-group usage across levels."""
    return _combine_usage_by_count(
        entries, sc_key="pitch_group_usage_by_count", ordered_keys=PITCH_GROUP_ORDER
    )

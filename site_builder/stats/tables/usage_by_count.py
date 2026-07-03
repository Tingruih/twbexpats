"""Pitch usage by count table — pitch-type mix per ball-strike count bucket."""

from ...constants import COMBINED_COUNT_USAGE_BUCKETS, COUNT_USAGE_BUCKETS
from ...util.numbers import ratio
from ..core.pitches import (
    filter_known_pitch_events,
    is_unknown_pitch_type,
    pre_count_tuple,
)


def compute_pitch_usage_by_count(pitches: list[dict]) -> dict:
    """Pitch-type usage percentages for common ball-strike count buckets."""
    pitches = filter_known_pitch_events(pitches)
    if not pitches:
        return {"pitch_types": [], "rows": []}

    type_counts: dict[str, int] = {}
    type_names: dict[str, str] = {}
    for p in pitches:
        ptype = p.get("pitch_type") or "UN"
        type_counts[ptype] = type_counts.get(ptype, 0) + 1
        if p.get("pitch_name") and type_names.get(ptype, ptype) == ptype:
            type_names[ptype] = p.get("pitch_name") or ptype
        else:
            type_names.setdefault(ptype, ptype)

    ordered_types = sorted(type_counts, key=lambda t: type_counts[t], reverse=True)
    pitch_types = [
        {"type": t, "name": type_names.get(t, t), "count": type_counts[t]}
        for t in ordered_types
    ]

    rows = []
    for bucket in COUNT_USAGE_BUCKETS:
        count_set = bucket["counts"]
        bucket_pitches = [p for p in pitches if pre_count_tuple(p) in count_set]

        bucket_total = len(bucket_pitches)
        bucket_type_counts = {t: 0 for t in ordered_types}
        for p in bucket_pitches:
            ptype = p.get("pitch_type") or "UN"
            if ptype in bucket_type_counts:
                bucket_type_counts[ptype] += 1

        rows.append({
            "key": bucket["key"],
            "label": bucket["label"],
            "counts_label": bucket["counts_label"],
            "pitches": bucket_total,
            "pitch_types": [
                {
                    "type": t,
                    "name": type_names.get(t, t),
                    "count": bucket_type_counts[t],
                    "pct": ratio(bucket_type_counts[t], bucket_total),
                }
                for t in ordered_types
            ],
        })

    return {"pitch_types": pitch_types, "rows": rows}


def combine_pitch_usage_by_count(entries: list[dict]) -> dict:
    """Combine per-level count-bucket pitch usage by summing raw counts."""
    type_names: dict[str, str] = {}
    totals_by_type: dict[str, int] = {}
    bucket_data = {
        key: {"pitches": 0, "type_counts": {}}
        for key, _, _ in COMBINED_COUNT_USAGE_BUCKETS
    }

    for e in entries:
        if e.get("sport_level") == "_combined":
            continue
        usage = ((e.get("sc") or {}).get("pitch_usage_by_count") or {})
        for pt in usage.get("pitch_types") or []:
            ptype = pt.get("type") or "UN"
            if is_unknown_pitch_type(ptype, pt.get("name")):
                continue
            type_names[ptype] = pt.get("name") or ptype
            totals_by_type[ptype] = totals_by_type.get(ptype, 0) + (pt.get("count") or 0)

        for row in usage.get("rows") or []:
            key = row.get("key")
            if key not in bucket_data:
                continue
            bucket = bucket_data[key]
            bucket["pitches"] += row.get("pitches") or 0
            for pt in row.get("pitch_types") or []:
                ptype = pt.get("type") or "UN"
                if is_unknown_pitch_type(ptype, pt.get("name")):
                    continue
                type_names.setdefault(ptype, pt.get("name") or ptype)
                bucket["type_counts"][ptype] = (
                    bucket["type_counts"].get(ptype, 0) + (pt.get("count") or 0)
                )
                if row.get("key") == "all" and ptype not in totals_by_type:
                    totals_by_type[ptype] = totals_by_type.get(ptype, 0) + (pt.get("count") or 0)

    if not totals_by_type:
        return {"pitch_types": [], "rows": []}

    ordered_types = sorted(totals_by_type, key=lambda t: totals_by_type[t], reverse=True)
    pitch_types = [
        {"type": t, "name": type_names.get(t, t), "count": totals_by_type[t]}
        for t in ordered_types
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
                    "type": t,
                    "name": type_names.get(t, t),
                    "count": bucket["type_counts"].get(t, 0),
                    "pct": ratio(bucket["type_counts"].get(t, 0), total, digits=4),
                }
                for t in ordered_types
            ],
        })

    return {"pitch_types": pitch_types, "rows": rows}

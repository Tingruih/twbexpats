"""Pitch Plinko — pitch-type usage across the ball-strike count graph."""

from typing import Optional

from ..constants import PLINKO_COUNT_LABELS, PLINKO_COUNTS, PLINKO_EDGES
from ..stats.core.pitches import (
    count_label,
    is_unknown_pitch_type,
    post_count_tuple,
    pre_count_tuple,
)
from ..util.numbers import ratio


def _empty_plinko_nodes() -> list[dict]:
    return [
        {"count": count_label(count), "pitches": 0, "pct": None, "pitch_types": []}
        for count in PLINKO_COUNTS
    ]


def _empty_plinko_edges() -> list[dict]:
    return [
        {"from": from_count, "to": to_count, "pitches": 0}
        for from_count, to_count in PLINKO_EDGES
    ]


def compute_pitch_plinko(
    pitches: list[dict],
    *,
    split_field: str,
    split_specs: tuple[tuple[str, str], ...],
    skip_types: Optional[set[str]] = None,
) -> dict:
    """Build Pitch Plinko data split by pitcher/batter handedness."""
    valid_counts = set(PLINKO_COUNTS)
    split_keys = {key for key, _ in split_specs}

    candidates = []
    for p in pitches:
        if p.get(split_field) not in split_keys:
            continue
        ptype = p.get("pitch_type") or "UN"
        if is_unknown_pitch_type(ptype, p.get("pitch_name")):
            continue
        if skip_types and ptype in skip_types:
            continue
        if pre_count_tuple(p) not in valid_counts:
            continue
        candidates.append(p)

    type_names: dict[str, str] = {}
    total_type_counts: dict[str, int] = {}
    for p in candidates:
        ptype = p.get("pitch_type") or "UN"
        if p.get("pitch_name") and type_names.get(ptype, ptype) == ptype:
            type_names[ptype] = p.get("pitch_name") or ptype
        else:
            type_names.setdefault(ptype, ptype)
        total_type_counts[ptype] = total_type_counts.get(ptype, 0) + 1

    ordered_types = sorted(total_type_counts, key=lambda t: total_type_counts[t], reverse=True)
    total = len(candidates)
    pitch_types = [
        {
            "type": t,
            "name": type_names.get(t, t),
            "count": total_type_counts[t],
            "pct": ratio(total_type_counts[t], total, digits=4),
        }
        for t in ordered_types
    ]

    splits = []
    edge_keys = set(PLINKO_EDGES)
    for split_key, split_label in split_specs:
        split_pitches = [p for p in candidates if p.get(split_field) == split_key]
        split_total = len(split_pitches)
        node_data = {
            count_label(count): {"pitches": 0, "type_counts": {}}
            for count in PLINKO_COUNTS
        }
        edge_counts = {edge: 0 for edge in PLINKO_EDGES}

        for p in split_pitches:
            pre_count = pre_count_tuple(p)
            if pre_count not in valid_counts:
                continue
            pre_label = count_label(pre_count)
            ptype = p.get("pitch_type") or "UN"
            bucket = node_data[pre_label]
            bucket["pitches"] += 1
            bucket["type_counts"][ptype] = bucket["type_counts"].get(ptype, 0) + 1

            post_count = post_count_tuple(p)
            if p.get("is_pa_final") or post_count not in valid_counts:
                continue
            edge = (pre_label, count_label(post_count))
            if edge in edge_keys:
                edge_counts[edge] += 1

        nodes = []
        for count in PLINKO_COUNTS:
            label = count_label(count)
            bucket = node_data[label]
            node_total = bucket["pitches"]
            node_pitch_types = [
                {
                    "type": t,
                    "name": type_names.get(t, t),
                    "count": bucket["type_counts"].get(t, 0),
                    "pct": ratio(bucket["type_counts"].get(t, 0), node_total, digits=4),
                }
                for t in ordered_types
                if bucket["type_counts"].get(t, 0)
            ]
            node_pitch_types.sort(key=lambda pt: pt.get("count", 0), reverse=True)
            nodes.append({
                "count": label,
                "pitches": node_total,
                "pct": ratio(node_total, split_total, digits=4),
                "pitch_types": node_pitch_types,
            })

        splits.append({
            "key": split_key,
            "label": split_label,
            "pitches": split_total,
            "pct": ratio(split_total, total, digits=4),
            "nodes": nodes if split_total else _empty_plinko_nodes(),
            "edges": [
                {"from": from_count, "to": to_count, "pitches": edge_counts[(from_count, to_count)]}
                for from_count, to_count in PLINKO_EDGES
            ] if split_total else _empty_plinko_edges(),
        })

    return {"total_pitches": total, "pitch_types": pitch_types, "splits": splits}


def combine_pitch_plinko(entries: list[dict]) -> dict:
    """Combine per-level Pitch Plinko nodes/edges by summing raw counts."""
    type_names: dict[str, str] = {}
    totals_by_type: dict[str, int] = {}
    split_order: list[str] = []
    split_labels: dict[str, str] = {}
    split_data: dict[str, dict] = {}

    def _new_split_bucket() -> dict:
        return {
            "pitches": 0,
            "nodes": {
                count: {"pitches": 0, "type_counts": {}}
                for count in PLINKO_COUNT_LABELS
            },
            "edges": {edge: 0 for edge in PLINKO_EDGES},
        }

    for e in entries:
        if e.get("sport_level") == "_combined":
            continue
        plinko = ((e.get("sc") or {}).get("pitch_plinko") or {})
        if not plinko:
            continue

        for pt in plinko.get("pitch_types") or []:
            ptype = pt.get("type") or "UN"
            type_names[ptype] = pt.get("name") or ptype
            totals_by_type[ptype] = totals_by_type.get(ptype, 0) + (pt.get("count") or 0)

        for split in plinko.get("splits") or []:
            split_key = split.get("key") or split.get("label") or "all"
            if split_key not in split_data:
                split_data[split_key] = _new_split_bucket()
                split_order.append(split_key)
            split_labels.setdefault(split_key, split.get("label") or split_key)
            bucket = split_data[split_key]
            bucket["pitches"] += split.get("pitches") or 0

            for node in split.get("nodes") or []:
                count = node.get("count")
                if count not in bucket["nodes"]:
                    continue
                node_bucket = bucket["nodes"][count]
                node_bucket["pitches"] += node.get("pitches") or 0
                for pt in node.get("pitch_types") or []:
                    ptype = pt.get("type") or "UN"
                    type_names.setdefault(ptype, pt.get("name") or ptype)
                    node_bucket["type_counts"][ptype] = (
                        node_bucket["type_counts"].get(ptype, 0) + (pt.get("count") or 0)
                    )

            for edge in split.get("edges") or []:
                edge_key = (edge.get("from"), edge.get("to"))
                if edge_key in bucket["edges"]:
                    bucket["edges"][edge_key] += edge.get("pitches") or 0

    if not split_data:
        return {"total_pitches": 0, "pitch_types": [], "splits": []}

    total = sum(bucket["pitches"] for bucket in split_data.values())
    ordered_types = sorted(totals_by_type, key=lambda t: totals_by_type[t], reverse=True)
    pitch_types = [
        {
            "type": t,
            "name": type_names.get(t, t),
            "count": totals_by_type[t],
            "pct": ratio(totals_by_type[t], total, digits=4),
        }
        for t in ordered_types
    ]

    splits = []
    for split_key in split_order:
        bucket = split_data[split_key]
        split_total = bucket["pitches"]
        splits.append({
            "key": split_key,
            "label": split_labels.get(split_key, split_key),
            "pitches": split_total,
            "pct": ratio(split_total, total, digits=4),
            "nodes": [
                {
                    "count": count,
                    "pitches": node_bucket["pitches"],
                    "pct": ratio(node_bucket["pitches"], split_total, digits=4),
                    "pitch_types": sorted(
                        [
                            {
                                "type": t,
                                "name": type_names.get(t, t),
                                "count": node_bucket["type_counts"].get(t, 0),
                                "pct": ratio(node_bucket["type_counts"].get(t, 0), node_bucket["pitches"], digits=4),
                            }
                            for t in ordered_types
                            if node_bucket["type_counts"].get(t, 0)
                        ],
                        key=lambda pt: pt.get("count", 0),
                        reverse=True,
                    ),
                }
                for count, node_bucket in bucket["nodes"].items()
            ],
            "edges": [
                {"from": from_count, "to": to_count, "pitches": bucket["edges"][(from_count, to_count)]}
                for from_count, to_count in PLINKO_EDGES
            ],
        })

    return {"total_pitches": total, "pitch_types": pitch_types, "splits": splits}

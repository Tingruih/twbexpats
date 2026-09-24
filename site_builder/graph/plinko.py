"""Pitch Plinko — pitch-type usage across the ball-strike count graph."""

from ..constants import PLINKO_COUNT_LABELS, PLINKO_COUNTS, PLINKO_EDGES
from ..stats.core.pitches import (
    count_label,
    filter_known_pitch_events,
    pitch_type_key,
    pitch_type_shares,
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
) -> dict:
    """Build Pitch Plinko data split by pitcher/batter handedness."""
    valid_counts = set(PLINKO_COUNTS)
    split_keys = {key for key, _ in split_specs}

    # 之後的迴圈都只走 candidates，所以球數合法與否只在這裡檢查一次
    candidates = [
        p for p in filter_known_pitch_events(pitches)
        if p.get(split_field) in split_keys and pre_count_tuple(p) in valid_counts
    ]

    total_type_counts: dict[str, int] = {}
    for p in candidates:
        ptype = pitch_type_key(p)
        total_type_counts[ptype] = total_type_counts.get(ptype, 0) + 1

    total = len(candidates)
    pitch_types = pitch_type_shares(total_type_counts, total)
    # 各節點同顆數的球種依整體用量排序，讓每一格的球種順序一致
    ordered_types = [pt["type"] for pt in pitch_types]

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
            pre_label = count_label(pre_count_tuple(p))
            ptype = pitch_type_key(p)
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
            node_type_counts = {
                t: bucket["type_counts"][t] for t in ordered_types if t in bucket["type_counts"]
            }
            nodes.append({
                "count": label,
                "pitches": node_total,
                "pct": ratio(node_total, split_total, digits=4),
                "pitch_types": pitch_type_shares(node_type_counts, node_total),
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

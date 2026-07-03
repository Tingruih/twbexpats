"""Pitch movement chart — per-pitch HB/IVB scatter points for pitchers."""

from typing import Optional

from ..stats.core.pitches import filter_known_pitch_events, is_unknown_pitch_type
from ..util.numbers import float_or_none, ratio

# Per-level payloads cap at 700 points; the cross-level combined chart allows
# more before downsampling since it merges multiple levels.
COMPUTE_MAX_POINTS = 700
COMBINE_MAX_POINTS = 900


def compute_pitch_movement_chart(
    pitches: list[dict], max_points: Optional[int] = COMPUTE_MAX_POINTS
) -> dict:
    """Return lightweight per-pitch movement points for pitcher charts."""
    points = []
    type_names: dict[str, str] = {}
    type_counts: dict[str, int] = {}

    for p in filter_known_pitch_events(pitches):
        hb = float_or_none(p.get("hb"))
        ivb = float_or_none(p.get("ivb"))
        if hb is None or ivb is None:
            continue

        ptype = p.get("pitch_type") or "UN"
        name = p.get("pitch_name") or ptype
        type_names.setdefault(ptype, name)
        if p.get("pitch_name") and type_names.get(ptype, ptype) == ptype:
            type_names[ptype] = p.get("pitch_name") or ptype
        type_counts[ptype] = type_counts.get(ptype, 0) + 1

        point = {
            "type": ptype,
            "name": type_names.get(ptype, name),
            "hb": round(hb, 1),
            "ivb": round(ivb, 1),
        }
        velo = float_or_none(p.get("start_speed"))
        spin = float_or_none(p.get("spin_rate"))
        if velo is not None:
            point["velo"] = round(velo, 1)
        if spin is not None:
            point["spin"] = int(round(spin))
        points.append(point)

    total = len(points)
    if max_points and total > max_points:
        step = total / max_points
        points = [points[min(total - 1, int(i * step))] for i in range(max_points)]

    ordered_types = sorted(type_counts, key=lambda t: type_counts[t], reverse=True)
    pitch_types = [
        {
            "type": t,
            "name": type_names.get(t, t),
            "count": type_counts[t],
            "pct": ratio(type_counts[t], total, digits=4),
        }
        for t in ordered_types
    ]

    return {
        "total_pitches": total,
        "shown_pitches": len(points),
        "pitch_types": pitch_types,
        "points": points,
    }


def combine_pitch_movement(entries: list[dict]) -> dict:
    """Combine per-level pitch movement chart payloads."""
    type_names: dict[str, str] = {}
    totals_by_type: dict[str, int] = {}
    points: list[dict] = []
    total = 0

    for e in entries:
        if e.get("sport_level") == "_combined":
            continue
        movement = ((e.get("sc") or {}).get("pitch_movement") or {})
        total += movement.get("total_pitches") or 0

        for pt in movement.get("pitch_types") or []:
            ptype = pt.get("type") or "UN"
            if is_unknown_pitch_type(ptype, pt.get("name")):
                continue
            type_names[ptype] = pt.get("name") or ptype
            totals_by_type[ptype] = totals_by_type.get(ptype, 0) + (pt.get("count") or 0)

        for point in movement.get("points") or []:
            ptype = point.get("type") or "UN"
            if is_unknown_pitch_type(ptype, point.get("name")):
                continue
            points.append(dict(point))

    if not points:
        return {"total_pitches": 0, "shown_pitches": 0, "pitch_types": [], "points": []}

    if not total:
        total = len(points)
    if not totals_by_type:
        for point in points:
            ptype = point.get("type") or "UN"
            type_names.setdefault(ptype, point.get("name") or ptype)
            totals_by_type[ptype] = totals_by_type.get(ptype, 0) + 1

    if len(points) > COMBINE_MAX_POINTS:
        step = len(points) / COMBINE_MAX_POINTS
        points = [
            points[min(len(points) - 1, int(i * step))]
            for i in range(COMBINE_MAX_POINTS)
        ]

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

    return {
        "total_pitches": total,
        "shown_pitches": len(points),
        "pitch_types": pitch_types,
        "points": points,
    }

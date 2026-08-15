"""Pitch movement chart — per-pitch HB/IVB scatter points for pitchers."""

from typing import Optional

from ..stats.core.pitches import filter_known_pitch_events
from ..util.numbers import float_or_none, ratio

# Scatter payloads are downsampled past this many points to keep the page light.
COMPUTE_MAX_POINTS = 700


def compute_pitch_movement_chart(
    pitches: list[dict], max_points: Optional[int] = COMPUTE_MAX_POINTS
) -> dict:
    """Return lightweight per-pitch movement points for pitcher charts.

    Each point is a fixed-order ``[type, hb, ivb, velo, spin]`` array rather
    than a dict: up to ``COMPUTE_MAX_POINTS`` of them ship inside every page,
    so dropping the repeated keys is a real payload win. Missing velo/spin stay
    as ``None`` placeholders to keep the positions stable.
    """
    points = []
    type_counts: dict[str, int] = {}

    for p in filter_known_pitch_events(pitches):
        hb = float_or_none(p.get("hb"))
        ivb = float_or_none(p.get("ivb"))
        if hb is None or ivb is None:
            continue

        ptype = p.get("pitch_type") or "UN"
        type_counts[ptype] = type_counts.get(ptype, 0) + 1

        velo = float_or_none(p.get("start_speed"))
        spin = float_or_none(p.get("spin_rate"))
        points.append([
            ptype,
            round(hb, 1),
            round(ivb, 1),
            round(velo, 1) if velo is not None else None,
            int(round(spin)) if spin is not None else None,
        ])

    total = len(points)
    if max_points and total > max_points:
        step = total / max_points
        points = [points[min(total - 1, int(i * step))] for i in range(max_points)]

    ordered_types = sorted(type_counts, key=lambda t: type_counts[t], reverse=True)
    pitch_types = [
        {
            "type": t,
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

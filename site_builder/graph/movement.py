"""Pitch movement chart — per-pitch HB/IVB scatter points for pitchers."""

from typing import Optional

from ..stats.core.pitches import filter_known_pitch_events, pitch_type_key, pitch_type_shares
from ..util.numbers import round_half_up, safe_float

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
        hb = safe_float(p.get("hb"))
        ivb = safe_float(p.get("ivb"))
        if hb is None or ivb is None:
            continue

        ptype = pitch_type_key(p)
        type_counts[ptype] = type_counts.get(ptype, 0) + 1

        velo = safe_float(p.get("start_speed"))
        spin = safe_float(p.get("spin_rate"))
        points.append([ptype, hb, ivb, velo, spin])

    total = len(points)
    if max_points and total > max_points:
        step = total / max_points
        points = [points[min(total - 1, int(i * step))] for i in range(max_points)]
    # 降採樣之後才捨入：只處理實際輸出的點
    points = [
        [
            ptype,
            round_half_up(hb, 1),
            round_half_up(ivb, 1),
            round_half_up(velo, 1) if velo is not None else None,
            int(round_half_up(spin, 0)) if spin is not None else None,
        ]
        for ptype, hb, ivb, velo, spin in points
    ]

    pitch_types = pitch_type_shares(type_counts, total)

    return {
        "total_pitches": total,
        "shown_pitches": len(points),
        "pitch_types": pitch_types,
        "points": points,
    }

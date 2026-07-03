"""Cross-level combined Statcast summary (the "合計" row at build time)."""

from ..graph.movement import combine_pitch_movement
from ..graph.plinko import combine_pitch_plinko
from .tables.arsenal import combine_pitch_arsenal
from .tables.bat_side_splits import combine_pitcher_bat_side_splits
from .tables.outcomes import combine_pitch_outcomes
from .tables.usage_by_count import combine_pitch_usage_by_count
from .tables.vs_pitch_types import combine_vs_pitch_types


def combine_statcast_dicts(entries: list[dict]) -> dict:
    """Compute a weighted-average combined statcast dict from multiple level entries.

    Args:
        entries: list of {sport_level, team_name, sc} dicts (the per-level entries).

    Returns:
        A combined sc dict suitable for display in a summary row.
        pitch_arsenal and vs_pitch_types are computed as count-weighted averages.
    """
    scs = [e["sc"] for e in entries if e.get("sc")]
    if not scs:
        return {}
    if len(scs) == 1:
        return dict(scs[0])

    def _wsum(field, weight_field):
        """Weighted sum of (value * weight) and sum of weights."""
        total_w = 0.0
        total_wv = 0.0
        for sc in scs:
            v = sc.get(field)
            w = sc.get(weight_field) or 0
            if v is not None and w:
                total_w += w
                total_wv += v * w
        return total_wv, total_w

    def _wpct(field, weight_field, digits=3):
        wv, w = _wsum(field, weight_field)
        if not w:
            return None
        return round(wv / w, digits)

    total_p = sum((sc.get("total_pitches") or 0) for sc in scs)
    total_bbe = sum((sc.get("bbe") or 0) for sc in scs)
    total_pa = sum((sc.get("pa_count") or 0) for sc in scs)

    # Pitch-discipline fields — weight by total_pitches
    pitch_pct_fields = [
        "swing_pct", "swstr_pct", "csw_pct", "zone_pct", "strike_pct",
        "z_swing_pct", "o_swing_pct", "z_contact_pct", "whiff_pct",
        "avg_extension",
    ]
    # BBE-based fields — weight by bbe
    bbe_fields = [
        "barrel_pct", "hard_hit_pct", "avg_ev", "avg_la", "swsp_pct",
        "gb_pct", "ld_pct", "fb_pct", "pu_pct", "air_pct", "pull_pct",
        "straight_pct", "oppo_pct", "pull_air_pct", "hr_fb_pct", "ev90",
    ]
    # PA-based fields — weight by pa_count
    pa_fields = ["woba", "woba_against"]

    combined: dict = {
        "total_pitches": total_p,
        "bbe": total_bbe,
        "pa_count": total_pa,
    }
    for f in pitch_pct_fields:
        combined[f] = _wpct(f, "total_pitches")
    for f in bbe_fields:
        combined[f] = _wpct(f, "bbe")
    for f in pa_fields:
        combined[f] = _wpct(f, "pa_count")

    # max_ev — take the maximum across levels
    max_evs = [sc.get("max_ev") for sc in scs if sc.get("max_ev") is not None]
    combined["max_ev"] = round(max(max_evs), 1) if max_evs else None

    # pitch_arsenal / vs_pitch_types: combine using count-weighted averages
    combined["pitch_arsenal"] = combine_pitch_arsenal(entries)
    combined["vs_pitch_types"] = combine_vs_pitch_types(entries)
    combined["pitch_outcomes"] = combine_pitch_outcomes(entries)
    combined["pitch_usage_by_count"] = combine_pitch_usage_by_count(entries)
    combined["pitcher_bat_side_splits"] = combine_pitcher_bat_side_splits(entries)
    combined["pitch_plinko"] = combine_pitch_plinko(entries)
    combined["pitch_movement"] = combine_pitch_movement(entries)

    return combined

"""Pitch outcomes table — per-pitch-type result quality for a pitcher
(strike/whiff/CSW rates, put-away, AVG/wOBA against, contact quality)."""

from ...util.numbers import ratio
from ..core.pa_outcomes import compute_pa_outcome_totals
from ..core.pitches import aggregate_pitches, filter_known_pitch_events
from ..discipline.pitch_strike_pct import compute_pitch_strike_pct
from ..discipline.put_away import compute_put_away
from ..discipline.z_whiff_pct import compute_z_whiff_pct
from .weighted import combine_pitch_type_data


def compute_pitch_outcomes(pitches: list[dict]) -> list[dict]:
    """Per-pitch-type outcome breakdown for a pitcher."""
    pitches = filter_known_pitch_events(pitches)
    if not pitches:
        return []

    total = len(pitches)

    by_type: dict[str, list[dict]] = {}
    for p in pitches:
        t = p.get("pitch_type") or "UN"
        by_type.setdefault(t, []).append(p)

    out = []
    for ptype, ps in by_type.items():
        n = len(ps)
        agg = aggregate_pitches(ps)
        totals = compute_pa_outcome_totals(agg["pa_final"])
        put_away_pct, two_strike_count = compute_put_away(ps)
        name = next((p.get("pitch_name") for p in ps if p.get("pitch_name")), ptype)

        out.append({
            "type": ptype,
            "name": name,
            "count": n,
            "pct": ratio(n, total),
            "strike_pct": compute_pitch_strike_pct(ps),
            "z_whiff_pct": compute_z_whiff_pct(agg),
            "o_swing_pct": ratio(len(agg["out_zone_swings"]), len(agg["out_zone"])),
            "swstr_pct": ratio(len(agg["whiffs"]), n),
            "csw_pct": ratio(len(agg["called"]) + len(agg["whiffs"]), n),
            "put_away_pct": put_away_pct,
            "two_strike_count": two_strike_count,
            "avg": ratio(totals["hits"], totals["ab"]),
            "woba": ratio(totals["woba_num"], totals["woba_den"]),
            "barrel_pct": ratio(agg["barrels"], len(agg["in_play"])),
            "hard_hit_pct": ratio(agg["hard_hits"], len(agg["bbe_ev"])),
        })
    out.sort(key=lambda r: r.get("count", 0), reverse=True)
    return out


def combine_pitch_outcomes(entries: list[dict]) -> list[dict]:
    """Combine per-level pitcher pitch_outcomes into a count-weighted list."""
    return combine_pitch_type_data(
        entries,
        sc_key="pitch_outcomes",
        rate_fields=[
            "strike_pct", "z_whiff_pct", "o_swing_pct", "swstr_pct",
            "csw_pct", "avg", "woba", "barrel_pct", "hard_hit_pct",
        ],
        include_pct=True,
    )

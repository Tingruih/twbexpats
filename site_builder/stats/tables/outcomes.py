"""Pitch outcomes table — per-pitch-type result quality for a pitcher
(strike/whiff/CSW rates, put-away, AVG/wOBA against, contact quality)."""

from ...util.numbers import ratio
from ..advanced.woba import compute_pitch_woba
from ..batted_ball.barrel import compute_barrel_pct
from ..batted_ball.hard_hit import compute_hard_hit_pct
from ..batting.avg import compute_avg
from ..core.pa_outcomes import compute_pa_outcome_totals
from ..core.pitches import aggregate_pitches, filter_known_pitch_events
from ..discipline.csw_pct import compute_csw_pct
from ..discipline.o_swing_pct import compute_o_swing_pct
from ..discipline.pitch_strike_pct import compute_pitch_strike_pct
from ..discipline.put_away import compute_put_away
from ..discipline.swstr_pct import compute_swstr_pct
from ..discipline.z_whiff_pct import compute_z_whiff_pct


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
            "o_swing_pct": compute_o_swing_pct(agg),
            "swstr_pct": compute_swstr_pct(agg),
            "csw_pct": compute_csw_pct(agg),
            "put_away_pct": put_away_pct,
            "two_strike_count": two_strike_count,
            "avg": compute_avg(totals["hits"], totals["ab"]),
            "woba": compute_pitch_woba(totals),
            "barrel_pct": compute_barrel_pct(agg),
            "hard_hit_pct": compute_hard_hit_pct(agg),
        })
    out.sort(key=lambda r: r.get("count", 0), reverse=True)
    return out

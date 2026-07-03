"""Vs-pitch-types table — how a batter fares against each pitch type."""

from ...constants import BATTER_PLINKO_SKIP_TYPES
from ..advanced.woba import compute_pitch_woba
from ..batted_ball.barrel import compute_barrel_pct
from ..batted_ball.hard_hit import compute_hard_hit_pct
from ..batting.avg import compute_avg
from ..core.pa_outcomes import compute_pa_outcome_totals
from ..core.pitches import aggregate_pitches
from ..discipline.csw_pct import compute_csw_pct
from ..discipline.o_swing_pct import compute_o_swing_pct
from ..discipline.pitch_strike_pct import compute_pitch_strike_pct
from ..discipline.put_away import compute_put_away
from ..discipline.swstr_pct import compute_swstr_pct
from ..discipline.whiff_pct import compute_whiff_pct
from ..discipline.z_swing_pct import compute_z_swing_pct
from ..discipline.zone_pct import compute_zone_pct
from .weighted import combine_pitch_type_data


def compute_vs_pitch_types(pitches: list[dict]) -> list[dict]:
    """Per-pitch-type breakdown for a batter."""
    # EP (Eephus) and FA (generic Fastball) almost exclusively appear in
    # position-player-pitching situations (e.g. catcher or shortstop mops up
    # in a blowout).  Exclude them so they don't pollute the breakdown or
    # show as spurious pitch types (matching TJStats / Baseball Savant behaviour).
    by_type: dict[str, list[dict]] = {}
    for p in pitches:
        t = p.get("pitch_type") or "UN"
        if t in BATTER_PLINKO_SKIP_TYPES:
            continue
        by_type.setdefault(t, []).append(p)

    # Drop the UN (unknown) bucket when there are real named pitch types,
    # so unknown pitches don't pollute the per-type breakdown.
    if any(t != "UN" for t in by_type):
        by_type = {t: v for t, v in by_type.items() if t != "UN"}

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
            "strike_pct": compute_pitch_strike_pct(ps),
            "zone_pct": compute_zone_pct(agg),
            "z_swing_pct": compute_z_swing_pct(agg),
            "o_swing_pct": compute_o_swing_pct(agg),
            "whiff_pct": compute_whiff_pct(agg),
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


def combine_vs_pitch_types(entries: list[dict]) -> list[dict]:
    """Combine per-level vs_pitch_types into a single count-weighted list."""
    return combine_pitch_type_data(
        entries,
        sc_key="vs_pitch_types",
        rate_fields=[
            "strike_pct", "zone_pct", "z_swing_pct", "o_swing_pct",
            "whiff_pct", "swstr_pct", "csw_pct",
            "avg", "woba", "barrel_pct", "hard_hit_pct",
        ],
    )

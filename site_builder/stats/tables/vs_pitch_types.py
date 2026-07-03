"""Vs-pitch-types table — how a batter fares against each pitch type."""

from ...constants import BATTER_PLINKO_SKIP_TYPES
from ...util.numbers import ratio
from ..core.pa_outcomes import compute_pa_outcome_totals
from ..core.pitches import aggregate_pitches
from ..discipline.pitch_strike_pct import compute_pitch_strike_pct
from ..discipline.put_away import compute_put_away
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
            "zone_pct": ratio(len(agg["in_zone"]), len(agg["in_zone"]) + len(agg["out_zone"])),
            "z_swing_pct": ratio(len(agg["in_zone_swings"]), len(agg["in_zone"])),
            "o_swing_pct": ratio(len(agg["out_zone_swings"]), len(agg["out_zone"])),
            "whiff_pct": ratio(len(agg["whiffs"]), len(agg["swings"])),
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

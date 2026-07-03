"""Pitch arsenal table — per-pitch-type physical characteristics for a pitcher
(velo, movement, spin, release) plus zone/chase/whiff/put-away/wOBA results."""

from ...util.numbers import mean_round, ratio
from ..advanced.woba import compute_pitch_woba
from ..core.pa_outcomes import compute_pa_outcome_totals
from ..core.pitches import aggregate_pitches, filter_known_pitch_events
from ..discipline.o_swing_pct import compute_o_swing_pct
from ..discipline.put_away import compute_put_away
from ..discipline.whiff_pct import compute_whiff_pct
from ..discipline.zone_pct import compute_zone_pct
from .weighted import combine_pitch_type_data


def compute_pitch_arsenal(pitches: list[dict]) -> list[dict]:
    """Per-pitch-type breakdown for a pitcher."""
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
        name = next((p.get("pitch_name") for p in ps if p.get("pitch_name")), ptype)
        put_away_pct, two_strike_count = compute_put_away(ps)

        out.append({
            "type": ptype,
            "name": name,
            "count": n,
            "pct": ratio(n, total),
            "velo": mean_round([p.get("start_speed") for p in ps], 1),
            "ivb": mean_round([p.get("ivb") for p in ps], 1),
            "hb": mean_round([p.get("hb") for p in ps], 1),
            "spin": mean_round([p.get("spin_rate") for p in ps], 0),
            "extension": mean_round([p.get("extension") for p in ps], 2),
            "v_rel": mean_round([p.get("z0") for p in ps], 2),
            "h_rel": mean_round([p.get("x0") for p in ps], 2),
            "zone_pct": compute_zone_pct(agg),
            "chase_pct": compute_o_swing_pct(agg),
            "whiff_pct": compute_whiff_pct(agg),
            "put_away_pct": put_away_pct,
            "two_strike_count": two_strike_count,
            "woba": compute_pitch_woba(totals),
        })
    out.sort(key=lambda r: r.get("count", 0), reverse=True)
    return out


def combine_pitch_arsenal(entries: list[dict]) -> list[dict]:
    """Combine per-level pitch_arsenal into a single count-weighted list."""
    return combine_pitch_type_data(
        entries,
        sc_key="pitch_arsenal",
        rate_fields=[
            "velo", "ivb", "hb", "spin", "extension", "v_rel", "h_rel",
            "zone_pct", "chase_pct", "whiff_pct", "woba",
        ],
        include_pct=True,
    )

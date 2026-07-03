"""Pitch arsenal table — per-pitch-type physical characteristics for a pitcher
(velo, movement, spin, release) plus zone/chase/whiff/put-away/wOBA results."""

from ...util.numbers import mean_round, ratio
from ..advanced.woba import compute_pitch_woba
from ..core.pitches import aggregate_pitches, filter_known_pitch_events
from ..discipline.put_away import compute_put_away
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
        woba_num, woba_den = compute_pitch_woba(agg["pa_final"])
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
            "zone_pct": ratio(len(agg["in_zone"]), len(agg["in_zone"]) + len(agg["out_zone"])),
            "chase_pct": ratio(len(agg["out_zone_swings"]), len(agg["out_zone"])),
            "whiff_pct": ratio(len(agg["whiffs"]), len(agg["swings"])),
            "put_away_pct": put_away_pct,
            "two_strike_count": two_strike_count,
            "woba": ratio(woba_num, woba_den),
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

"""Vs-pitch-types table — how a batter fares against each pitch type."""

from ...constants import (
    BATTER_PLINKO_SKIP_TYPES,
    PITCH_HAND_SPLITS,
    PITCH_TYPE_GROUPS,
    PITCH_TYPE_TO_GROUP,
)
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
from ..discipline.whiff_pct import compute_whiff_pct
from ..discipline.z_swing_pct import compute_z_swing_pct
from ..discipline.zone_pct import compute_zone_pct
from .splits import compute_pitch_splits
from .usage_by_count import compute_pitch_group_usage_by_count


VS_PITCH_RATE_FIELDS = [
    "strike_pct", "zone_pct", "z_swing_pct", "o_swing_pct",
    "whiff_pct", "swstr_pct", "csw_pct",
    "avg", "woba", "barrel_pct", "hard_hit_pct",
]


def _compute_pitch_bucket_row(key: str, name: str, ps: list[dict]) -> dict:
    """Stat row for one bucket of pitches — shared by the per-pitch-type and
    per-pitch-group tables so the two breakdowns can never drift apart."""
    agg = aggregate_pitches(ps)
    totals = compute_pa_outcome_totals(agg["pa_final"])
    put_away_pct, two_strike_count = compute_put_away(ps)

    return {
        "type": key,
        "name": name,
        "count": len(ps),
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
    }


def compute_vs_pitch_types(pitches: list[dict]) -> list[dict]:
    """Per-pitch-type breakdown for a batter."""
    pitches = filter_known_pitch_events(pitches)

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

    out = [
        _compute_pitch_bucket_row(
            ptype,
            next((p.get("pitch_name", "") for p in ps if p.get("pitch_name")), ptype),
            ps,
        )
        for ptype, ps in by_type.items()
    ]
    out.sort(key=lambda r: r.get("count", 0), reverse=True)
    return out


def compute_vs_pitch_groups(pitches: list[dict]) -> list[dict]:
    """Same breakdown as compute_vs_pitch_types, rolled up into the
    fastball / breaking / offspeed super-categories (PITCH_TYPE_GROUPS)."""
    by_group: dict[str, list[dict]] = {}
    for p in pitches:
        t = p.get("pitch_type") or "UN"
        if t in BATTER_PLINKO_SKIP_TYPES:
            continue
        group = PITCH_TYPE_TO_GROUP.get(t)
        if group is None:
            continue
        by_group.setdefault(group, []).append(p)

    return [
        _compute_pitch_bucket_row(key, label, by_group[key])
        for key, label, _codes in PITCH_TYPE_GROUPS
        if by_group.get(key)
    ]


def compute_batter_pitch_hand_splits(pitches: list[dict]) -> dict[str, dict]:
    """Build all/L/R pitcher-hand splits of the vs-pitch-types /
    vs-pitch-groups / pitch-group-usage-by-count tables for batters."""
    return compute_pitch_splits(
        pitches,
        PITCH_HAND_SPLITS,
        split_field="pitch_hand",
        table_fns={
            "vs_pitch_types": compute_vs_pitch_types,
            "vs_pitch_groups": compute_vs_pitch_groups,
            "pitch_group_usage_by_count": compute_pitch_group_usage_by_count,
        },
    )

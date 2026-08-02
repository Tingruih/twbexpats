"""Season-level batter Statcast aggregation entry point."""

from ..constants import BATTER_PLINKO_SPLITS
from ..graph.plinko import compute_pitch_plinko
from .advanced.woba import compute_pitch_woba
from .batted_ball import batted_ball_metrics
from .batted_ball.exit_velocity import compute_ev90, compute_max_ev
from .batted_ball.launch_angle import compute_avg_la
from .batted_ball.sweet_spot import compute_sweet_spot_pct
from .core.atypical import annotate_atypical
from .core.pa_outcomes import compute_pa_outcome_totals
from .core.pitches import aggregate_pitches, ensure_pre_strikes
from .discipline import discipline_metrics
from .discipline.pitch_strike_pct import compute_pitch_strike_pct
from .tables.usage_by_count import compute_pitch_group_usage_by_count
from .tables.vs_pitch_types import (
    compute_batter_pitch_hand_splits,
    compute_vs_pitch_groups,
    compute_vs_pitch_types,
)


def compute_batter_statcast(pitches: list[dict]) -> dict:
    """Season-level batter aggregates from pitch list."""
    if not pitches:
        return {}

    # Ensure every pitch has a pre_strikes field (backfills cached data
    # that predates the field being added to extract_pitch_logs).
    ensure_pre_strikes(pitches)
    # Cross-pitch context (currently: PA-level bunt-attempt membership)
    # for the atypical-pitch exclusion framework. Must run before any
    # pitch_hand split divides the list (core/atypical.py docstring).
    annotate_atypical(pitches)

    agg = aggregate_pitches(pitches)
    totals = compute_pa_outcome_totals(agg["pa_final"])

    la_in_play = [p for p in agg["in_play"] if p.get("la") is not None]
    la_values = [p["la"] for p in la_in_play]

    result = {
        "total_pitches": agg["total"],
        "pa_count": totals["woba_den"],
        "strike_pct": compute_pitch_strike_pct(pitches),
        "woba": compute_pitch_woba(totals),
        "max_ev": compute_max_ev(agg["bbe_ev"]),
        "ev90": compute_ev90(agg["bbe_ev"]),
        "avg_la": compute_avg_la(la_values),
        "swsp_pct": compute_sweet_spot_pct(la_values),
        "vs_pitch_types": compute_vs_pitch_types(pitches),
        "vs_pitch_groups": compute_vs_pitch_groups(pitches),
        "pitch_group_usage_by_count": compute_pitch_group_usage_by_count(pitches),
        "batter_pitch_hand_splits": compute_batter_pitch_hand_splits(pitches),
        "pitch_plinko": compute_pitch_plinko(
            pitches,
            split_field="pitch_hand",
            split_specs=BATTER_PLINKO_SPLITS,
        ),
    }
    result.update(discipline_metrics(agg))
    result.update(batted_ball_metrics(agg))
    return result

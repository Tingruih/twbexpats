"""Season-level batter Statcast aggregation entry point."""

from ..constants import BATTER_PLINKO_SPLITS
from ..graph.plinko import compute_pitch_plinko
from .advanced.woba import compute_pitch_woba
from .batted_ball import batted_ball_metrics
from .batted_ball.exit_velocity import compute_ev90, compute_max_ev
from .batted_ball.launch_angle import collect_la_values, compute_avg_la
from .batted_ball.sweet_spot import compute_sweet_spot_pct
from .core.atypical import annotate_atypical
from .core.pa_outcomes import compute_pa_outcome_totals
from .core.pitches import aggregate_pitches
from .discipline import discipline_metrics
from .discipline.pitch_strike_pct import compute_pitch_strike_pct
from .tables.vs_pitch_types import compute_batter_pitch_hand_splits


def compute_batter_statcast(pitches: list[dict]) -> dict:
    """Season-level batter aggregates from pitch list."""
    if not pitches:
        return {}

    # Cross-pitch context (currently: PA-level bunt-attempt membership)
    # for the atypical-pitch exclusion framework. Must run before any
    # pitch_hand split divides the list (core/atypical.py docstring).
    annotate_atypical(pitches)

    agg = aggregate_pitches(pitches)
    totals = compute_pa_outcome_totals(agg["pa_final"])

    la_values = collect_la_values(agg["in_play"])
    # 球種表只算一次：頂層欄位直接沿用 "all" 分組（與 pitcher_statcast 相同作法），
    # 避免兩份「全部」各自計算而漂移
    hand_splits = compute_batter_pitch_hand_splits(pitches)
    all_split = hand_splits["all"]

    result = {
        "total_pitches": agg["total"],
        "pa_count": totals["woba_den"],
        "strike_pct": compute_pitch_strike_pct(pitches),
        "woba": compute_pitch_woba(totals),
        "max_ev": compute_max_ev(agg["bbe_ev"]),
        "ev90": compute_ev90(agg["bbe_ev"]),
        "avg_la": compute_avg_la(la_values),
        "swsp_pct": compute_sweet_spot_pct(la_values),
        "vs_pitch_types": all_split["vs_pitch_types"],
        "vs_pitch_groups": all_split["vs_pitch_groups"],
        "pitch_group_usage_by_count": all_split["pitch_group_usage_by_count"],
        "batter_pitch_hand_splits": hand_splits,
        "pitch_plinko": compute_pitch_plinko(
            pitches,
            split_field="pitch_hand",
            split_specs=BATTER_PLINKO_SPLITS,
        ),
    }
    result.update(discipline_metrics(agg))
    result.update(batted_ball_metrics(agg))
    return result

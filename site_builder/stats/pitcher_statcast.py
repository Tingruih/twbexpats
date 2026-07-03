"""Season-level pitcher Statcast aggregation entry point."""

from ..constants import PITCHER_PLINKO_SPLITS
from ..graph.movement import compute_pitch_movement_chart
from ..graph.plinko import compute_pitch_plinko
from ..util.numbers import ratio
from .advanced.woba import compute_pitch_woba
from .batted_ball import batted_ball_metrics
from .batted_ball.extension import compute_avg_extension
from .batted_ball.hr_fb import compute_hr_fb_pct
from .core.pitches import aggregate_pitches, ensure_pre_strikes
from .discipline import discipline_metrics
from .tables.bat_side_splits import compute_pitcher_bat_side_splits


def compute_pitcher_statcast(pitches: list[dict]) -> dict:
    """Season-level pitcher aggregates from pitch list."""
    if not pitches:
        return {}

    # Ensure every pitch has a pre_strikes field (backfills cached data
    # that predates the field being added to extract_pitch_logs).
    ensure_pre_strikes(pitches)

    agg = aggregate_pitches(pitches)
    woba_num, woba_den = compute_pitch_woba(agg["pa_final"])
    bat_side_splits = compute_pitcher_bat_side_splits(pitches)

    result = {
        "total_pitches": agg["total"],
        "pa_count": woba_den,
        "woba_against": ratio(woba_num, woba_den),
        "hr_fb_pct": compute_hr_fb_pct(agg["pa_final"], agg["fb"]),
        "avg_extension": compute_avg_extension(pitches),
        "pitch_arsenal": bat_side_splits["all"]["pitch_arsenal"],
        "pitch_outcomes": bat_side_splits["all"]["pitch_outcomes"],
        "pitch_usage_by_count": bat_side_splits["all"]["pitch_usage_by_count"],
        "pitcher_bat_side_splits": bat_side_splits,
        "pitch_plinko": compute_pitch_plinko(
            pitches,
            split_field="bat_side",
            split_specs=PITCHER_PLINKO_SPLITS,
        ),
        "pitch_movement": compute_pitch_movement_chart(pitches),
    }
    result.update(discipline_metrics(agg))
    result.update(batted_ball_metrics(agg))
    return result

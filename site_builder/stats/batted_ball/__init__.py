"""Batted-ball quality metrics from pitch-level data — one stat per file.

Modules hold each stat's *definition* (barrel window, hard-hit threshold,
sweet-spot band, spray-angle formula); the rate assembly below reads the
counts produced by ``stats.core.pitches.aggregate_pitches``.
"""

from ...constants import BATTED_BALL_RATE_DIGITS
from ...util.numbers import ratio
from .exit_velocity import compute_avg_ev


def batted_ball_metrics(agg: dict) -> dict:
    """Build the batted-ball metrics dict from aggregate_pitches output."""
    n_ip = len(agg["in_play"])
    n_ev = len(agg["bbe_ev"])
    spray_available = (agg.get("spray_total") or 0) > 0
    metrics = {
        "bbe": n_ip,
        "gb_pct": ratio(agg["gb"], n_ip, digits=BATTED_BALL_RATE_DIGITS),
        "ld_pct": ratio(agg["ld"], n_ip, digits=BATTED_BALL_RATE_DIGITS),
        "fb_pct": ratio(agg["fb"], n_ip, digits=BATTED_BALL_RATE_DIGITS),
        "pu_pct": ratio(agg["pu"], n_ip, digits=BATTED_BALL_RATE_DIGITS),
        "air_pct": ratio(
            agg["ld"] + agg["fb"], n_ip, digits=BATTED_BALL_RATE_DIGITS
        ),
        "pull_pct": None,
        "straight_pct": None,
        "oppo_pct": None,
        "pull_air_pct": None,
        "barrel_pct": ratio(agg["barrels"], n_ip),
        "hard_hit_pct": ratio(agg["hard_hits"], n_ev),
        "avg_ev": compute_avg_ev(agg["bbe_ev"]),
    }
    if spray_available:
        metrics.update({
            "pull_pct": ratio(agg["pull"], n_ip, digits=BATTED_BALL_RATE_DIGITS),
            "straight_pct": ratio(agg["straight"], n_ip, digits=BATTED_BALL_RATE_DIGITS),
            "oppo_pct": ratio(agg["oppo"], n_ip, digits=BATTED_BALL_RATE_DIGITS),
            "pull_air_pct": ratio(agg["pull_air"], n_ip, digits=BATTED_BALL_RATE_DIGITS),
        })
    return metrics

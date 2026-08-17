"""Batted-ball quality metrics from pitch-level data — one stat per file.

Modules hold each stat's *definition* (barrel window, hard-hit threshold,
sweet-spot band, spray-angle formula); the rate assembly below reads the
counts produced by ``stats.core.pitches.aggregate_pitches``.
"""

from ...constants import BATTED_BALL_RATE_DIGITS
from ...util.numbers import ratio
from .barrel import compute_barrel_pct
from .exit_velocity import compute_avg_ev
from .hard_hit import compute_hard_hit_pct


def batted_ball_metrics(agg: dict) -> dict:
    """Build the batted-ball metrics dict from aggregate_pitches output.

    Each rate's denominator is the count of balls that actually got a
    classification for *that* axis, not every ball in play -- a ball with a
    missing/unrecognized ``trajectory`` (common in MiLB) contributes to none
    of gb/ld/fb/pu, and a ball with no usable hit coordinates or hitData
    location contributes to none of pull/straight/oppo/pull_air. Using
    ``n_ip`` as the denominator for either group would silently dilute every
    rate in that group by the fraction of unclassified balls.
    """
    n_ip = len(agg["in_play"])
    trajectory_classified = agg["gb"] + agg["ld"] + agg["fb"] + agg["pu"]
    spray_total = agg.get("spray_total") or 0
    metrics = {
        "bbe": n_ip,
        "gb_pct": ratio(agg["gb"], trajectory_classified, digits=BATTED_BALL_RATE_DIGITS),
        "ld_pct": ratio(agg["ld"], trajectory_classified, digits=BATTED_BALL_RATE_DIGITS),
        "fb_pct": ratio(agg["fb"], trajectory_classified, digits=BATTED_BALL_RATE_DIGITS),
        "pu_pct": ratio(agg["pu"], trajectory_classified, digits=BATTED_BALL_RATE_DIGITS),
        "air_pct": ratio(
            agg["ld"] + agg["fb"], trajectory_classified, digits=BATTED_BALL_RATE_DIGITS
        ),
        "pull_pct": None,
        "straight_pct": None,
        "oppo_pct": None,
        "pull_air_pct": None,
        "barrel_pct": compute_barrel_pct(agg),
        "hard_hit_pct": compute_hard_hit_pct(agg),
        "avg_ev": compute_avg_ev(agg["bbe_ev"]),
    }
    if spray_total > 0:
        metrics.update({
            "pull_pct": ratio(agg["pull"], spray_total, digits=BATTED_BALL_RATE_DIGITS),
            "straight_pct": ratio(agg["straight"], spray_total, digits=BATTED_BALL_RATE_DIGITS),
            "oppo_pct": ratio(agg["oppo"], spray_total, digits=BATTED_BALL_RATE_DIGITS),
            "pull_air_pct": ratio(agg["pull_air"], spray_total, digits=BATTED_BALL_RATE_DIGITS),
        })
    return metrics

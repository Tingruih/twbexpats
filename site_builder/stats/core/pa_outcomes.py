"""Unified plate-appearance outcome accounting.

Single source for which PA-final events count toward the wOBA / AVG
denominators. Every consumer (season wOBA, per-pitch-type outcome tables,
batter vs-pitch-type tables) must go through this module so the exclusion
rules — intentional walks, sacrifice bunts, and non-PA baserunning events —
never drift apart again.
"""

from ...constants import NON_PA_EVENTS, WOBA_EVENT_MAP, WOBA_WEIGHTS

# AB = PA - BB - HBP - SF - SH (official-rule at-bat exclusions).
_NON_AB_EVENTS = ("walk", "hit_by_pitch", "sac_fly", "sac_bunt", "intent_walk")

_HIT_EVENTS = ("single", "double", "triple", "home_run")


def compute_pa_outcome_totals(pa_final: list[dict]) -> dict:
    """Tally wOBA numerator/denominator plus hits and at-bats from PA-final pitches.

    Excludes intentional walks, sacrifice bunts, and non-PA baserunning
    events (caught stealing, pickoffs) from the denominator.

    Returns ``{"woba_num", "woba_den", "hits", "ab"}``.
    """
    woba_num = 0.0
    woba_den = 0
    hits = 0
    ab = 0
    for p in pa_final:
        ev = p.get("pa_event", "")
        if ev in NON_PA_EVENTS:
            continue
        if ev in ("intent_walk", "sac_bunt"):
            continue
        woba_den += 1
        key = WOBA_EVENT_MAP.get(ev)
        if key:
            woba_num += WOBA_WEIGHTS[key]
        if ev not in _NON_AB_EVENTS:
            ab += 1
            if ev in _HIT_EVENTS:
                hits += 1
    return {"woba_num": woba_num, "woba_den": woba_den, "hits": hits, "ab": ab}

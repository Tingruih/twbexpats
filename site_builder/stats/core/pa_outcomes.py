"""Unified plate-appearance outcome accounting.

Single source for which PA-final events count toward the wOBA / AVG
denominators. Every consumer (season wOBA, per-pitch-type outcome tables,
batter vs-pitch-type tables) must go through this module so the exclusion
rules — intentional walks, sacrifice bunts, catcher interference, and unfinished
PAs — never drift apart again.

The ``*_double_play`` sacrifice variants follow their base sacrifice: the API
only emits them when the official scorer already credited the sacrifice
(Rule 9.08); a failed sacrifice (lead runner retired, 9.08(c)) arrives as
``fielders_choice_out`` / ``double_play`` etc. and is charged an AB like any
other out. Verified against official box scores (atBats / sacFlies / sacBunts).
"""

from ...constants import (
    HIT_EVENTS,
    NON_PA_EVENTS,
    SAC_BUNT_EVENTS,
    SAC_FLY_EVENTS,
    WOBA_EVENT_MAP,
    WOBA_WEIGHTS,
)

# Excluded from both the wOBA denominator and AB, matching FanGraphs/TJStats
# denominator AB + BB - IBB + SF + HBP: IBB, SH, and catcher interference
# (Rule 9.02(a)(1)(D) — no AB when awarded first on interference).
_EXCLUDED_EVENTS = frozenset({"intent_walk", "catcher_interf"}) | SAC_BUNT_EVENTS

# Still in the wOBA denominator but not an AB (Rule 9.02(a)(1): BB, HBP, SF).
_NON_AB_EVENTS = frozenset({"walk", "hit_by_pitch"}) | SAC_FLY_EVENTS


def compute_pa_outcome_totals(pa_final: list[dict]) -> dict:
    """Tally wOBA numerator/denominator plus hits and at-bats from PA-final pitches.

    Excludes intentional walks, sacrifice bunts, catcher interference, and
    unfinished PAs (runner play or called game ended it mid-count; see
    ``constants.NON_PA_EVENTS``) from the denominator.

    Returns ``{"woba_num", "woba_den", "hits", "ab"}``.
    """
    woba_num = 0.0
    woba_den = 0
    hits = 0
    ab = 0
    for p in pa_final:
        ev = p.get("pa_event", "")
        # Empty eventType: the play never completed (game called mid-PA), so
        # there is no PA to count — the box score charges none either.
        if not ev or ev in NON_PA_EVENTS:
            continue
        if ev in _EXCLUDED_EVENTS:
            continue
        woba_den += 1
        key = WOBA_EVENT_MAP.get(ev)
        if key:
            woba_num += WOBA_WEIGHTS[key]
        if ev not in _NON_AB_EVENTS:
            ab += 1
            if ev in HIT_EVENTS:
                hits += 1
    return {"woba_num": woba_num, "woba_den": woba_den, "hits": hits, "ab": ab}

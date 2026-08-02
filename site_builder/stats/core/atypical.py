"""Batter-side "atypical situation" pitch-exclusion framework.

Some pitches don't represent a normal batter-vs-pitcher read/react decision
— a bunt attempt, a position player mopping up on the mound — and pollute
the vs-pitch-type breakdown tables if left in. This module is the single,
extensible place that classification lives: table functions declare which
`Reason`s they want excluded via `exclude_atypical`; this module owns ALL
the matching logic. Table functions never see match logic — they only pass
a set of `Reason` members.

── How to add a new exclusion reason ──────────────────────────────────────

Concrete worked example, so this isn't abstract: say the position-player-
pitching design in
`docs/superpowers/specs/2026-08-01-position-player-pitching-approach-comparison.md`
ships later as a `pitcher_season_profile` table keyed by
`(player_id, season)`, and the caller can look up "is this pitcher a real
pitcher this season" before calling into this module. Adding it is four
small, local edits — no existing Reason, table function, or test changes:

1. Add a member to `Reason`:

       class Reason(StrEnum):
           BUNT_PA = auto()
           BUNT_PITCH = auto()
           POSITION_PLAYER_PITCHING = auto()   # <- new

2. Declare its granularity in `REASON_GRANULARITY` — position-player
   pitching taints the whole plate appearance, not just one pitch:

       REASON_GRANULARITY = {
           Reason.BUNT_PA: Granularity.PA,
           Reason.BUNT_PITCH: Granularity.PITCH,
           Reason.POSITION_PLAYER_PITCHING: Granularity.PA,   # <- new
       }

   `TestReasonGranularityCompleteness` in tests/test_atypical.py fails
   immediately if this step is skipped — it asserts
   `set(REASON_GRANULARITY) == set(Reason)`, so a forgotten entry breaks
   the build instead of silently mis-classifying pitches later.

3. Add a branch to `_matches`. If the profile lookup is cheap and pure, it
   can read a field set by step 4 directly, same shape as the existing
   two branches:

       def _matches(p, reason):
           if reason == Reason.BUNT_PA:
               return bool(p.get("_bunt_pa"))
           if reason == Reason.BUNT_PITCH:
               return p.get("result_code", "") in BUNT_SWING_CODES
           if reason == Reason.POSITION_PLAYER_PITCHING:        # <- new
               return bool(p.get("_position_player_pitching"))
           raise ValueError(f"unhandled atypical reason: {reason!r}")

4. Only needed when the reason requires cross-pitch context (a PA
   boundary, an outing aggregate, a lookup keyed by something other than
   the single pitch dict) — add a pass inside `annotate_atypical`,
   following the same shape as `_flush_bunt_pa` below: compute the fact
   once per group, then stamp it onto every pitch in that group so
   `_matches` (step 3) can stay a flat per-pitch check. If step 2 declared
   `Granularity.PA`, this step is NOT optional — skipping it produces a
   reason that silently behaves as pitch-granularity instead of the
   PA-granularity you declared.

       def annotate_atypical(pitches, *, pitcher_profiles=None):
           if not pitches:
               return
           _annotate_bunt_pa(pitches)                        # existing
           if pitcher_profiles is not None:
               _annotate_position_player_pitching(            # <- new
                   pitches, pitcher_profiles
               )

   `_annotate_position_player_pitching` would set
   `p["_position_player_pitching"]` per pitch, grouping by `pitcher_id` +
   season instead of PA boundaries — new grouping key, same pattern as
   `_flush_bunt_pa`. `annotate_atypical`'s own docstring below documents
   the two ordering rules every such pass must keep obeying.

Finally, the table that wants the new reason opts in where it already
declares its reason set — e.g. in `stats/tables/vs_pitch_types.py`:

    _ATYPICAL_REASONS = {
        Reason.BUNT_PA, Reason.BUNT_PITCH, Reason.POSITION_PLAYER_PITCHING,
    }

`compute_pitch_group_usage_by_count` would very likely NOT add the new
reason to its own set — it never calls `exclude_atypical` at all today;
see the `_ATYPICAL_REASONS` comment in `stats/tables/vs_pitch_types.py`
for why it opts out of the two existing bunt reasons — that inclusion
decision is made per-table, at the declaration site, never inside this
module.
"""

from enum import StrEnum, auto
from typing import Collection

from ...constants import BUNT_SWING_CODES, BUNT_TRAJECTORIES


class Granularity(StrEnum):
    """How much of a plate appearance a matched reason removes.

    Every `Reason` must appear as a key in `REASON_GRANULARITY` below —
    this is what a new reason declares in step 2 of the module docstring's
    "how to add a new exclusion reason" walkthrough.

    This is declarative documentation, not an enforcement mechanism:
    `exclude_atypical` never reads `REASON_GRANULARITY` at filter time. A
    `PA` declaration only becomes true if the reason's `annotate_atypical`
    pass actually stamps its flag onto every pitch in the PA (the way
    `_flush_bunt_pa` does for `BUNT_PA`) — declaring `Granularity.PA`
    without writing that pass silently gives you pitch-level removal
    instead of the PA-level removal you declared.
    """

    PA = auto()     # every pitch in the plate appearance
    PITCH = auto()  # just the one matched pitch


class Reason(StrEnum):
    """One member per exclusion reason. Add new members here (step 1 of
    the module docstring's walkthrough) — nothing else in this file
    changes shape when a member is added, only the two dicts/functions
    below grow a branch each."""

    BUNT_PA = auto()
    BUNT_PITCH = auto()


# Declarative only — see Granularity's docstring: nothing here enforces
# that a PA-granularity reason's annotate pass actually marks every pitch
# in the PA. That correctness lives in the annotate pass itself.
REASON_GRANULARITY: dict[Reason, Granularity] = {
    Reason.BUNT_PA: Granularity.PA,
    Reason.BUNT_PITCH: Granularity.PITCH,
}


def _flush_bunt_pa(group: list[dict]) -> None:
    if not group:
        return
    last = group[-1]
    is_bunt_pa = bool(last.get("is_pa_final")) and (
        last.get("pa_event") == "sac_bunt"
        or last.get("trajectory") in BUNT_TRAJECTORIES
    )
    for p in group:
        p["_bunt_pa"] = is_bunt_pa


def annotate_atypical(pitches: list[dict]) -> None:
    """Pre-pass computing cross-pitch context atypical reasons need.

    Must run over the complete, unsplit pitch list for one player — after
    `core.pitches.ensure_pre_strikes` (order between the two doesn't
    matter, but both must run before any filtering removes pitches), and
    before `tables.splits.compute_pitch_splits` divides the list by
    pitch_hand. Idempotent: safe to call more than once, always
    recomputes.

    Currently runs one grouping pass, `_flush_bunt_pa`, which computes
    PA-level bunt-attempt membership (`Reason.BUNT_PA`) by grouping
    pitches into PAs the same way `ensure_pre_strikes` does: walk in
    order, reset at each `game_pk` boundary, a PA ends at the pitch where
    `is_pa_final` is true. A trailing group with no `is_pa_final` pitch (a
    truncated game log) is left unmarked rather than guessed at.

    Extending this function: a future PA-granularity reason that needs
    its own cross-pitch context (see the module docstring's step 4, e.g.
    grouping by pitcher outing instead of PA) adds a sibling pass here,
    called the same way `_flush_bunt_pa`-driven grouping is called below
    — each pass owns one `_<reason>` field it stamps onto every pitch in
    its group, and passes never need to know about each other.
    """
    if not pitches:
        return

    group: list[dict] = []
    last_game_pk = object()  # sentinel, never equals a real game_pk
    for p in pitches:
        gpk = p.get("game_pk")
        if gpk != last_game_pk:
            _flush_bunt_pa(group)
            group = []
            last_game_pk = gpk
        group.append(p)
        if p.get("is_pa_final"):
            _flush_bunt_pa(group)
            group = []
    _flush_bunt_pa(group)  # trailing partial PA, if any


def _matches(p: dict, reason: Reason) -> bool:
    """One branch per `Reason` member — the module docstring's step 3.
    Every branch is a flat, cheap check on a single pitch dict; any
    cross-pitch work a reason needs must already have happened in
    `annotate_atypical` and be readable off `p` here (see BUNT_PA reading
    `_bunt_pa`, the field `_flush_bunt_pa` stamps on)."""
    if reason == Reason.BUNT_PA:
        return bool(p.get("_bunt_pa"))
    if reason == Reason.BUNT_PITCH:
        return p.get("result_code", "") in BUNT_SWING_CODES
    raise ValueError(f"unhandled atypical reason: {reason!r}")


def exclude_atypical(pitches: list[dict], reasons: Collection[Reason]) -> list[dict]:
    """Drop pitches matching any of `reasons`. This is the only function
    table modules call directly — they pass in whichever `Reason` members
    they've opted into (module docstring's final step) and never touch
    `_matches` or the annotate passes themselves.

    PA-granularity reasons (see `REASON_GRANULARITY`) rely on
    `annotate_atypical` having already run over the full pitch list for
    this player — pitches without the annotation are treated as
    "not excluded", never as an error.
    """
    if not reasons:
        return pitches
    return [p for p in pitches if not any(_matches(p, r) for r in reasons)]

# 短打排除框架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement bunt-attempt exclusion for the batter vs-pitch-type tables (`vs_pitch_types`, `vs_pitch_groups`, and their pitch-hand splits), built as a small, explicitly extensible framework so a future exclusion reason (e.g. position-player-pitching, once `2026-08-01-position-player-pitching-approach-comparison.md` is decided) can be added without redesigning the call sites.

**Architecture:** New module `site_builder/stats/core/atypical.py` owns a `Reason` enum, a `Granularity` enum (`PA` vs `PITCH`), and two entry points: `annotate_atypical(pitches)` (a pre-pass that computes cross-pitch context — currently just PA-level bunt membership — and must run once over the full, unsplit pitch list) and `exclude_atypical(pitches, reasons)` (a pure filter that drops pitches matching any requested `Reason`). Table functions declare which reasons they want via a module-level constant and call `exclude_atypical`; nothing about bunt-specific logic leaks into the table layer. This mirrors the three-layer separation from `2026-07-31-vs-pitch-types-atypical-exclusion-design.md` §2 (extract → classify → declare), minus the extract-layer change, since every field bunt classification needs (`result_code`, `trajectory`, `pa_event`, `is_pa_final`) already exists in `pitches_json`.

**Tech Stack:** Python 3.12, pytest (tests use `unittest.TestCase`, matching `tests/test_fip.py` and `tests/test_helpers.py`).

## Global Constraints

- Only these three tables (and their pitch-hand splits) are in scope: `compute_vs_pitch_types`, `compute_vs_pitch_groups`, `compute_batter_pitch_hand_splits`. `compute_pitch_group_usage_by_count` must **not** exclude bunts (design doc §5: pitch selection happens before the batter shows bunt intent). Pitcher-side tables and `season_stats`/`compute_batter_statcast`'s overall summary are untouched.
- No new API calls, no new database columns, no new cached fields on disk — every field this needs is already in `pitches_json` (`result_code`, `trajectory`, `pa_event`, `is_pa_final`, `game_pk`).
- Filtering must happen **after** `core.pitches.ensure_pre_strikes()` has run over the full pitch list (design doc §6, hard ordering rule #1) — removing pitches first corrupts the chronological pre-count walk for every pitch after the removed one.
- The annotate pass must run over the full, unsplit pitch list **before** `tables.splits.compute_pitch_splits` divides it by `pitch_hand` (design doc §6, hard ordering rule #2).
- `Reason` is a `StrEnum` with `auto()` values, matching the existing `RefreshPolicy(Enum)` convention in `site_builder/league_constant/policy.py`.
- Only the batter-side entry point (`site_builder/stats/batter_statcast.py`) currently calls the three affected table functions — confirmed via repo-wide grep, no other caller to update.

---

## Task 1: `stats/core/atypical.py` — the exclusion framework

**Files:**
- Modify: `site_builder/constants.py` (add two constants near the existing `SWING_CODES` / `*_TRAJECTORIES` blocks)
- Create: `site_builder/stats/core/atypical.py`
- Test: `tests/test_atypical.py`

**Interfaces:**
- Produces: `Reason` (`StrEnum`, members `BUNT_PA`, `BUNT_PITCH`), `Granularity` (`StrEnum`, members `PA`, `PITCH`), `REASON_GRANULARITY: dict[Reason, Granularity]`, `annotate_atypical(pitches: list[dict]) -> None` (mutates in place), `exclude_atypical(pitches: list[dict], reasons: Collection[Reason]) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_atypical.py`:

```python
"""Tests for site_builder.stats.core.atypical"""

import unittest

from site_builder.stats.core.atypical import (
    Granularity,
    REASON_GRANULARITY,
    Reason,
    annotate_atypical,
    exclude_atypical,
)


def _pitch(game_pk=1, is_pa_final=False, pa_event="", trajectory="", result_code="B"):
    return {
        "game_pk": game_pk,
        "is_pa_final": is_pa_final,
        "pa_event": pa_event,
        "trajectory": trajectory,
        "result_code": result_code,
    }


class TestReasonGranularityCompleteness(unittest.TestCase):
    def test_every_reason_has_a_declared_granularity(self):
        # Guards future additions: forgetting to declare a new Reason's
        # granularity in REASON_GRANULARITY fails this test immediately.
        self.assertEqual(set(REASON_GRANULARITY), set(Reason))
        self.assertEqual(REASON_GRANULARITY[Reason.BUNT_PA], Granularity.PA)
        self.assertEqual(REASON_GRANULARITY[Reason.BUNT_PITCH], Granularity.PITCH)


class TestAnnotateAtypicalBuntPa(unittest.TestCase):
    def test_marks_every_pitch_in_a_pa_ending_in_sac_bunt(self):
        take = _pitch(result_code="C")
        final = _pitch(is_pa_final=True, pa_event="sac_bunt", result_code="D")
        pitches = [take, final]

        annotate_atypical(pitches)

        self.assertTrue(take["_bunt_pa"])
        self.assertTrue(final["_bunt_pa"])

    def test_marks_every_pitch_in_a_pa_ending_in_bunt_trajectory(self):
        foul_bunt = _pitch(result_code="L")
        final = _pitch(is_pa_final=True, trajectory="bunt_grounder", result_code="X")
        pitches = [foul_bunt, final]

        annotate_atypical(pitches)

        self.assertTrue(foul_bunt["_bunt_pa"])
        self.assertTrue(final["_bunt_pa"])

    def test_does_not_mark_a_pa_that_ends_in_a_non_bunt_result(self):
        # Mid-PA bunt foul, batter later swings away for a real hit — the
        # known "take bunt" style limitation this framework doesn't solve.
        foul_bunt_attempt = _pitch(result_code="L")
        final = _pitch(is_pa_final=True, pa_event="single", trajectory="line_drive", result_code="X")
        pitches = [foul_bunt_attempt, final]

        annotate_atypical(pitches)

        self.assertFalse(foul_bunt_attempt["_bunt_pa"])
        self.assertFalse(final["_bunt_pa"])

    def test_resets_pa_grouping_at_game_boundary(self):
        game1_final = _pitch(game_pk=1, is_pa_final=True, pa_event="sac_bunt", result_code="D")
        game2_take = _pitch(game_pk=2, result_code="B")
        game2_final = _pitch(game_pk=2, is_pa_final=True, pa_event="single", result_code="X")
        pitches = [game1_final, game2_take, game2_final]

        annotate_atypical(pitches)

        self.assertTrue(game1_final["_bunt_pa"])
        self.assertFalse(game2_take["_bunt_pa"])
        self.assertFalse(game2_final["_bunt_pa"])

    def test_trailing_incomplete_pa_is_not_marked(self):
        # No is_pa_final pitch at all for this PA. Must default to
        # "not excluded" and never crash.
        pitches = [_pitch(result_code="C"), _pitch(result_code="L")]

        annotate_atypical(pitches)

        self.assertFalse(pitches[0]["_bunt_pa"])
        self.assertFalse(pitches[1]["_bunt_pa"])

    def test_idempotent(self):
        pitches = [_pitch(is_pa_final=True, pa_event="sac_bunt", result_code="D")]

        annotate_atypical(pitches)
        annotate_atypical(pitches)

        self.assertTrue(pitches[0]["_bunt_pa"])

    def test_empty_list_is_a_noop(self):
        annotate_atypical([])  # must not raise


class TestExcludeAtypical(unittest.TestCase):
    def test_no_reasons_returns_the_same_list(self):
        pitches = [_pitch()]
        self.assertIs(exclude_atypical(pitches, set()), pitches)

    def test_bunt_pa_removes_every_pitch_in_the_marked_pa(self):
        p1 = _pitch(result_code="C")
        p2 = _pitch(is_pa_final=True, pa_event="sac_bunt", result_code="D")
        pitches = [p1, p2]
        annotate_atypical(pitches)

        result = exclude_atypical(pitches, {Reason.BUNT_PA})

        self.assertEqual(result, [])

    def test_bunt_pitch_removes_only_the_matched_pitch(self):
        foul_bunt = _pitch(result_code="L")
        ball = _pitch(result_code="B")
        final = _pitch(is_pa_final=True, pa_event="strikeout", result_code="S")
        pitches = [foul_bunt, ball, final]
        annotate_atypical(pitches)  # PA doesn't end in bunt -> _bunt_pa all False

        result = exclude_atypical(pitches, {Reason.BUNT_PITCH})

        self.assertEqual(result, [ball, final])

    def test_bunt_pa_and_bunt_pitch_combine_without_duplication(self):
        take = _pitch(result_code="C")
        foul_bunt = _pitch(result_code="L")
        final = _pitch(is_pa_final=True, pa_event="sac_bunt", result_code="D")
        pitches = [take, foul_bunt, final]
        annotate_atypical(pitches)

        result = exclude_atypical(pitches, {Reason.BUNT_PA, Reason.BUNT_PITCH})

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_atypical.py -v`
Expected: collection error / `ModuleNotFoundError: No module named 'site_builder.stats.core.atypical'`

- [ ] **Step 3: Add the bunt constants**

In `site_builder/constants.py`, right after the `CALLED_STRIKE_CODES` line (around line 120):

```python
CALLED_STRIKE_CODES = {"C"}  # Strike - Called (excludes automatic strikes: A/AB/AC/K)

# Bunt-attempt subset of SWING_CODES — used by stats.core.atypical to flag
# individual pitches for BUNT_PITCH exclusion regardless of PA outcome.
BUNT_SWING_CODES = {"M", "L", "O"}
```

And right after the `PU_TRAJECTORIES` line (around line 490):

```python
PU_TRAJECTORIES = {"popup", "bunt_popup"}

# Bunt-attempt subset of {GB,LD,PU}_TRAJECTORIES — a PA whose final in-play
# ball lands in one of these is a completed bunt attempt
# (stats.core.atypical Reason.BUNT_PA).
BUNT_TRAJECTORIES = {"bunt_grounder", "bunt_line_drive", "bunt_popup"}
AIR_TRAJECTORIES = LD_TRAJECTORIES | FB_TRAJECTORIES
```

(Keep `AIR_TRAJECTORIES` where it already is relative to the other trajectory sets — just insert `BUNT_TRAJECTORIES` before it.)

- [ ] **Step 4: Write `site_builder/stats/core/atypical.py`**

```python
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
   `_matches` (step 3) can stay a flat per-pitch check.

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
reason to its own set, the same way it already opts out of both bunt
reasons today (see that module's docstring for why) — that inclusion
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_atypical.py -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add site_builder/constants.py site_builder/stats/core/atypical.py tests/test_atypical.py
git commit -m "feat: add extensible atypical-pitch exclusion framework with bunt reasons"
```

---

## Task 2: Wire bunt exclusion into the vs-pitch-type tables

**Files:**
- Modify: `site_builder/stats/tables/vs_pitch_types.py`
- Modify: `site_builder/stats/batter_statcast.py`
- Test: `tests/test_vs_pitch_types.py`

**Interfaces:**
- Consumes (from Task 1): `Reason.BUNT_PA`, `Reason.BUNT_PITCH`, `annotate_atypical(pitches)`, `exclude_atypical(pitches, reasons)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_vs_pitch_types.py`:

```python
"""Tests for the bunt-exclusion wiring in site_builder.stats.tables.vs_pitch_types"""

import unittest

from site_builder.stats.core.atypical import annotate_atypical
from site_builder.stats.core.pitches import ensure_pre_strikes
from site_builder.stats.tables.usage_by_count import compute_pitch_group_usage_by_count
from site_builder.stats.tables.vs_pitch_types import (
    compute_batter_pitch_hand_splits,
    compute_vs_pitch_groups,
    compute_vs_pitch_types,
)


def _pitch(**overrides):
    base = {
        "game_pk": 1,
        "pitch_type": "FF",
        "pitch_name": "Four-Seam Fastball",
        "result_code": "C",
        "is_strike": True,
        "is_in_play": False,
        "zone": 5,
        "is_pa_final": False,
        "pa_event": "",
        "pa_event_desc": "",
        "trajectory": "",
        "ev": None,
        "la": None,
        "balls": 0,
        "strikes": 0,
        "pitch_hand": "R",
    }
    base.update(overrides)
    return base


class TestVsPitchTypesExcludesBunts(unittest.TestCase):
    def test_excludes_every_pitch_of_a_completed_bunt_pa(self):
        take = _pitch(result_code="C")
        sac_bunt_final = _pitch(
            result_code="D", is_in_play=True, is_pa_final=True,
            pa_event="sac_bunt", trajectory="bunt_grounder",
        )
        normal_final = _pitch(
            pitch_type="SL", pitch_name="Slider", result_code="X",
            is_in_play=True, is_pa_final=True, pa_event="single",
        )
        pitches = [take, sac_bunt_final, normal_final]
        annotate_atypical(pitches)

        rows = compute_vs_pitch_types(pitches)

        self.assertEqual({r["type"] for r in rows}, {"SL"})
        self.assertEqual(sum(r["count"] for r in rows), 1)

    def test_excludes_mid_pa_bunt_foul_but_keeps_the_rest_of_the_pa(self):
        foul_bunt = _pitch(result_code="L")
        final = _pitch(result_code="X", is_in_play=True, is_pa_final=True, pa_event="strikeout")
        pitches = [foul_bunt, final]
        annotate_atypical(pitches)

        rows = compute_vs_pitch_types(pitches)

        self.assertEqual(sum(r["count"] for r in rows), 1)

    def test_vs_pitch_groups_also_excludes_bunts(self):
        sac_bunt_final = _pitch(
            result_code="D", is_in_play=True, is_pa_final=True,
            pa_event="sac_bunt", trajectory="bunt_grounder",
        )
        pitches = [sac_bunt_final]
        annotate_atypical(pitches)

        rows = compute_vs_pitch_groups(pitches)

        self.assertEqual(rows, [])

    def test_usage_by_count_is_not_affected_by_bunts(self):
        # Explicit non-goal (design doc §5): pitch selection happens before
        # the batter shows bunt intent, so usage_by_count must not drop
        # these pitches.
        sac_bunt_final = _pitch(
            result_code="D", is_in_play=True, is_pa_final=True,
            pa_event="sac_bunt", trajectory="bunt_grounder",
        )
        pitches = [sac_bunt_final]
        annotate_atypical(pitches)

        result = compute_pitch_group_usage_by_count(pitches)

        self.assertEqual(sum(pt["count"] for pt in result["pitch_types"]), 1)

    def test_batter_pitch_hand_splits_inherit_bunt_exclusion(self):
        sac_bunt_final = _pitch(
            result_code="D", is_in_play=True, is_pa_final=True,
            pa_event="sac_bunt", trajectory="bunt_grounder", pitch_hand="R",
        )
        pitches = [sac_bunt_final]
        annotate_atypical(pitches)

        splits = compute_batter_pitch_hand_splits(pitches)

        self.assertEqual(splits["all"]["vs_pitch_types"], [])
        self.assertEqual(splits["R"]["vs_pitch_types"], [])


class TestOrderingAgainstEnsurePreStrikes(unittest.TestCase):
    def test_pre_strikes_backfill_survives_a_later_bunt_exclusion(self):
        # Regression guard for design doc §6 hard ordering rule #1: if a
        # BUNT_PITCH pitch were removed *before* ensure_pre_strikes walks
        # the list, every later pitch in the same PA would inherit the
        # wrong pre-pitch count. Here pitch2 (a foul-bunt attempt, later
        # excluded) sits between pitch1 and pitch3 in the count sequence
        # 0-0 -> 0-1 -> 0-2 -> (final). pitch3 must see pre_strikes == 2,
        # which only happens if pitch2 was still present during the walk.
        pitch1 = _pitch(result_code="C", balls=0, strikes=1)
        pitch2 = _pitch(result_code="L", balls=0, strikes=2)
        pitch3 = _pitch(
            pitch_type="SL", pitch_name="Slider", result_code="X",
            is_in_play=True, is_pa_final=True, pa_event="field_out",
            balls=0, strikes=2,
        )
        pitches = [pitch1, pitch2, pitch3]

        ensure_pre_strikes(pitches)
        annotate_atypical(pitches)

        self.assertEqual(pitch3["pre_strikes"], 2)

        rows = compute_vs_pitch_types(pitches)

        ff_row = next(r for r in rows if r["type"] == "FF")
        self.assertEqual(ff_row["count"], 1)  # only pitch1 survives
        sl_row = next(r for r in rows if r["type"] == "SL")
        self.assertEqual(sl_row["two_strike_count"], 1)  # pitch3, pre_strikes == 2


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_vs_pitch_types.py -v`
Expected: FAIL — `compute_vs_pitch_types` still includes bunt pitches (counts off by the bunt pitches; `test_usage_by_count_is_not_affected_by_bunts` passes already since that table isn't touched, the others fail).

- [ ] **Step 3: Wire `exclude_atypical` into the table functions**

In `site_builder/stats/tables/vs_pitch_types.py`, add the import and a module-level reason set, then apply it in both breakdown functions:

```python
from ...constants import (
    PITCH_HAND_SPLITS,
    PITCH_TYPE_GROUPS,
    PITCH_TYPE_TO_GROUP,
)
from ..advanced.woba import compute_pitch_woba
from ..batted_ball.barrel import compute_barrel_pct
from ..batted_ball.hard_hit import compute_hard_hit_pct
from ..batting.avg import compute_avg
from ..core.atypical import Reason, exclude_atypical
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


# Reasons excluded from the per-pitch-type / per-pitch-group breakdowns.
# compute_pitch_group_usage_by_count deliberately does NOT use this set —
# see its own module for why.
#
# To exclude a future atypical.Reason from these two tables too (e.g. if
# Reason.POSITION_PLAYER_PITCHING ships later — see the extension
# walkthrough in core/atypical.py's module docstring), just add it here;
# neither compute_vs_pitch_types nor compute_vs_pitch_groups needs to
# change, since both already call exclude_atypical(pitches, _ATYPICAL_REASONS).
_ATYPICAL_REASONS = {Reason.BUNT_PA, Reason.BUNT_PITCH}
```

Then update `compute_vs_pitch_types` and `compute_vs_pitch_groups`:

```python
def compute_vs_pitch_types(pitches: list[dict]) -> list[dict]:
    """Per-pitch-type breakdown for a batter."""
    pitches = filter_known_pitch_events(pitches)
    pitches = exclude_atypical(pitches, _ATYPICAL_REASONS)

    by_type: dict[str, list[dict]] = {}
    for p in pitches:
        t = p.get("pitch_type") or "UN"
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
    pitches = exclude_atypical(pitches, _ATYPICAL_REASONS)

    by_group: dict[str, list[dict]] = {}
    for p in pitches:
        t = p.get("pitch_type") or "UN"
        group = PITCH_TYPE_TO_GROUP.get(t)
        if group is None:
            continue
        by_group.setdefault(group, []).append(p)

    return [
        _compute_pitch_bucket_row(key, label, by_group[key])
        for key, label, _codes in PITCH_TYPE_GROUPS
        if by_group.get(key)
    ]
```

`compute_batter_pitch_hand_splits` and `_compute_pitch_bucket_row` are unchanged — the split builder calls `compute_vs_pitch_types` / `compute_vs_pitch_groups` per hand bucket, so they inherit the exclusion automatically.

- [ ] **Step 4: Call `annotate_atypical` in the batter Statcast entry point**

In `site_builder/stats/batter_statcast.py`, add the import and call it right after `ensure_pre_strikes`:

```python
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
    ...
```

(Only the two new lines and the accompanying import change; the rest of the function body is unchanged.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_atypical.py tests/test_vs_pitch_types.py -v`
Expected: all tests PASS

- [ ] **Step 6: Run the full test suite to check for regressions**

The baseline `tests/` directory has 4 pre-existing failures unrelated to
this plan (`tests/test_helpers.py` and `tests/test_sync.py` fail to
collect — `site_builder.helpers` and `site_builder.sync._fetch_player_data`
no longer exist; `tests/test_api.py::TestGetPlayerProfileRosterStatus` has
2 failures from a stale mock target). Do not attempt to fix these — they
predate this plan and are out of scope. Run the suite excluding the two
files that fail to collect, and confirm the failure count doesn't grow
beyond the known 2:

Run: `python3 -m pytest tests/ -v --ignore=tests/test_helpers.py --ignore=tests/test_sync.py`
Expected: 2 failures (both in `TestGetPlayerProfileRosterStatus`, pre-existing), everything else PASSES

- [ ] **Step 7: Commit**

```bash
git add site_builder/stats/tables/vs_pitch_types.py site_builder/stats/batter_statcast.py tests/test_vs_pitch_types.py
git commit -m "feat: exclude bunt attempts from batter vs-pitch-type tables"
```

---

## Self-Review Notes

- **Spec coverage:** design doc §4.3 (bunt rules) → Task 1 `_matches`/`_flush_bunt_pa`; §4.1 (Reason/granularity as first-class, extensible) → Task 1 `Reason`/`Granularity`/`REASON_GRANULARITY`; §4.4 (annotate pass) → Task 1 `annotate_atypical`; §5 (declarative per-table application, `usage_by_count` excluded) → Task 2; §6 (two ordering rules) → Task 2 Step 4 + the ordering regression test. §4.2 (position-player rules) is explicitly out of scope per the user's request and the spec's "尚未拍板" status — `Reason`/`REASON_GRANULARITY` are structured so adding `POSITION_PLAYER_PITCHING` later is a 3-4 line diff, not a redesign.
- **Placeholder scan:** no TBD/TODO markers; every step has real code.
- **Type consistency:** `Reason`, `Granularity`, `annotate_atypical`, `exclude_atypical` signatures are identical between Task 1's production code and Task 2's imports/usage.

---

**Plan complete and saved to `docs/superpowers/plans/2026-08-02-bunt-exclusion-framework.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

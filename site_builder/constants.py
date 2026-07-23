"""
Single source of truth for computation constants, paths, and runtime config.

Layout (keep new constants in the right section):

  1. Paths & runtime config     — project paths, timeouts, worker counts.
  2. ANNUAL CONSTANTS           — values that must be refreshed each spring.
                                  SEASON_YEAR rolls over automatically;
                                  LEAGUE_RA9 needs a manual entry each year
                                  (falls back to the latest year otherwise).
                                  The MiLB FIP constant is no longer manual —
                                  see db.fip_constants_cache.
  3. Stable domain constants    — pitch codes, wOBA weights, chart definitions.
                                  These do not change year to year; every entry
                                  carries a source note.

League *levels* are NOT defined here — that registry lives in
``site_builder.levels`` (see its module docstring).
"""

import datetime
import os
from pathlib import Path
from typing import Optional

# ══════════════════════════════════════════════════════════════════════════
# 1. PATHS & RUNTIME CONFIG
# ══════════════════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
TEMPLATE_DIR = SRC_DIR / "templates"
STATIC_DIR = SRC_DIR / "static"
DEFAULT_ROSTER_FILE = SRC_DIR / "data" / "roster.json"

# MLB Stats API request timeouts (seconds). The live feed payload is an order
# of magnitude larger than every other endpoint, so it gets a longer budget.
API_TIMEOUT = 15
LIVE_FEED_TIMEOUT = 30

# MLB Stats API rate limit (requests/second), enforced process-wide in
# site_builder/api/client.py::get_json regardless of how many threads call it.
API_RATE_LIMIT = 25

# HTTP retry / connection-pool tuning for site_builder/api/client.py. Retries
# (with exponential backoff + jitter, honouring Retry-After) are delegated to
# urllib3's Retry mounted on a per-thread Session's HTTPAdapter; the rate limit
# above stays the primary pacing mechanism and retries are the rare exception.
API_MAX_RETRIES = 3
API_BACKOFF_FACTOR = 0.5
API_POOL_MAXSIZE = 10

# Thread-pool sizes. The two sync pipelines parallelise different units of
# work (players vs. games), so they are tuned independently.
PLAYER_FETCH_WORKERS = 20
GAME_FETCH_WORKERS = 50

# The /content highlight index can lag behind the live feed; retry games with
# zero videos for this many days after game date.
CONTENT_RETRY_DAYS = 14

# ══════════════════════════════════════════════════════════════════════════
# 2. ANNUAL CONSTANTS — refresh each spring
# ══════════════════════════════════════════════════════════════════════════
#
# Season-start checklist (one place, one commit):
#   1. SEASON_YEAR rolls over automatically (see _auto_season_year below) —
#      nothing to bump by hand.
#   2. Add LEAGUE_RA9 entries for the new year.
# get_league_ra9 falls back to the latest available year, so a season
# without a new entry keeps working — just with a stale constant.
#
# FIP_CONSTANTS is no longer a manual table: the MiLB FIP constant is computed
# from real league-wide pitching totals fetched from the MLB Stats API (see
# db.fip_constants_cache / api.league_stats / stats.advanced.fip). Nothing to
# refresh here by hand.


def _auto_season_year() -> int:
    """Current MLB season year, rolling over each March.

    Jan/Feb still belong to the prior season (off-season/spring training for
    the season that already finished); from March onward it's the new one.
    """
    today = datetime.date.today()
    return today.year if today.month >= 3 else today.year - 1


# DEFAULT_SEASON_YEAR env var overrides auto-derivation (manual testing /
# backfilling a specific year); unset in normal operation.
_env_season_year = os.environ.get("DEFAULT_SEASON_YEAR")
SEASON_YEAR = int(_env_season_year) if _env_season_year else _auto_season_year()

# Last-resort FIP constant when db.fip_constants_cache can't resolve one at
# all (fetch failure, unrecognized level, season hasn't started yet).
FIP_DEFAULT_CONSTANT = 3.2

# League RA/9 per (sport_level, year), used in the xWPCT (Pythagenpat) formula.
# Approximate values; refresh manually each spring (source: TJStats/FanGraphs
# guts). Candidate for the same auto-computed treatment as the FIP constant
# (db.fip_constants_cache) — deferred for now.
LEAGUE_RA9 = {
    ("MLB", 2024): 4.40,
    ("AAA", 2024): 5.10,
    ("AA", 2024): 4.80,
    ("A+", 2024): 4.60,
    ("A", 2024): 4.70,
}
LEAGUE_RA9_DEFAULT = 4.5  # last-resort fallback when a level has no entry at all


def _lookup_annual(table: dict, level: str, year: Optional[int]):
    """Shared (level, year) lookup with fall-back to the latest year at *level*.

    Returns ``(value, exact)`` where *exact* is True only for a direct
    (level, year) hit. ``(None, False)`` when the level is entirely unknown.
    """
    if year is not None:
        exact = table.get((level, year))
        if exact is not None:
            return exact, True
    candidates = {yr: v for (lvl, yr), v in table.items() if lvl == level}
    if candidates:
        return candidates[max(candidates)], False
    return None, False


def get_league_ra9(level: str, year: Optional[int] = None) -> tuple[Optional[float], bool]:
    """League RA/9 for *level*/*year*; falls back to the latest year at *level*."""
    return _lookup_annual(LEAGUE_RA9, level, year)


# ══════════════════════════════════════════════════════════════════════════
# 3. STABLE DOMAIN CONSTANTS
# ══════════════════════════════════════════════════════════════════════════

# ── Pitch result-code classifications ──
# Source: MLB Stats API ``details.code`` values, cross-checked against the
# ``/api/v1/pitchCodes`` reference endpoint (swingStatus / swingMissStatus
# fields) so every code with swingStatus=true is represented here.
SWING_CODES = {
    "S",  # Strike - Swinging
    "W",  # Strike - Swinging Blocked
    "F",  # Strike - Foul
    "T",  # Strike - Foul Tip
    "M",  # Strike - Missed Bunt
    "L",  # Strike - Foul Bunt
    "O",  # Strike - Bunt Foul Tip
    "R",  # Strike - Foul on Pitchout
    "Q",  # Strike - Swinging on Pitchout
    "X",  # Hit Into Play - Out(s)
    "D",  # Hit Into Play - No Out(s)
    "E",  # Hit Into Play - Run(s)
    "Y",  # Pitchout Hit Into Play - Out(s)
    "J",  # Pitchout Hit Into Play - No Out(s)
    "Z",  # Pitchout Hit Into Play - Run(s)
}

WHIFF_CODES = {
    "S",  # Strike - Swinging
    "W",  # Strike - Swinging Blocked
    "T",  # Strike - Foul Tip (counts as swinging strike per Statcast)
    "M",  # Strike - Missed Bunt
    "O",  # Strike - Bunt Foul Tip
    "Q",  # Strike - Swinging on Pitchout
}
# The above are exactly the codes with swingMissStatus=true per pitchCodes.

CALLED_STRIKE_CODES = {"C"}  # Strike - Called (excludes automatic strikes: A/AB/AC/K)

# ── wOBA linear weights (TJStats fixed set, shared across all levels and seasons) ──
# Source: https://tjstats.ca/glossary/
# TJStats uses one fixed set of weights and handles run-environment variation
# through per-league constants (lg_wOBA, lg_R/PA) and park factors instead.
WOBA_WEIGHTS: dict[str, float] = {
    "walk": 0.689,
    "hbp": 0.720,
    "single": 0.881,
    "double": 1.254,
    "triple": 1.589,
    "home_run": 2.048,
}

# PA event strings from MLB Stats API ``result.eventType`` that count as wOBA outcomes.
WOBA_EVENT_MAP = {
    "walk": "walk",
    "hit_by_pitch": "hbp",
    "single": "single",
    "double": "double",
    "triple": "triple",
    "home_run": "home_run",
}

# TJStats wRC+ scale converting a wOBA gap back to runs.
# Source: https://tjstats.ca/glossary/
WOBA_SCALE = 1.24

# Seasons before this have no TJStats coverage, so wRC+ is never computed.
MIN_WRC_YEAR = 2021

# site_builder.levels Tier key → (pf_level query value, league-constants Level
# code) on tjstats.ca. The two pages spell the same levels differently
# (hi_a/lo_a vs hi-a/lo-a), hence one table with both spellings.
TJSTATS_LEVEL_PARAMS = {
    "MLB": ("mlb", "mlb"),
    "AAA": ("aaa", "aaa"),
    "AA": ("aa", "aa"),
    "A+": ("hi_a", "hi-a"),
    "A": ("lo_a", "lo-a"),
}
PF_LEVEL_PARAM = {k: v[0] for k, v in TJSTATS_LEVEL_PARAMS.items()}
LC_LEVEL_CODE = {k: v[1] for k, v in TJSTATS_LEVEL_PARAMS.items()}
WRC_LEVELS = tuple(TJSTATS_LEVEL_PARAMS.keys())

# Baserunning play events that occur during a batter's PA but do NOT
# constitute a plate appearance outcome for the batter (e.g. caught stealing,
# pickoff outs).  Pitches ending in these events must be excluded from batter
# wOBA / AB / PA calculations.
NON_PA_EVENTS: frozenset[str] = frozenset({
    "caught_stealing_2b",
    "caught_stealing_3b",
    "caught_stealing_home",
    "pickoff_caught_stealing_2b",
    "pickoff_caught_stealing_3b",
    "pickoff_caught_stealing_home",
    "pickoff_1b",
    "pickoff_2b",
    "pickoff_3b",
    "game_advisory",
    "other_advance",
})

# ── Splits & chart definitions (shared by per-level compute and cross-level combine) ──

BAT_SIDE_SPLITS = (
    ("all", "全部"),
    ("L", "左打"),
    ("R", "右打"),
)

# Ball-strike count buckets used when computing per-level usage tables at sync
# time (labels are stored inside the statcast JSON payload).
COUNT_USAGE_BUCKETS = (
    {
        "key": "early",
        "label": "前段球數",
        "counts_label": "0-0, 0-1, 1-0",
        "counts": {(0, 0), (0, 1), (1, 0)},
    },
    {
        "key": "pitcher_ahead",
        "label": "球數領先",
        "counts_label": "0-1, 0-2, 1-2, 2-2",
        "counts": {(0, 1), (0, 2), (1, 2), (2, 2)},
    },
    {
        "key": "pitcher_behind",
        "label": "球數落後",
        "counts_label": "1-0, 2-0, 3-0, 2-1, 3-1",
        "counts": {(1, 0), (2, 0), (3, 0), (2, 1), (3, 1)},
    },
    {
        "key": "pre_two_strikes",
        "label": "兩好球前",
        "counts_label": "0-0, 0-1, 1-0, 1-1, 2-1, 3-1",
        "counts": {(0, 0), (0, 1), (1, 0), (1, 1), (2, 1), (3, 1)},
    },
    {
        "key": "two_strikes",
        "label": "兩好球後",
        "counts_label": "0-2, 1-2, 2-2, 3-2",
        "counts": {(0, 2), (1, 2), (2, 2), (3, 2)},
    },
)

# Bucket list used by the cross-level *combine* step at build time. Kept as a
# separate table because the historical builder version had an extra "all"
# bucket and English labels; combined rows in the rendered site rely on these
# exact labels. (Candidate for future unification with COUNT_USAGE_BUCKETS.)
COMBINED_COUNT_USAGE_BUCKETS = (
    ("all", "All Counts", "All ball-strike counts"),
    ("early", "Early Count", "0-0, 0-1, 1-0"),
    ("pitcher_ahead", "Pitcher Ahead", "0-1, 0-2, 1-2, 2-2"),
    ("pitcher_behind", "Pitcher Behind", "1-0, 2-0, 3-0, 2-1, 3-1"),
    ("pre_two_strikes", "Pre Two Strikes", "0-0, 0-1, 1-0, 1-1, 2-1, 3-1"),
    ("two_strikes", "Two Strikes", "0-2, 1-2, 2-2, 3-2"),
)

# Pitch Plinko count-transition graph: the 12 legal counts and 17 legal edges.
PLINKO_COUNTS = (
    (0, 0), (0, 1), (1, 0), (0, 2), (1, 1), (2, 0),
    (1, 2), (2, 1), (3, 0), (2, 2), (3, 1), (3, 2),
)
# Same counts in "B-S" label form (the shape stored in the statcast JSON).
PLINKO_COUNT_LABELS = tuple(f"{b}-{s}" for b, s in PLINKO_COUNTS)

PLINKO_EDGES = (
    ("0-0", "0-1"), ("0-0", "1-0"),
    ("0-1", "0-2"), ("0-1", "1-1"),
    ("1-0", "1-1"), ("1-0", "2-0"),
    ("0-2", "1-2"),
    ("1-1", "1-2"), ("1-1", "2-1"),
    ("2-0", "2-1"), ("2-0", "3-0"),
    ("1-2", "2-2"),
    ("2-1", "2-2"), ("2-1", "3-1"),
    ("3-0", "3-1"),
    ("2-2", "3-2"), ("3-1", "3-2"),
)

BATTER_PLINKO_SPLITS = (
    ("L", "vs LHP"),
    ("R", "vs RHP"),
)

PITCHER_PLINKO_SPLITS = (
    ("L", "vs LHB"),
    ("R", "vs RHB"),
)

# EP (Eephus) and FA (generic Fastball) almost exclusively appear in
# position-player-pitching situations; excluded from batter breakdowns to
# match TJStats / Baseball Savant behaviour.
BATTER_PLINKO_SKIP_TYPES = {"EP", "FA"}

# ── Batted-ball trajectory classification ──
# Source: MLB Stats API ``hitData.trajectory`` values.
GB_TRAJECTORIES = {"ground_ball", "bunt_grounder"}
LD_TRAJECTORIES = {"line_drive", "bunt_line_drive"}
FB_TRAJECTORIES = {"fly_ball"}
PU_TRAJECTORIES = {"popup", "bunt_popup"}
AIR_TRAJECTORIES = LD_TRAJECTORIES | FB_TRAJECTORIES

BATTED_BALL_RATE_DIGITS = 6

# ── MLB Gameday hit coordinate origin and spray-angle formula ──
# Source: Jeff & Darrell Zimmerman / Bill Petti, The Hardball Times (2017)
# https://tht.fangraphs.com/research-notebook-new-format-for-statcast-data-export-at-baseball-savant/
# Formula: atan((hc_x - 125.42) / (198.27 - hc_y)) * 180/pi * 0.75
# The 0.75 factor corrects for the perspective distortion of the Gameday spray chart image.
GAMEDAY_HOME_X = 125.42
GAMEDAY_HOME_Y = 198.27
GAMEDAY_SPRAY_CORRECTION = 0.75
GAMEDAY_LEFT_FIELD_THRESHOLD_DEG = 15.0
GAMEDAY_RIGHT_FIELD_THRESHOLD_DEG = 15.0

# MLB Stats API hitData.location → broad field zone (LF / CF / RF).
# Used as fallback when hit coordinates are unavailable.
# '1'=Pitcher, '2'=Catcher, '3'=1B, '4'=2B, '5'=3B, '6'=SS,
# '7'=LF, '78'=LC, '8'=CF, '89'=RC, '9'=RF
HIT_LOCATION_ZONE: dict[str, str] = {
    "1":  "CF",  # pitcher (e.g. comebacker)
    "2":  "CF",  # catcher (bunt)
    "3":  "RF",  # first baseman
    "4":  "CF",  # second baseman (up the middle)
    "5":  "LF",  # third baseman
    "6":  "LF",  # shortstop
    "7":  "LF",  # left fielder
    "78": "LF",  # left-center
    "8":  "CF",  # center fielder
    "89": "RF",  # right-center
    "9":  "RF",  # right fielder
}

# ── Counting stat fields summed in career / season-combined aggregations ──
COUNTING_FIELDS = [
    # ── Shared ──
    "gp",
    # ── Hitting ──
    "pa", "ab", "runs", "hits", "doubles", "triples", "hr", "rbi", "tb",
    "hit_bb", "h_so", "hbp", "ibb", "sb", "cs", "gdp", "lob",
    "sac_bunts", "sac_flies", "h_ground_outs", "h_air_outs", "pitches_seen",
    "gidpo", "roe", "wo", "xbh",
    # ── Pitching ──
    "wins", "losses", "sv", "hld", "so", "bb", "gs", "bf",
    "earned_runs", "pitches", "svo", "outs", "cg", "sho", "strikes",
    "balks", "wp", "pickoffs", "gf", "ir", "irs", "qs",
    "runs_allowed", "p_hits", "p_hr", "p_hbp", "p_ibb",
    "p_sb", "p_cs", "p_gdp", "p_doubles", "p_triples", "p_tb", "p_ab",
    "p_ground_outs", "p_air_outs", "p_sac_bunts", "p_sac_flies",
    # ── Advanced / derived counting ──
    "bqr", "bqr_s", "run_support", "p_gidpo",
]

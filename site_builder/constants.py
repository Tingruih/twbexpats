"""
Single source of truth for computation constants, paths, and runtime config.

Layout (keep new constants in the right section):

  1. Paths & runtime config     — project paths, timeouts, worker counts,
                                  plus SEASON_YEAR (rolls over on its own).
  2. Stable domain constants    — pitch codes, wOBA weights, chart definitions.
                                  These do not change year to year; every entry
                                  carries a source note.

Two kinds of constant are deliberately NOT here:

  - League *levels* live in ``site_builder.levels`` (see its docstring).
  - Per-season, per-league run-environment numbers (FIP constants, league
    ERA, park factors, lg_wOBA / lg_R/PA) live in
    ``site_builder.league_constant``, which fetches and caches them instead
    of anyone maintaining a table by hand.
"""

import datetime
import os
from pathlib import Path

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

# ── Season rollover ──
# There is deliberately no "annual constants" table in this file any more.
# Every per-season, per-league number (FIP constants, league ERA, park
# factors, lg_wOBA / lg_R/PA) is fetched and cached by
# site_builder.league_constant, so nothing here needs a manual spring
# refresh. SEASON_YEAR is the only season-dependent value left, and it rolls
# over on its own.

# ══════════════════════════════════════════════════════════════════════════
# 2. STABLE DOMAIN CONSTANTS
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

PITCH_HAND_SPLITS = (
    ("all", "全部"),
    ("L", "左投"),
    ("R", "右投"),
)

# Pitch-type → super-category classification: the standard three-way
# Statcast / sabermetric split into fastballs (velocity + backspin carry),
# breaking balls (spin-driven lateral/vertical break), and offspeed pitches
# (defining trait is reduced velocity relative to the pitcher's fastball).
# Sources: FanGraphs "Pitch Type Abbreviations & Classifications" library
# page and Baseball Savant's pitch-type groupings.
PITCH_TYPE_GROUPS = (
    ("FASTBALL", "Fastball", ("FF", "SI", "FC", "FA", "FT")),
    ("BREAKING", "Breaking", ("SL", "ST", "SV", "CU", "CB", "KC", "CS", "SC")),
    ("OFFSPEED", "Offspeed", ("CH", "FS", "FO", "KN", "EP")),
)
PITCH_TYPE_TO_GROUP: dict[str, str] = {
    code: key for key, _label, codes in PITCH_TYPE_GROUPS for code in codes
}

# Ball-strike count buckets shared by per-level computation and cross-level
# combination. Labels are stored inside the statcast JSON payload.
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

# ── 逐球軌跡幾何 ──
# 來源：MLB Stats API 的 ``pitchData``。API 給的是一組九參數等加速度軌跡擬合
# （x0/y0/z0、vX0/vY0/vZ0、aX/aY/aZ），可以求值在任何一個 y 平面上。
#
# 投手板前緣到本壘板尖端的距離，規則值 60.5 呎。出手點平面 = 60.5 - extension。
RUBBER_TO_PLATE_FT = 60.5

# 軌跡擬合的原點平面，也就是 ``coordinates.x0`` / ``z0`` 所在的位置。
#
# 這個常數有兩個用途，兩者都很重要：
#
# 1. 它「不是」出手點。x0/z0 是球飛到距本壘板 50 呎時的位置，此時球已離手約
#    3–4 呎、飛了約 30 毫秒，期間已經因為自身速度而位移（主導項是等速項
#    v·t，不是重力或球種位移）。直接把 x0/z0 當出手點會同時低估出手高度
#    與左右幅度，且方向隨慣用手相反，等於把左右投的出手寬度差壓縮約 4 吋。
#    出手點的正確平面是 60.5 - extension——這點用 API 自己的 ``startSpeed``
#    驗證過：在出手平面求值可還原到 0.04 mph 誤差，在 50 呎平面則差 0.51 mph。
#
# 2. 它是舊資料缺 ``y0`` 時的預設值。PITCHf/x 剛上線時各球場的擬合原點並不
#    統一，實測出現過 40、45、50、55 四種平面：2007 年賽季初全聯盟是 55 呎，
#    6 月下旬出現 40 呎，7 月中多數球場才轉 50 呎；2009 年 Fenway Park 另有
#    5 場跑在 45 呎，其中 2009-07-28 那場甚至在場中從 45 切換到 50。把不同
#    平面的 x0/z0 平均，等於把沿飛行路徑相距最多 15 呎的位置混在一起。
#
#    因此 y0 必須逐球讀，不能整組共用一個值。本專案的處理方式是：
#    ``sync.extract`` 會把 API 的 ``coordinates.y0`` 一併存進逐球紀錄，
#    ``stats.pitching.release_point._origin_plane()`` 逐球取用；只有在該欄
#    不存在（在 y0 開始儲存之前寫入的舊列）時才退回這個預設值。
#
#    退回 50 對現有資料是精確的：全庫 49,233 顆帶完整軌跡與落點的投球逐顆
#    做過平面判定，0 顆無法判定，非 50 的只有 2007 全年與 2009-08-10；而這
#    些比賽的逐球紀錄都已經回抓過、y0 已入庫。但這是對「現有資料」的稽核
#    結論，不是對 MLB 的通則主張——日後若加入有 2017 年前資歷的新球員，
#    應重跑一次平面稽核再信任這個預設值。
PITCH_TRAJECTORY_ORIGIN_Y_FT = 50.0

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

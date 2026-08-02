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

# Bunt-attempt subset of SWING_CODES — used by stats.core.atypical to flag
# individual pitches for BUNT_PITCH exclusion regardless of PA outcome.
BUNT_SWING_CODES = {"M", "L", "O"}

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

# 球種代碼的單一真相來源。過去中文名（PITCH_TYPE_ZH）跟配色
# （PITCH_TYPE_FAMILIES）是兩張各自維護、僅靠人工對齊代碼集合的表，前端
# pitch-plinko.js / pitcher-charts.js 又各自手抄一份英文名 + 配色，四份資料
# 互相同步全靠人眼——結果是 KC/CS/SC 在 JS 手抄表裡被誤併成跟 CU 同一個
# "Curveball"，圖例因此出現看似重複、實則是不同代碼的兩行。
#
# 現在改成兩層表：先定義「家族」（球速 × 位移方向切出的一層，色相依附於
# 此），再定義每個 API 代碼屬於哪個家族＋中英文名稱。PITCH_TYPE_ZH、
# PITCH_TYPE_COLORS、PITCH_TYPE_TO_FAMILY、PITCH_TYPE_GROUPS、
# PITCH_TYPE_TO_GROUP、PITCH_GROUP_LABELS、PITCH_GROUP_ORDER、
# PITCH_TYPE_DISPLAY 全部從這兩張表算出來，不再各自維護一份原始資料；
# render/env.py 把 PITCH_TYPE_DISPLAY 序列化成 JSON 注入 base.j2，
# PITCH_TAG_CSS 是生成好的 CSS 規則字串，前端 JS/CSS 從此不再手抄任何一份。
#
# 三大分類的顯示標籤與固定列序（分類表永遠照 Fastball → Breaking → Offspeed
# 排，不隨球數多寡浮動）。
GROUP_ORDER: tuple[str, ...] = ("FASTBALL", "BREAKING", "OFFSPEED")
GROUP_LABELS: dict[str, str] = {
    "FASTBALL": "Fastball",
    "BREAKING": "Breaking",
    "OFFSPEED": "Offspeed",
}

# 球種配色的家族表：色相 = 家族，同家族成員共用同一組底色／文字色（文字色
# 是底色在 OKLCH 拉到 L≈0.84 手動調出來的值，直接存值而非即時運算，
# 對比皆 >= 9.9:1）。
#
# 規則
# ────
# 1. 家族是三大分類底下、依「球速 × 位移方向」再切的一層，永不跨分類邊界：
#    FASTBALL 拿暖色段（紅／橙／金），BREAKING 拿藍／紫，OFFSPEED 拿綠／粉。
# 2. 同家族成員共用同一色票——這是硬性限制不是偏好，見下。
# 3. 沒有 fallback 灰：每個會進到圖表或標籤的代碼都在 PITCH_TYPES 有一筆。
#    非球種代碼（NON_PITCH_TYPE_CODES）早在 filter_known_pitch_events() 就
#    被濾掉，不會走到配色這一步。
#
# 為什麼是 7 個色票（原本 8 個，SWEEPER 併入 SLIDER）
# ────────────────────────────
# 位移散點圖任兩個球種都可能相鄰，屬於 all-pairs 情境。在本站深色表面
# （#09090b）、OKLCH 明度帶 0.48–0.67、彩度 >= 0.10、對比 >= 3:1 的條件下實測
# 各色數的最佳可達分離度（Machado 2009 protan/deutan 模擬，OKLab ΔE×100）：
#
#     色數   最差 CVD ΔE   最差常視 ΔE   （門檻 8.0 / 15.0）
#      6        11.0          19.1        通過
#      7         9.1          16.6        通過
#      8         8.0          15.0        通過
#      9         7.4          13.9        不通過
#     12         5.9          10.6        不通過
#
# 8 是天花板；SWEEPER（掃球／滑曲球）併入 SLIDER 家族後只用 7 色，落在已驗證
# 安全的範圍內，掃球／滑曲球從此與滑球／子彈球共用同一組藍色。
#
# 代價：同家族球種同時出現時色彩不可分（實測 95 組（球員 × 年度）球種組合中
# SL+ST 佔 20 組、曲球家族內部撞色 13 組）。這些情境靠次要編碼辨識——圖例、
# 標籤文字、hover tooltip 都會寫出球種全名，識別從不只靠顏色。
PITCH_FAMILY_META: dict[str, dict] = {
    "FOUR_SEAM": {"label": "速球", "group": "FASTBALL", "bg": "#fc3766", "text": "#ff9fae"},
    "SINKER":    {"label": "伸卡", "group": "FASTBALL", "bg": "#bd3b05", "text": "#ffa680"},
    "CUTTER":    {"label": "卡特", "group": "FASTBALL", "bg": "#c58104", "text": "#ffbc5b"},
    "SLIDER":    {"label": "滑球", "group": "BREAKING", "bg": "#4b88fd", "text": "#93cbff"},
    "CURVE":     {"label": "曲球", "group": "BREAKING", "bg": "#9618d0", "text": "#ecaeff"},
    "CHANGEUP":  {"label": "變速", "group": "OFFSPEED", "bg": "#18761e", "text": "#8de58b"},
    "KNUCKLE":   {"label": "特殊", "group": "OFFSPEED", "bg": "#bf0b82", "text": "#ffa0dd"},
}

# 三大分類標籤（.pitch-fastball 等）借用哪個家族的顏色代表：取各分類中球數
# 最多的家族色，與改版前的分類配色一致（紅／藍／綠）。
GROUP_REPRESENTATIVE_FAMILY: dict[str, str] = {
    "FASTBALL": "FOUR_SEAM",
    "BREAKING": "SLIDER",
    "OFFSPEED": "CHANGEUP",
}

# 球種代碼主表：每個會進到圖表或標籤的代碼一筆，含中英文顯示名與所屬家族。
#
# 中文譯名來源：官方 ``/api/v1/pitchTypes`` 端點的 description（Four-seam
# FB、Knuckleball、Eephus Pitch）與 playByPlay 實際回傳的 pitch_name
# （Four-Seam Fastball、Knuckle Ball、Eephus）並不一致，故以「代碼」為鍵。
# 英文顯示名同理不採 API 原始字串，各代碼獨立給一個顯示名（過去只存在於
# 前端 JS 手抄表，未跟中文譯名的區分邏輯對齊）。
#
# 刻意不收錄的代碼：IN（Intentional Ball）、PO（Pitchout）、AB（Automatic
# Ball）、AS（Automatic Strike）、NP（No Pitch）都不是球種而是投球事件；
# UN（Unknown）則會被 filter_known_pitch_events() 濾掉。查無資料者一律不進
# legend，因此這些代碼即使出現在表格列裡也不會出現在 tooltip 中。
#
# CU/CB 中英文顯示名刻意相同：CB 是舊版 API 對曲球的代碼，語意上就是同一種
# 球路，不是兩種球，只是不同年代留下的字串；兩者在此仍各自成列（各自統計，
# 圖例可能同時各出現一行），不做代碼合併。
PITCH_TYPES: dict[str, dict] = {
    # Fastball
    "FF": {"zh": "四縫線速球", "en": "Four-Seam", "family": "FOUR_SEAM"},
    "FA": {"zh": "速球", "en": "Fastball", "family": "FOUR_SEAM"},
    "FT": {"zh": "二縫線速球", "en": "Two-Seam", "family": "SINKER"},
    "SI": {"zh": "伸卡球", "en": "Sinker", "family": "SINKER"},
    "FC": {"zh": "卡特球", "en": "Cutter", "family": "CUTTER"},
    # Breaking
    "SL": {"zh": "滑球", "en": "Slider", "family": "SLIDER"},
    "GY": {"zh": "子彈球", "en": "Gyroball", "family": "SLIDER"},
    "ST": {"zh": "橫掃球", "en": "Sweeper", "family": "SLIDER"},
    "SV": {"zh": "滑曲球", "en": "Slurve", "family": "SLIDER"},
    "CU": {"zh": "曲球", "en": "Curveball", "family": "CURVE"},
    "CB": {"zh": "曲球", "en": "Curveball", "family": "CURVE"},
    "KC": {"zh": "彈指曲球", "en": "Knuckle Curve", "family": "CURVE"},
    "CS": {"zh": "慢速曲球", "en": "Slow Curve", "family": "CURVE"},
    "SC": {"zh": "螺旋球", "en": "Screwball", "family": "CURVE"},
    # OffSpeed
    "CH": {"zh": "變速球", "en": "Changeup", "family": "CHANGEUP"},
    "FS": {"zh": "快速指叉球", "en": "Splitter", "family": "CHANGEUP"},
    "FO": {"zh": "指叉球", "en": "Forkball", "family": "CHANGEUP"},
    "KN": {"zh": "蝴蝶球", "en": "Knuckleball", "family": "KNUCKLE"},
    "EP": {"zh": "小便球", "en": "Eephus", "family": "KNUCKLE"},
}

# ── 以下皆從 PITCH_TYPES / PITCH_FAMILY_META 推導，不手動維護 ──

PITCH_TYPE_ZH: dict[str, str] = {code: info["zh"] for code, info in PITCH_TYPES.items()}

PITCH_TYPE_COLORS: dict[str, str] = {
    code: PITCH_FAMILY_META[info["family"]]["bg"] for code, info in PITCH_TYPES.items()
}

PITCH_TYPE_TO_FAMILY: dict[str, str] = {code: info["family"] for code, info in PITCH_TYPES.items()}

PITCH_TYPE_TO_GROUP: dict[str, str] = {
    code: PITCH_FAMILY_META[info["family"]]["group"] for code, info in PITCH_TYPES.items()
}

# Pitch-type → super-category classification: the standard three-way
# Statcast / sabermetric split into fastballs (velocity + backspin carry),
# breaking balls (spin-driven lateral/vertical break), and offspeed pitches
# (defining trait is reduced velocity relative to the pitcher's fastball).
# Sources: FanGraphs "Pitch Type Abbreviations & Classifications" library
# page and Baseball Savant's pitch-type groupings.
PITCH_TYPE_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = tuple(
    (
        group,
        GROUP_LABELS[group],
        tuple(
            code for code, info in PITCH_TYPES.items()
            if PITCH_FAMILY_META[info["family"]]["group"] == group
        ),
    )
    for group in GROUP_ORDER
)
PITCH_GROUP_LABELS: dict[str, str] = GROUP_LABELS
PITCH_GROUP_ORDER: tuple[str, ...] = GROUP_ORDER

# 前端用的攤平表：build 時序列化成 JSON 注入頁面（見 render/env.py 的
# ``pitch_type_display`` global、base.j2 的 ``#pitch-type-data``），取代過去
# pitch-plinko.js / pitcher-charts.js 各自手抄一份 PITCH_COLORS / PITCH_NAMES
# 的做法。
PITCH_TYPE_DISPLAY: dict[str, dict] = {
    code: {
        "zh": info["zh"],
        "en": info["en"],
        "family": info["family"],
        "group": PITCH_FAMILY_META[info["family"]]["group"],
        "bg": PITCH_FAMILY_META[info["family"]]["bg"],
        "text": PITCH_FAMILY_META[info["family"]]["text"],
    }
    for code, info in PITCH_TYPES.items()
}


def _build_pitch_tag_css() -> str:
    """Generate the ``.pitch-{code}`` / ``.pitch-{group}`` CSS rules that used
    to be hand-copied into gamelogs.css. One rule per family (all member
    codes share a selector) plus one per super-category group."""
    family_codes: dict[str, list[str]] = {}
    for code, info in PITCH_TYPES.items():
        family_codes.setdefault(info["family"], []).append(code)

    def _rule(selector: str, meta: dict) -> str:
        r, g, b = (int(meta["bg"][i:i + 2], 16) for i in (1, 3, 5))
        return f"{selector} {{ background: rgb({r} {g} {b} / 0.22); color: {meta['text']}; }}"

    lines = [
        _rule(", ".join(f".pitch-{c.lower()}" for c in codes), PITCH_FAMILY_META[family])
        for family, codes in family_codes.items()
    ]
    lines += [
        _rule(f".pitch-{group.lower()}", PITCH_FAMILY_META[family])
        for group, family in GROUP_REPRESENTATIVE_FAMILY.items()
    ]
    return "\n".join(lines)


PITCH_TAG_CSS: str = _build_pitch_tag_css()

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

# Pitch-type codes that don't represent an actual delivered pitch with real
# "stuff": IN (intentional-walk lob), PO (pitchout), AB/AS (pitch-clock
# automatic ball/strike — no pitch thrown at all), NP (no pitch), UN
# (unknown). Combined with the blank/placeholder check in
# ``is_unknown_pitch_type()`` so every pitch-type breakdown table (pitcher
# and batter alike) excludes them from a single source of truth.
NON_PITCH_TYPE_CODES = {"UN", "IN", "PO", "AB", "AS", "NP"}

# 佔位字串：API 沒有給出球種時，pitch_type / pitch_name 會落在這幾個值上
# （MiLB 舊賽季大量如此）。比對前一律 strip + upper。
UNKNOWN_PITCH_TOKENS = frozenset({"UN", "UNKNOWN"})

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

# Bunt-attempt subset of {GB,LD,PU}_TRAJECTORIES — a PA whose final in-play
# ball lands in one of these is a completed bunt attempt
# (stats.core.atypical Reason.BUNT_PA).
BUNT_TRAJECTORIES = {"bunt_grounder", "bunt_line_drive", "bunt_popup"}
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

"""
Single source of truth for MLB/MiLB league-level logic.

Every piece of level knowledge — sportId mapping, historical-spelling aliases,
hierarchy rank, and era-aware display string — lives here. No other module may
define its own level constant table; they import from this one instead.

Background: the 2020–21 MiLB reorganization renamed levels and eliminated the
short-season and rookie-advanced tiers, but the *hierarchy* never changed. So we
model each level as a "tier" with a stable rank, plus an era-aware display name:

    tier   rank  sportId  2021+ (modern)   2020- (legacy / "period name")
    ─────  ────  ───────  ──────────────   ──────────────────────────────
    MLB     0    1        MLB              MLB
    AAA     1    11       AAA              AAA
    AA      2    12       AA               AA
    A+      3    13       A+  (High-A)     A(Adv)  (Class A-Advanced)
    A       4    14       A   (Low-A)      A(Full) (Class A full-season)
    A-      5    15       — (eliminated)   A(Short) (Class A Short Season)
    ROA     6    5442     — (eliminated)   ROA     (Rookie Advanced)
    ROK     7    16       ROK              ROK
    WIN     8    17       WIN              WIN
    Minors  99   21       Minors           Minors

Storage contract: every DB level column (``season_stats.sport_level``,
``game_logs.sport_level``, ``players.level``, ``league_fip_constants.sport_level``)
holds the tier *key*, written through :func:`sport_to_tier_key`. Period names
never reach the DB; :func:`level_display` derives them from the season year.
"""

from dataclasses import dataclass
from typing import Optional

# Season cutoff: 2021 onward uses the reorganized ("modern") names. 2020 had no
# MiLB season (COVID), so the boundary is clean.
_MODERN_FROM_YEAR = 2021

# 跨層級合計列的 sentinel，不是真的層級：
#   COMBINED_LEVEL — Statcast 年度合計列（render/pages.py::_build_statcast_entries）
#   ALL_LEVELS     — 走勢圖跨層級累計序列（graph/season_trend.py），也是前端
#                    篩選器「All Levels」選項的值（src/static/js/util.js 寫死同一字串）
COMBINED_LEVEL = "_combined"
ALL_LEVELS = "_all"
_ALL_LEVELS_LABEL = "All Levels"
_SENTINELS = frozenset({COMBINED_LEVEL, ALL_LEVELS, ""})


@dataclass(frozen=True)
class Tier:
    key: str                       # canonical tier key, e.g. "A+"
    rank: int                      # hierarchy rank (lower = higher level)
    sport_ids: tuple               # MLB Stats API sportId(s)
    modern: Optional[str]          # 2021+ display string (None = tier eliminated)
    legacy: str                    # 2020- display string ("period name")
    aliases: tuple                 # every raw spelling seen in the API / DB
    names: tuple = ()              # official MLB Stats API sport `name` strings


# ── The one and only level table ──
# rank 順序與 MLB Stats API /sports 的 sortOrder 一致（A(Short) 501 < ROA 601 < ROK 701）
TIERS = (
    Tier("MLB",    0,  (1,),    "MLB",    "MLB",      ("MLB",),
         ("Major League Baseball",)),
    Tier("AAA",    1,  (11,),   "AAA",    "AAA",      ("AAA",),
         ("Triple-A",)),
    Tier("AA",     2,  (12,),   "AA",     "AA",       ("AA",),
         ("Double-A",)),
    Tier("A+",     3,  (13,),   "A+",     "A(Adv)",   ("A+", "A(Adv)", "A (Adv)"),
         ("High-A", "Class A-Advanced", "Class A Advanced")),
    Tier("A",      4,  (14,),   "A",      "A(Full)",  ("A", "A(Full)", "A (Full)"),
         ("Single-A", "Low-A", "Class A")),
    Tier("A-",     5,  (15,),   None,     "A(Short)", ("A-", "A(Short)", "A (Short)"),
         ("Class A Short Season",)),
    # Rookie Advanced（Pioneer / Appalachian League）有自己的 sportId 5442，
    # 與 ROK（sportId 16）是不同層級；2021 年重組後廢除，所以跟 A- 一樣沒有 modern 名稱
    Tier("ROA",    6,  (5442,), None,     "ROA",      ("ROA",),
         ("Rookie Advanced",)),
    Tier("ROK",    7,  (16,),   "ROK",    "ROK",      ("ROK", "Rk", "Rookie"),
         ("Rookie",)),
    Tier("WIN",    8,  (17,),   "WIN",    "WIN",      ("WIN",),
         ("Winter Leagues",)),
    Tier("Minors", 99, (21,),   "Minors", "Minors",   ("Minors",),
         ("Minor League Baseball",)),
)

MLB_KEY = "MLB"  # SQL 參數用（WHERE sport_level = ?），避免在 SQL 字串裡寫死層級
# 層級未知時的預設值（沒有現役球隊、也沒有任何 season_stats 可推算）；
# db/schema.py 的 players.level DEFAULT 'Minors' 必須跟它一致
MINORS_KEY = "Minors"

_UNKNOWN_RANK = 50  # below every real level, above the "Minors" aggregate (99)

_BY_ALIAS = {alias: t for t in TIERS for alias in t.aliases}
_BY_SPORT_ID = {sid: t for t in TIERS for sid in t.sport_ids}
_BY_NAME = {name: t for t in TIERS for name in t.names}
_BY_KEY = {t.key: t for t in TIERS}

# 附屬小聯盟：MLB 與 WIN 之間的 tier（WIN 是冬季聯盟，Minors 是 API 的整季合計列）
_MILB_KEYS = tuple(
    t.key for t in TIERS if _BY_KEY["MLB"].rank < t.rank < _BY_KEY["WIN"].rank
)

# 查詢未來賽程（/schedule?sportId=...）用：MLB 加上仍存在的附屬小聯盟層級。
# 已廢除的 A-/ROA（modern 為 None）不會有未來比賽；WIN 與 Minors 合計列不追蹤
SCHEDULE_SPORT_IDS = tuple(
    sid
    for t in TIERS
    if t.modern is not None and (t.key == MLB_KEY or t.key in _MILB_KEYS)
    for sid in t.sport_ids
)


def resolve_tier(raw: Optional[str]) -> Optional[Tier]:
    """Resolve any raw level spelling (modern code or historical) to its Tier."""
    if not raw:
        return None
    return _BY_ALIAS.get(raw)


def level_rank(raw: Optional[str]) -> int:
    """Hierarchy rank for sorting/comparison (lower = higher level).

    Collapses every era/spelling onto its tier, so `A(Adv)` and `A+` rank equal.
    Unknown levels fall back to 50 (below real levels, above the Minors aggregate).
    """
    tier = resolve_tier(raw)
    return tier.rank if tier else _UNKNOWN_RANK


def level_display(raw: Optional[str], year: Optional[int]) -> Optional[str]:
    """Period-accurate display string for *raw* as it was known in *year*.

    - Sentinels (`_combined`, `_all`, ``) and unknown values pass through.
    - 2021+ seasons use the modern code (A+, A, ROK …); 2020- seasons keep the
      period name (A(Adv), A(Full), A(Short) …). Driven by *year*.
    - The DB stores tier keys only, so this is the one place a period name
      is produced; the correctness of the label depends on *year*.
    """
    if raw in _SENTINELS or raw is None:
        return raw
    tier = resolve_tier(raw)
    if tier is None:
        return raw
    if year is not None and year >= _MODERN_FROM_YEAR and tier.modern is not None:
        return tier.modern
    return tier.legacy


def level_label(raw: Optional[str], year: Optional[int]) -> Optional[str]:
    """給人看的層級標籤：合計 sentinel 顯示 ``All Levels``，其餘同 :func:`level_display`。

    ``level_display`` 讓 sentinel 原樣通過，因為前端篩選器拿它當 ``<option>`` 的值；
    需要顯示文字的地方（``data-level-label``、走勢圖標籤）用這個。
    """
    if raw in (COMBINED_LEVEL, ALL_LEVELS):
        return _ALL_LEVELS_LABEL
    return level_display(raw, year)


def is_level(raw: Optional[str], *tier_keys: str) -> bool:
    """*raw*（任何拼法）是否屬於 *tier_keys* 其中之一。

    *tier_keys* 必須是 TIERS 裡的 key；打錯字或傳入舊制名稱（``A(Adv)``）時直接
    ``ValueError``，否則這種呼叫會永遠回 False 而沒人發現。未知層級一律回 False。
    """
    if not tier_keys:
        raise ValueError("is_level() needs at least one tier key")
    unknown = [k for k in tier_keys if k not in _BY_KEY]
    if unknown:
        raise ValueError(f"not tier keys: {unknown}")
    tier = resolve_tier(raw)
    return tier is not None and tier.key in tier_keys


def is_mlb(raw: Optional[str]) -> bool:
    """Whether *raw* is the MLB tier — the only MLB check the codebase should use."""
    return is_level(raw, MLB_KEY)


def is_milb(raw: Optional[str]) -> bool:
    """*raw* 是否為附屬小聯盟（AAA … ROK，含已廢除的 A-/ROA）。

    不含冬季聯盟 ``WIN``、``Minors`` 合計列與無法對應 tier 的層級（如獨立聯盟
    ``IND``），所以 MiLB 生涯合計不能寫成 ``not is_mlb()``。
    """
    return is_level(raw, *_MILB_KEYS)


def to_tier_key(raw: Optional[str]) -> str:
    """把任何層級拼法收斂成 tier key；未知拼法原樣回傳，``None`` 視為空字串。"""
    if not raw:
        return ""
    tier = resolve_tier(raw)
    return tier.key if tier else raw


def sport_to_tier_key(sport: Optional[dict]) -> str:
    """MLB Stats API 的 sport 物件 → 寫入 DB 的 tier key。所有寫入端都走這裡。

    依序用 ``id``、``abbreviation``、``name`` 解析。``id`` 優先，因為
    ``abbreviation`` 會隨年代變（2019 年 sportId 13 回 ``A(Adv)``），``name`` 也是。
    三者都對不到（例如 sportId 23 獨立聯盟）時保留 API 的 ``abbreviation``，
    不丟掉資訊；``level_rank`` 會把它排在所有已知層級之後。
    """
    # sport 物件缺漏（例如 gameLog 的 group 層沒有 sport）
    if not sport:
        return ""
    tier = (
        _BY_SPORT_ID.get(sport.get("id"))
        or resolve_tier(sport.get("abbreviation"))
        or _BY_NAME.get(sport.get("name", ""))
    )
    if tier:
        return tier.key
    return sport.get("abbreviation") or ""

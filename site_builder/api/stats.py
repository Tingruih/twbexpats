"""Player stat endpoints (yearByYear / seasonAdvanced / gameLog /
sabermetrics / expectedStatistics).

全部經由 ``_fetch_stats``（每年一次、或不帶年份一次），任一請求在重試用盡後失敗就
整個丟出 ``FetchError``，不回傳只有一部分的結果：呼叫端才能分辨「API 沒有資料」
與「抓取失敗」，失敗時保留 DB 舊值並在下次執行重抓（見 sync/players.py）。
"""

from typing import Optional

from ..constants import GAME_LOG_GAME_TYPES
from ..positions import ROLES, stat_group_for_role, stat_groups_param
from .client import BASE_URL, get_json

# leagueListId：不帶時 API 只回 MLB；mlb_milb（官方 LeagueListsEnum 的 MLB_MILB）
# 一次回 MLB + 所有 MiLB 層級，資料與「不帶 + milb_all」兩次請求逐筆相同，
# 只有 group/split 的順序不同。寫入端依角色分存、與順序無關（見 sync/players.py），
# 所以可以只打一次。
MLB_ONLY = (None,)
MLB_AND_MILB = ("mlb_milb",)


def _fetch_stats(
    mlb_id: int,
    query: str,
    years: Optional[list[int]] = None,
    *,
    leagues: tuple[Optional[str], ...] = MLB_AND_MILB,
) -> list:
    """``/people/{mlb_id}/stats?{query}`` 回傳的 ``stats`` 列表，依「年份 → 聯盟清單」順序串接。

    ``years`` 給定時每年加 ``season`` 各打一次，否則不帶 ``season``（API 預設球季）；
    每一年對 ``leagues`` 裡的每個 leagueListId 各打一次（None 代表不帶，只查 MLB）。
    """
    stats = []
    for yr in years or [None]:
        for league in leagues:
            url = f"{BASE_URL}/people/{mlb_id}/stats?{query}"
            if league:
                url += f"&leagueListId={league}"
            if yr:
                url += f"&season={yr}"
            stats.extend(get_json(url).get("stats", []))
    return stats


def get_player_stats(mlb_id: int) -> list:
    """
    api endpoint: /people/{mlb_id}/stats?stats=yearByYear&group=hitting,pitching,fielding&leagueListId=mlb_milb

    回傳所有年份的選手MLB與MiLB基礎數據，包含打擊、投球和守備。
    """
    return _fetch_stats(
        mlb_id, f"stats=yearByYear&group={stat_groups_param(ROLES, fielding=True)}"
    )


def get_player_advanced_stats(mlb_id: int, years: Optional[list[int]] = None) -> list:
    """
    api endpoint: /people/{mlb_id}/stats?stats=seasonAdvanced&group=hitting,pitching&season={year}&leagueListId=mlb_milb

    傳入要查詢的 Mlb ID 與 年份
    回傳每年份的選手MLB與MiLB進階數據。
    """
    return _fetch_stats(
        mlb_id, f"stats=seasonAdvanced&group={stat_groups_param(ROLES)}", years
    )


def get_game_logs(mlb_id: int, season: int) -> list:
    """Fetch game logs for a specific season, MLB and MiLB together (``leagueListId=mlb_milb``).

    Always covers both so shuttle players (MLB ↔ MiLB) get all game logs
    regardless of current assignment.
    Includes postseason games (see ``GAME_LOG_GAME_TYPES``); each split
    carries its own ``gameType``.
    """
    game_types = ",".join(GAME_LOG_GAME_TYPES)
    return _fetch_stats(
        mlb_id, f"stats=gameLog&group={stat_groups_param(ROLES)}&gameType={game_types}", [season]
    )


def get_player_sabermetrics(mlb_id: int, years: Optional[list[int]] = None) -> list:
    """Fetch sabermetrics stats (FIP/xFIP/WAR) — MLB only.

    Returns the raw ``stats`` list from the API; caller walks splits.
    """
    return _fetch_stats(
        mlb_id, f"stats=sabermetrics&group={stat_groups_param(ROLES)}", years, leagues=MLB_ONLY
    )


def get_player_expected_stats(
    mlb_id: int,
    role: str,
    years: Optional[list[int]] = None,
) -> list:
    """Fetch expectedStatistics (xwOBA, xBA, xSLG) for one role — MLB only.

    ``role`` 刻意沒有預設值：帶錯角色會拿到另一個角色的空結果，而
    ``db/season_fetches`` 仍會把它登記成「抓過」，過去球季從此不再重抓。

    Only fetches the MLB endpoint. MiLB (leagueListId=milb_all / mlb_milb)
    always returns 0.0 for all expected stats fields — the MLB Stats API does
    not publish Statcast-derived expected stats for minor-league play — so
    calling it wastes bandwidth and latency.

    Note: API fields are named ``avg``/``slg``/``woba``/``wobaCon`` (no x prefix).
    """
    return _fetch_stats(
        mlb_id, f"stats=expectedStatistics&group={stat_group_for_role(role)}", years, leagues=MLB_ONLY
    )

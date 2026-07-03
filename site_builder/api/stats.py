"""Player stat endpoints (yearByYear / seasonAdvanced / gameLog /
sabermetrics / expectedStatistics)."""

import logging
from typing import Optional

from .client import BASE_URL, get_json

logger = logging.getLogger(__name__)


def get_player_stats(mlb_id: int) -> list:
    """
    api endpoint: /people/{mlb_id}/stats?stats=yearByYear&group={groups}" (MLB)
                : /people/{mlb_id}/stats?stats=yearByYear&leagueListId=milb_all&group={groups}" (MiLB)

    回傳所有年份的選手MLB與MiLB基礎數據，包含打擊、投球和守備。
    """
    all_stats = []
    groups = "hitting,pitching,fielding"

    # MLB endpoint — returns MLB-level seasons only; empty for players without MLB time
    try:
        url = f"{BASE_URL}/people/{mlb_id}/stats?stats=yearByYear&group={groups}"
        all_stats.extend(get_json(url).get("stats", []))
    except Exception as e:
        logger.warning("MLB yearByYear failed for %s: %s", mlb_id, e)

    # MiLB endpoint — always needed for minor-league history
    try:
        url = (
            f"{BASE_URL}/people/{mlb_id}/stats"
            f"?stats=yearByYear&leagueListId=milb_all&group={groups}"
        )
        all_stats.extend(get_json(url).get("stats", []))
    except Exception as e:
        logger.warning("MiLB yearByYear failed for %s: %s", mlb_id, e)

    return all_stats


def get_player_advanced_stats(mlb_id: int, years: Optional[list[int]] = None) -> list:
    """
    api endpoint: /people/{mlb_id}/stats?stats=seasonAdvanced&group={groups}&season={year} (MLB)
                : /people/{mlb_id}/stats?stats=seasonAdvanced&leagueListId=milb_all&group={groups}&season={year} (MiLB)

    傳入要查詢的 Mlb ID 與 年份
    回傳每年份的選手MLB與MiLB進階數據。
    """
    all_stats = []
    groups = "hitting,pitching"
    fetch_years = years if years else [None]

    for yr in fetch_years:
        year_param = f"&season={yr}" if yr else ""

        # MLB endpoint — returns empty for players without MLB time
        url = f"{BASE_URL}/people/{mlb_id}/stats?stats=seasonAdvanced&group={groups}{year_param}"
        try:
            all_stats.extend(get_json(url).get("stats", []))
        except Exception as e:
            logger.warning(
                "MLB seasonAdvanced failed for %s year=%s: %s", mlb_id, yr, e
            )

        url = (
            f"{BASE_URL}/people/{mlb_id}/stats"
            f"?stats=seasonAdvanced&leagueListId=milb_all&group={groups}{year_param}"
        )
        try:
            all_stats.extend(get_json(url).get("stats", []))
        except Exception as e:
            logger.warning(
                "MiLB seasonAdvanced failed for %s year=%s: %s", mlb_id, yr, e
            )

    return all_stats


def get_game_logs(mlb_id: int, season: int) -> list:
    """Fetch game logs for a specific season from both MLB and MiLB endpoints.

    Always fetches both endpoints so shuttle players (MLB ↔ MiLB) get all
    game logs regardless of current assignment.
    """
    all_logs = []

    # MLB endpoint — returns MLB game logs; empty for players without MLB time
    url = (
        f"{BASE_URL}/people/{mlb_id}/stats"
        f"?stats=gameLog&season={season}&group=hitting,pitching"
    )
    try:
        all_logs.extend(get_json(url).get("stats", []))
    except Exception as e:
        logger.warning("MLB game logs failed for %s/%s: %s", mlb_id, season, e)

    url = (
        f"{BASE_URL}/people/{mlb_id}/stats"
        f"?stats=gameLog&season={season}&leagueListId=milb_all&group=hitting,pitching"
    )
    try:
        all_logs.extend(get_json(url).get("stats", []))
    except Exception as e:
        logger.warning("MiLB game logs failed for %s/%s: %s", mlb_id, season, e)

    return all_logs


def get_player_sabermetrics(mlb_id: int, years: Optional[list[int]] = None) -> list:
    """Fetch sabermetrics stats (FIP/xFIP/WAR) — MLB only.

    Returns the raw ``stats`` list from the API; caller walks splits.
    """
    all_stats = []
    fetch_years = years if years else [None]
    for yr in fetch_years:
        year_param = f"&season={yr}" if yr else ""
        url = (
            f"{BASE_URL}/people/{mlb_id}/stats"
            f"?stats=sabermetrics&group=pitching,hitting{year_param}"
        )
        try:
            all_stats.extend(get_json(url).get("stats", []))
        except Exception as e:
            logger.warning("sabermetrics failed for %s year=%s: %s", mlb_id, yr, e)
    return all_stats


def get_player_expected_stats(
    mlb_id: int,
    years: Optional[list[int]] = None,
    group: str = "pitching",
) -> list:
    """Fetch expectedStatistics (xwOBA, xBA, xSLG) — MLB only.

    Only fetches the MLB endpoint. The MiLB endpoint (leagueListId=milb_all)
    always returns 0.0 for all expected stats fields — the MLB Stats API does
    not publish Statcast-derived expected stats for minor-league play — so
    calling it wastes bandwidth and latency.

    Note: API fields are named ``avg``/``slg``/``woba``/``wobaCon`` (no x prefix).
    """
    all_stats = []
    fetch_years = years if years else [None]
    for yr in fetch_years:
        year_param = f"&season={yr}" if yr else ""

        # MLB endpoint — returns valid xBA/xSLG/xwOBA for MLB seasons only
        url = (
            f"{BASE_URL}/people/{mlb_id}/stats"
            f"?stats=expectedStatistics&group={group}{year_param}"
        )
        try:
            all_stats.extend(get_json(url).get("stats", []))
        except Exception as e:
            logger.warning(
                "MLB expectedStatistics failed for %s year=%s: %s", mlb_id, yr, e
            )

    return all_stats

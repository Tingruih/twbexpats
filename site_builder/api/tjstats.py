"""TJStats (tjstats.ca) park factors and league constants — HTML scrape.

Both fetches are best-effort enhancements for wRC+ computation, not core
data, so network failures must never raise; they log a warning and return {}.
A page whose layout no longer matches the parser also logs a warning (the
wRC+ column would otherwise vanish without a trace). A season that has not
been published yet renders the same page minus its table(s) (verified
2026-09: pf_season=2027 has no table.tjs-guts, lc_season=2027 has only the
park-factor one), so a missing table only warns for past seasons, which are
always published; for the current season or later it logs at INFO.
"""

import logging

from bs4 import BeautifulSoup

from ..constants import SEASON_YEAR
from ..util.log import describe_exc
from .client import FetchError, get_text

logger = logging.getLogger(__name__)


def _log_missing_table(year: int, what: str, url: str) -> None:
    """找不到預期的 table：過去球季代表版面改了（WARNING），當季以後視為尚未發布（INFO）。"""
    if year < SEASON_YEAR:
        logger.warning("TJStats %s table missing for past season %s (layout changed?): %s",
                       what, year, url)
    else:
        logger.info("TJStats %s not published yet for %s", what, year)

# site_builder.levels Tier key → (pf_level query value, league-constants Level
# code) on tjstats.ca. The two pages spell the same levels differently
# (hi_a/lo_a vs hi-a/lo-a), hence one table with both spellings.  This lives
# with the scraper rather than in constants.py because it is nothing but this
# one site's URL/table spelling — and because league_constant/ imports this
# module, so the reverse direction would be circular.
TJSTATS_LEVEL_PARAMS = {
    "MLB": ("mlb", "mlb"),
    "AAA": ("aaa", "aaa"),
    "AA": ("aa", "aa"),
    "A+": ("hi_a", "hi-a"),
    "A": ("lo_a", "lo-a"),
}
PF_LEVEL_PARAM = {k: v[0] for k, v in TJSTATS_LEVEL_PARAMS.items()}
LC_LEVEL_CODE = {k: v[1] for k, v in TJSTATS_LEVEL_PARAMS.items()}


def fetch_park_factors(level: str, year: int) -> dict[str, dict]:
    """Fetch TJStats park factors for one tier/year.

    Returns {team_name: {"pf_final": float, "league": str}}. Returns {} on
    an unknown level or any fetch/parse failure.
    """
    param = PF_LEVEL_PARAM.get(level)
    if not param:
        return {}

    url = f"https://tjstats.ca/park-factors/?pf_level={param}&pf_season={year}"
    try:
        html = get_text(url)
    except FetchError as exc:
        logger.warning(
            "TJStats park factors fetch failed for %s %s: %s", level, year, describe_exc(exc)
        )
        return {}

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select("table.tjs-guts")
    if not tables:
        _log_missing_table(year, f"park factors ({level})", url)
        return {}

    rows = tables[0].select("tbody tr")
    result = {}
    for tr in rows:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 9:
            continue
        team_name, league = cells[0], cells[1]
        try:
            pf_final = float(cells[8])
        except ValueError:
            continue
        result[team_name] = {"pf_final": pf_final, "league": league}
    if rows and not result:
        logger.warning(
            "TJStats park factors: %d row(s) for %s %s but none parsed (columns changed?): %s",
            len(rows), level, year, url,
        )
    return result


def fetch_league_constants(year: int) -> dict[tuple[str, str], dict]:
    """Fetch TJStats league constants for every level/league in one year.

    Returns {(level_code, league_name): {"lg_woba": float, "lg_r_pa": float}}.
    level_code matches LC_LEVEL_CODE's values above (mlb/aaa/aa/hi-a/lo-a).
    Returns {} on any fetch/parse failure.
    """
    url = f"https://tjstats.ca/park-factors/?lc_season={year}"
    try:
        html = get_text(url)
    except FetchError as exc:
        logger.warning(
            "TJStats league constants fetch failed for %s: %s", year, describe_exc(exc)
        )
        return {}

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select("table.tjs-guts")
    # 同一頁第二張 table.tjs-guts 才是 league constants，第一張是 park factors
    if len(tables) < 2:
        _log_missing_table(year, "league constants", url)
        return {}

    rows = tables[1].select("tbody tr")
    result = {}
    for tr in rows:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 7:
            continue
        level_code, league = cells[0], cells[1]
        try:
            lg_woba = float(cells[3])
            lg_r_pa = float(cells[5])
        except ValueError:
            continue
        result[(level_code, league)] = {"lg_woba": lg_woba, "lg_r_pa": lg_r_pa}
    if rows and not result:
        logger.warning(
            "TJStats league constants: %d row(s) for %s but none parsed (columns changed?): %s",
            len(rows), year, url,
        )
    return result

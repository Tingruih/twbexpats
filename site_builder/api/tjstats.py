"""TJStats (tjstats.ca) park factors and league constants — HTML scrape.

Both fetches are best-effort enhancements for wRC+ computation, not core
data, so failures must never raise; they log a warning and return {}.
"""

import logging

from bs4 import BeautifulSoup

from .client import get_text

logger = logging.getLogger(__name__)

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
    except Exception as exc:
        print(f"  WARNING: failed to fetch TJStats park factors for {level} {year}: {exc}")
        return {}

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select("table.tjs-guts")
    if not tables:
        return {}

    result = {}
    for tr in tables[0].select("tbody tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 9:
            continue
        team_name, league = cells[0], cells[1]
        try:
            pf_final = float(cells[8])
        except ValueError:
            continue
        result[team_name] = {"pf_final": pf_final, "league": league}
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
    except Exception as exc:
        print(f"  WARNING: failed to fetch TJStats league constants for {year}: {exc}")
        return {}

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select("table.tjs-guts")
    if len(tables) < 2:
        return {}

    result = {}
    for tr in tables[1].select("tbody tr"):
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
    return result

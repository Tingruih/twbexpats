"""SQLite-backed cache for MLB-Stats-API-derived FIP constants.

Unlike ``tjstats_cache.py`` (external source publishes final numbers once a
season is over, then they never change), the league pitching totals used
here keep accumulating all season long for the year in progress. So the
caching policy differs from the TJStats one:

  - year <  SEASON_YEAR (season already finished): cache forever, same as
    tjstats_cache — read the cache first, live-fetch only on a miss.
  - year >= SEASON_YEAR (season in progress): always live-fetch and upsert.
    The cached row for that year is only a snapshot of the most recent
    fetch, never treated as final.

Pass ``force_refresh=True`` to bypass the cache for a *past* year too (e.g.
if MLB Stats API ever corrects historical numbers) — wired to the same
``--update-constants`` build.py flag used for the TJStats cache.
"""

import sqlite3

from ..api.league_stats import fetch_team_league_map, fetch_team_pitching_totals
from ..constants import SEASON_YEAR
from ..levels import resolve_tier
from ..stats.advanced.fip import compute_league_fip_constant

_TOTAL_FIELDS = ("hr", "bb", "hbp", "k", "earned_runs", "outs")


def _load(conn: sqlite3.Connection, sport_level: str, year: int) -> dict[str, float]:
    rows = conn.execute(
        "SELECT league_name, fip_constant FROM league_fip_constants "
        "WHERE year = ? AND sport_level = ?",
        (year, sport_level),
    ).fetchall()
    return dict(rows)


def _save(
    conn: sqlite3.Connection, sport_level: str, year: int, data: dict[str, float]
) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO league_fip_constants "
        "(year, sport_level, league_name, fip_constant) VALUES (?, ?, ?, ?)",
        [(year, sport_level, league_name, c) for league_name, c in data.items()],
    )
    conn.commit()


def _fetch_and_compute(sport_level: str, year: int) -> dict[str, float]:
    """Live-fetch team pitching totals for *sport_level*/*year*, grouped by league.

    Returns {league_name: fip_constant}, plus a "" entry holding the
    whole-level aggregate (used as a fallback when a team's league can't be
    resolved, or a player's own league doesn't have its own entry). Empty
    dict on any fetch failure, an unknown level, or a not-yet-started season.
    """
    tier = resolve_tier(sport_level)
    if tier is None or not tier.sport_ids:
        return {}
    sport_id = tier.sport_ids[0]

    team_totals = fetch_team_pitching_totals(sport_id, year)
    if not team_totals:
        return {}
    league_map = fetch_team_league_map(sport_id, year)

    by_league: dict[str, dict] = {}
    level_wide = dict.fromkeys(_TOTAL_FIELDS, 0)
    for team in team_totals:
        for field in _TOTAL_FIELDS:
            level_wide[field] += team[field]

        league_name = league_map.get(team["team_id"])
        if not league_name:
            continue  # unmapped team still counts toward the level-wide fallback only
        bucket = by_league.setdefault(league_name, dict.fromkeys(_TOTAL_FIELDS, 0))
        for field in _TOTAL_FIELDS:
            bucket[field] += team[field]

    result = {}
    for league_name, totals in by_league.items():
        c = compute_league_fip_constant(totals)
        if c is not None:
            result[league_name] = c
    level_c = compute_league_fip_constant(level_wide)
    if level_c is not None:
        result[""] = level_c
    return result


def get_fip_constants(
    conn: sqlite3.Connection, sport_level: str, year: int, force_refresh: bool = False
) -> dict[str, float]:
    """FIP constants for one (sport_level, year), cached in SQLite.

    Returns {league_name: fip_constant}; "" is the whole-level aggregate,
    used as a fallback when a player's actual league entry is missing.
    Empty dict if nothing could be computed (caller should fall back to
    ``constants.FIP_DEFAULT_CONSTANT``).
    """
    in_progress = year >= SEASON_YEAR
    if not force_refresh and not in_progress:
        cached = _load(conn, sport_level, year)
        if cached:
            return cached

    fetched = _fetch_and_compute(sport_level, year)
    if fetched:
        _save(conn, sport_level, year, fetched)
        return fetched

    # Fetch failed/empty (e.g. season hasn't started yet) — fall back to
    # whatever is already cached, if anything.
    return _load(conn, sport_level, year)

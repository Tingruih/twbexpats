"""FIP constants and league ERA from MLB Stats API team pitching totals, cached in SQLite.

Both numbers come out of the same ``compute_league_fip_constant()`` call over
the same team totals (see ``stats.advanced.fip``), so there is exactly one
fetch and one cached row serving both the per-pitcher FIP constant and
xWPCT's league-ERA denominator — not two of each.

Caching follows ``RefreshPolicy.ACCUMULATES_IN_SEASON`` (see ``policy.py``):
a finished season's row is final and reused forever, while the season in
progress is re-fetched every run because its league totals keep growing.
Pass ``force_refresh=True`` (wired to build.py's ``--update-constants``) to
bypass the cache for a finished season too, e.g. if MLB Stats API ever
corrects historical numbers.
"""

import sqlite3

from ..api.league_stats import fetch_team_league_map, fetch_team_pitching_totals
from ..levels import resolve_tier
from ..stats.advanced.fip import LeagueFipConstant, compute_league_fip_constant
from .policy import RefreshPolicy, should_use_cache

_POLICY = RefreshPolicy.ACCUMULATES_IN_SEASON
_TOTAL_FIELDS = ("hr", "bb", "hbp", "k", "earned_runs", "outs")


def _load(
    conn: sqlite3.Connection, level: str, year: int
) -> dict[str, LeagueFipConstant]:
    """Read the cached constants for one slice.

    *level* is a ``levels.Tier`` key; it is stored in the (older-named)
    ``sport_level`` column. Rows with ``lg_era = 0`` are skipped: that is the
    ALTER TABLE default left on rows written before lg_era existed, and
    treating them as a miss is what makes them self-heal on the next fetch.
    """
    rows = conn.execute(
        "SELECT league_name, fip_constant, lg_era FROM league_fip_constants "
        "WHERE year = ? AND sport_level = ? AND lg_era > 0",
        (year, level),
    ).fetchall()
    return {
        league_name: LeagueFipConstant(fip_constant=fip_constant, lg_era=lg_era)
        for league_name, fip_constant, lg_era in rows
    }


def _save(
    conn: sqlite3.Connection,
    level: str,
    year: int,
    data: dict[str, LeagueFipConstant],
) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO league_fip_constants "
        "(year, sport_level, league_name, fip_constant, lg_era) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (year, level, league_name, entry.fip_constant, entry.lg_era)
            for league_name, entry in data.items()
        ],
    )
    conn.commit()


def _fetch_and_compute(level: str, year: int) -> dict[str, LeagueFipConstant]:
    """Live-fetch team pitching totals for *level*/*year*, grouped by league.

    Returns {league_name: LeagueFipConstant}, plus a "" entry holding the
    whole-level aggregate. The "" entry serves two purposes: it is the
    fallback FIP constant when a team's league can't be resolved or has no
    entry of its own, and its ``lg_era`` is the denominator every xWPCT uses
    regardless of league (xWPCT is measured against the level-wide average,
    not one league inside it). Empty dict on any fetch failure, an unknown
    level, or a not-yet-started season.
    """
    tier = resolve_tier(level)
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

    result: dict[str, LeagueFipConstant] = {}
    for league_name, totals in by_league.items():
        c = compute_league_fip_constant(totals)
        if c is not None:
            result[league_name] = c
    level_c = compute_league_fip_constant(level_wide)
    if level_c is not None:
        result[""] = level_c
    return result


def get_pitching_constants(
    conn: sqlite3.Connection,
    level: str,
    year: int,
    *,
    force_refresh: bool = False,
) -> dict[str, LeagueFipConstant]:
    """FIP constant + league ERA for one (level, year), cached in SQLite.

    Returns {league_name: LeagueFipConstant(fip_constant, lg_era)}; "" is the
    whole-level aggregate. Empty dict if nothing could be computed — the
    caller then falls back to ``stats.advanced.fip.FIP_DEFAULT_CONSTANT`` for
    FIP and treats xWPCT as unavailable.

    Use ``PitchingConstants`` instead when resolving more than one slice in a
    run; this function re-reads (and for the season in progress, re-fetches)
    on every call.
    """
    if should_use_cache(year, policy=_POLICY, force_refresh=force_refresh):
        cached = _load(conn, level, year)
        if cached:
            return cached

    fetched = _fetch_and_compute(level, year)
    if fetched:
        _save(conn, level, year, fetched)
        return fetched

    # Fetch failed/empty (e.g. season hasn't started yet) — fall back to
    # whatever is already cached, if anything.
    return _load(conn, level, year)


class PitchingConstants:
    """Per-run resolver memoizing each (level, year) across a whole sync run.

    The in-memory memo is not an optimisation for the finished seasons (those
    hit the SQLite cache anyway) — it is what stops the season in progress,
    whose policy is to re-fetch on every call, from re-fetching once per
    player.
    """

    def __init__(self, conn: sqlite3.Connection, *, force_refresh: bool = False):
        self._conn = conn
        self._force_refresh = force_refresh
        self._cache: dict[tuple[str, int], dict[str, LeagueFipConstant]] = {}

    def for_level(self, level: str, year: int) -> dict[str, LeagueFipConstant]:
        """Constants for one slice; same return shape as get_pitching_constants."""
        key = (level, year)
        if key not in self._cache:
            self._cache[key] = get_pitching_constants(
                self._conn, level, year, force_refresh=self._force_refresh
            )
        return self._cache[key]

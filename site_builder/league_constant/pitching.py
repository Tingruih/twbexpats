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

A finished season whose totals can't produce a constant (pre-2005 MiLB has no
earned runs) writes no cache row, so it is additionally recorded in
``season_fetches`` (``db/season_fetches.py``) once fetched successfully;
otherwise every run would re-request those slices only to get nothing again.
"""

import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, Optional

from ..api import FetchError
from ..api.league_stats import fetch_team_league_map, fetch_team_pitching_totals
from ..constants import GAME_FETCH_WORKERS
from ..db.season_fetches import FIP_CONSTANTS, load_fetched, mark_fetched
from ..levels import resolve_tier
from ..stats.advanced.fip import LeagueFipConstant, compute_league_fip_constant
from ..util.log import describe_exc
from .policy import RefreshPolicy, should_use_cache

logger = logging.getLogger(__name__)

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


def _fetch_and_compute(level: str, year: int) -> Optional[dict[str, LeagueFipConstant]]:
    """Live-fetch team pitching totals for *level*/*year*, grouped by league.

    Returns {league_name: LeagueFipConstant}, plus a "" entry holding the
    whole-level aggregate. The "" entry serves two purposes: it is the
    fallback FIP constant when a team's league can't be resolved or has no
    entry of its own, and its ``lg_era`` is the denominator every xWPCT uses
    regardless of league (xWPCT is measured against the level-wide average,
    not one league inside it). Empty dict when the answer is genuinely "no
    constant": an unknown level, a not-yet-started season, or totals without
    earned runs. ``None`` on a fetch failure, so the caller can tell "retry
    next run" apart from "nothing to find" (only the latter is recorded in
    ``season_fetches``).

    Either request failing yields None rather than a partial result: with the
    totals but no league map every team would be "unmapped", only the ""
    entry would come back, and it would be cached for a finished season
    forever -- per-league FIP constants silently gone.
    """
    tier = resolve_tier(level)
    # 未知層級，或該層級沒有對應的 sportId
    if tier is None or not tier.sport_ids:
        return {}
    sport_id = tier.sport_ids[0]

    try:
        team_totals = fetch_team_pitching_totals(sport_id, year)
        # 球季尚未開打，沒有任何球隊有投球局數
        if not team_totals:
            return {}
        league_map = fetch_team_league_map(sport_id, year)
    except FetchError as e:
        logger.warning(
            "FIP constant inputs fetch failed for %s %s (sportId=%s); "
            "falling back to cached value if any: %s",
            level, year, sport_id, describe_exc(e),
        )
        return None

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


def _from_cache(
    conn: sqlite3.Connection,
    level: str,
    year: int,
    *,
    force_refresh: bool,
    fetched: set[tuple[str, int]],
) -> Optional[dict[str, LeagueFipConstant]]:
    """Resolve a slice without the network; ``None`` means it must be fetched."""
    if not should_use_cache(year, policy=_POLICY, force_refresh=force_refresh):
        return None
    cached = _load(conn, level, year)
    if cached:
        return cached
    # 過去球季成功抓過但解不出常數（2005 年以前的 MiLB），不必再抓
    if (level, year) in fetched:
        return {}
    return None


def _store(
    conn: sqlite3.Connection,
    level: str,
    year: int,
    fetched: Optional[dict[str, LeagueFipConstant]],
) -> dict[str, LeagueFipConstant]:
    """Persist one fetch result and return what the slice resolves to."""
    # 抓取失敗：不登記，下次執行重試
    if fetched is None:
        return _load(conn, level, year)
    if fetched:
        _save(conn, level, year, fetched)
        return fetched
    mark_fetched(conn.cursor(), FIP_CONSTANTS, level, [year])
    conn.commit()
    # 沒有常數（例如球季尚未開打）：退回既有快取，沒有就是 {}
    return _load(conn, level, year)


def get_pitching_constants(
    conn: sqlite3.Connection,
    level: str,
    year: int,
    *,
    force_refresh: bool = False,
) -> dict[str, LeagueFipConstant]:
    """FIP constant + league ERA for one (level, year), cached in SQLite.

    Returns {league_name: LeagueFipConstant(fip_constant, lg_era)}; "" is the
    whole-level aggregate. Empty dict if nothing could be computed (e.g.
    pre-2005 MiLB, where the API has no earned runs) — the caller then treats
    both FIP and xWPCT as unavailable.

    Use ``PitchingConstants`` instead when resolving more than one slice in a
    run; this function re-reads (and for the season in progress, re-fetches)
    on every call.
    """
    return PitchingConstants(conn, force_refresh=force_refresh).for_level(level, year)


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
        self._fetched = load_fetched(conn.cursor(), FIP_CONSTANTS)

    def prefetch(self, slices: Iterable[tuple[str, int]]) -> None:
        """Resolve many (level, year) slices at once, fetching the misses in parallel.

        Only the HTTP requests run in worker threads; every SQLite read/write
        stays on the calling thread (a sqlite3 connection is bound to the
        thread that created it).
        """
        to_fetch = []
        for key in sorted(set(slices) - self._cache.keys()):
            hit = _from_cache(
                self._conn, *key,
                force_refresh=self._force_refresh, fetched=self._fetched,
            )
            if hit is None:
                to_fetch.append(key)
            else:
                self._cache[key] = hit
        if not to_fetch:
            return
        logger.info("FIP constants: fetching %d level-season slice(s) ...", len(to_fetch))
        with ThreadPoolExecutor(max_workers=GAME_FETCH_WORKERS) as executor:
            results = list(executor.map(lambda key: _fetch_and_compute(*key), to_fetch))
        for key, result in zip(to_fetch, results):
            self._cache[key] = _store(self._conn, *key, result)

    def for_level(self, level: str, year: int) -> dict[str, LeagueFipConstant]:
        """Constants for one slice; same return shape as get_pitching_constants."""
        key = (level, year)
        if key not in self._cache:
            self.prefetch([key])
        return self._cache[key]

"""tjstats.ca park factors and league constants, joined per team, cached in SQLite.

wRC+ needs three numbers for one player-season: the park factor of the club
they played the most for, plus that club's league lg_wOBA and lg_R/PA. Those
arrive from two different tjstats.ca tables with two different key shapes, so
this module joins them here and hands the caller a single per-club record —
``stats.advanced.wrc_plus`` never sees a level_code or a league name it has
to translate.

Caching follows ``RefreshPolicy.FINAL_ONCE_PUBLISHED`` (see ``policy.py``):
a published slice never changes, so once cached it is reused forever. A fetch
that comes back empty (TJStats hasn't published the season yet) is never
written, so the next build retries the live fetch automatically. Pass
``force_refresh=True`` (build.py's ``--update-constants``) to bypass the
cache and overwrite it unconditionally.
"""

import sqlite3
from typing import NamedTuple

from ..api.tjstats import (
    LC_LEVEL_CODE,
    TJSTATS_LEVEL_PARAMS,
    fetch_league_constants,
    fetch_park_factors,
)
from .policy import RefreshPolicy, should_use_cache

_POLICY = RefreshPolicy.FINAL_ONCE_PUBLISHED

# Seasons before this have no TJStats coverage, so wRC+ is never computed.
_MIN_WRC_YEAR = 2021
# The levels TJStats publishes for — derived from the scraper's own spelling
# table so the two can never drift apart.
_WRC_LEVELS = tuple(TJSTATS_LEVEL_PARAMS)


class BattingConstant(NamedTuple):
    """One club's wRC+ inputs for a (level, year).

    ``pf_final`` and ``league`` come from the park-factor table; ``lg_woba``
    and ``lg_r_pa`` come from the league-constants table, joined on
    ``league``. All four are needed together by ``compute_wrc_plus``.
    """

    pf_final: float
    league: str
    lg_woba: float
    lg_r_pa: float


def publishes_constants(level: str, year: int) -> bool:
    """Whether TJStats publishes constants for this level/year at all.

    Callers use this for display decisions (whether a wRC+ column can exist
    for a row); the resolver applies it itself, so a lookup for an uncovered
    slice simply comes back empty rather than raising.
    """
    return year >= _MIN_WRC_YEAR and level in _WRC_LEVELS


def _load_park_factors(
    conn: sqlite3.Connection, level: str, year: int
) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT team_name, pf_final, league FROM tjstats_park_factors "
        "WHERE year = ? AND level = ?",
        (year, level),
    ).fetchall()
    return {
        team_name: {"pf_final": pf_final, "league": league}
        for team_name, pf_final, league in rows
    }


def _save_park_factors(
    conn: sqlite3.Connection, level: str, year: int, data: dict[str, dict]
) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO tjstats_park_factors "
        "(year, level, team_name, pf_final, league) VALUES (?, ?, ?, ?, ?)",
        [
            (year, level, team_name, entry["pf_final"], entry["league"])
            for team_name, entry in data.items()
        ],
    )
    conn.commit()


def _get_park_factors(
    conn: sqlite3.Connection, level: str, year: int, *, force_refresh: bool
) -> dict[str, dict]:
    if should_use_cache(year, policy=_POLICY, force_refresh=force_refresh):
        cached = _load_park_factors(conn, level, year)
        if cached:
            return cached

    fetched = fetch_park_factors(level, year)
    if fetched:
        _save_park_factors(conn, level, year, fetched)
        return fetched

    # Fetch failed or came back empty (e.g. a not-yet-published season) —
    # fall back to whatever is already cached, if anything.
    return _load_park_factors(conn, level, year)


def _load_league_constants(
    conn: sqlite3.Connection, year: int
) -> dict[tuple[str, str], dict]:
    rows = conn.execute(
        "SELECT level_code, league, lg_woba, lg_r_pa FROM tjstats_league_constants "
        "WHERE year = ?",
        (year,),
    ).fetchall()
    return {
        (level_code, league): {"lg_woba": lg_woba, "lg_r_pa": lg_r_pa}
        for level_code, league, lg_woba, lg_r_pa in rows
    }


def _save_league_constants(
    conn: sqlite3.Connection, year: int, data: dict[tuple[str, str], dict]
) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO tjstats_league_constants "
        "(year, level_code, league, lg_woba, lg_r_pa) VALUES (?, ?, ?, ?, ?)",
        [
            (year, level_code, league, entry["lg_woba"], entry["lg_r_pa"])
            for (level_code, league), entry in data.items()
        ],
    )
    conn.commit()


def _get_league_constants(
    conn: sqlite3.Connection, year: int, *, force_refresh: bool
) -> dict[tuple[str, str], dict]:
    if should_use_cache(year, policy=_POLICY, force_refresh=force_refresh):
        cached = _load_league_constants(conn, year)
        if cached:
            return cached

    fetched = fetch_league_constants(year)
    if fetched:
        _save_league_constants(conn, year, fetched)
        return fetched

    return _load_league_constants(conn, year)


def _join(
    level: str,
    pf_entries: dict[str, dict],
    lc_entries: dict[tuple[str, str], dict],
) -> dict[str, BattingConstant]:
    """Join per-club park factors to their league's constants.

    A club whose league has no published constants is simply absent from the
    result. Callers already treat a missing club as "skip this player-season"
    (that is how a missing park factor has always behaved), so absence needs
    no separate signal.
    """
    level_code = LC_LEVEL_CODE.get(level)
    if level_code is None:
        return {}
    out: dict[str, BattingConstant] = {}
    for team_name, pf in pf_entries.items():
        lc = lc_entries.get((level_code, pf["league"]))
        if lc is None:
            continue
        out[team_name] = BattingConstant(
            pf_final=pf["pf_final"],
            league=pf["league"],
            lg_woba=lc["lg_woba"],
            lg_r_pa=lc["lg_r_pa"],
        )
    return out


class BattingConstants:
    """Per-run resolver for the wRC+ inputs, memoized across a whole build.

    It holds two caches on purpose, and that is the reason this class exists
    rather than a bare function plus a caller-side memo: park factors come
    back per (level, year), but ``fetch_league_constants`` returns a whole
    year across every level in a single request. A caller memoizing only per
    (level, year) would re-scrape that one page once per level whenever the
    cache is bypassed.
    """

    def __init__(self, conn: sqlite3.Connection, *, force_refresh: bool = False):
        self._conn = conn
        self._force_refresh = force_refresh
        self._pf_cache: dict[tuple[str, int], dict[str, dict]] = {}
        self._lc_cache: dict[int, dict[tuple[str, str], dict]] = {}

    def for_level(self, level: str, year: int) -> dict[str, BattingConstant]:
        """{team_name: BattingConstant} for one slice; {} when uncovered."""
        if not publishes_constants(level, year):
            return {}

        pf_key = (level, year)
        if pf_key not in self._pf_cache:
            self._pf_cache[pf_key] = _get_park_factors(
                self._conn, level, year, force_refresh=self._force_refresh
            )
        if year not in self._lc_cache:
            self._lc_cache[year] = _get_league_constants(
                self._conn, year, force_refresh=self._force_refresh
            )
        return _join(level, self._pf_cache[pf_key], self._lc_cache[year])


def get_batting_constants(
    conn: sqlite3.Connection,
    level: str,
    year: int,
    *,
    force_refresh: bool = False,
) -> dict[str, BattingConstant]:
    """One-shot equivalent of ``BattingConstants(conn, ...).for_level(...)``.

    Use the resolver instead whenever a run looks up more than one slice.
    """
    return BattingConstants(conn, force_refresh=force_refresh).for_level(level, year)

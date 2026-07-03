"""SQLite-backed cache for TJStats park factors & league constants.

Completed seasons never change on tjstats.ca, so once a (year, level) or
(year) slice is cached it is reused forever. The current in-progress season
is cached the same way, but a fetch that comes back empty (TJStats hasn't
published the new season yet) is never written to the cache — so the next
build retries the live fetch automatically until it succeeds. Pass
``force_refresh=True`` to bypass the cache and overwrite it unconditionally
(used by the `--update-constants` build.py flag for correcting stale
mid-season numbers).
"""

import sqlite3

from ..api.tjstats import fetch_league_constants, fetch_park_factors


def _load_park_factors(conn: sqlite3.Connection, level: str, year: int) -> dict[str, dict]:
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


def get_park_factors(
    conn: sqlite3.Connection, level: str, year: int, force_refresh: bool = False
) -> dict[str, dict]:
    """Park factors for one tier/year, cached in SQLite (see module docstring)."""
    if not force_refresh:
        cached = _load_park_factors(conn, level, year)
        if cached:
            return cached

    fetched = fetch_park_factors(level, year)
    if fetched:
        _save_park_factors(conn, level, year, fetched)
        return fetched

    # Fetch failed or came back empty (e.g. force_refresh on a not-yet-published
    # season) — fall back to whatever is already cached, if anything.
    return _load_park_factors(conn, level, year)


def _load_league_constants(conn: sqlite3.Connection, year: int) -> dict[tuple[str, str], dict]:
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


def get_league_constants(
    conn: sqlite3.Connection, year: int, force_refresh: bool = False
) -> dict[tuple[str, str], dict]:
    """League constants for one year, cached in SQLite (see module docstring)."""
    if not force_refresh:
        cached = _load_league_constants(conn, year)
        if cached:
            return cached

    fetched = fetch_league_constants(year)
    if fetched:
        _save_league_constants(conn, year, fetched)
        return fetched

    return _load_league_constants(conn, year)

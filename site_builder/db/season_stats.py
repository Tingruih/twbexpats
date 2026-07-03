"""season_stats row load/save helpers."""

import sqlite3

from ..util.json import dumps_json, loads_json


def load_season_row(cur, mlb_id: int, year: int, team_name: str) -> dict:
    cur.execute(
        "SELECT league_name, sport_level, stat_json, fielding_json "
        "FROM season_stats WHERE player_mlb_id = ? AND year = ? AND team_name = ?",
        (mlb_id, year, team_name),
    )
    row = cur.fetchone()
    if not row:
        return {
            "league_name": "",
            "sport_level": "",
            "stat_json": {},
            "fielding_json": [],
        }
    return {
        "league_name": row[0] or "",
        "sport_level": row[1] or "",
        "stat_json": loads_json(row[2], {}),
        "fielding_json": loads_json(row[3], []),
    }


def save_season_row(
    cur,
    mlb_id,
    year,
    team_name,
    league_name,
    sport_level,
    stat_json,
    fielding_json,
):
    cur.execute(
        "INSERT INTO season_stats "
        "(player_mlb_id, year, team_name, league_name, sport_level, stat_json, fielding_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(player_mlb_id, year, team_name) DO UPDATE SET "
        " league_name=excluded.league_name, sport_level=excluded.sport_level, "
        " stat_json=excluded.stat_json, fielding_json=excluded.fielding_json",
        (
            mlb_id,
            year,
            team_name,
            league_name or "",
            sport_level or "",
            dumps_json(stat_json),
            dumps_json(fielding_json),
        ),
    )


def players_with_existing_stats(conn: sqlite3.Connection) -> set[int]:
    """Return mlb_ids that already have season_stats rows.

    Used to detect players being synced for the first time, so their
    history can be fully backfilled even during a fetch_all_years=False
    (update/refresh) run.
    """
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT player_mlb_id FROM season_stats")
    return {row[0] for row in cur.fetchall()}

"""players-table queries shared across pipelines."""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def warn_orphaned_players(conn: sqlite3.Connection, roster_ids: set[int]):
    """Log a warning for any players in the DB that are not in the current roster.

    These orphans accumulate when a player's MLB ID is corrected in roster.json
    or when a player is removed from the roster without cleaning the database.
    They won't appear on the built site (the builder filters by roster) but they
    do occupy space in the database and can cause confusion.
    """
    cur = conn.cursor()
    cur.execute("SELECT mlb_id, name_en, name_tw FROM players ORDER BY mlb_id")
    orphans = [
        (mlb_id, name_en, name_tw)
        for mlb_id, name_en, name_tw in cur.fetchall()
        if mlb_id not in roster_ids
    ]
    if not orphans:
        return
    id_list = ",".join(str(i) for i in roster_ids)
    lines = [f"{len(orphans)} DB player(s) not in current roster (won't appear on site):"]
    for mlb_id, name_en, name_tw in orphans:
        label = f"{name_tw} / {name_en}" if name_tw else name_en
        lines.append(f"    {mlb_id}  {label}")
    lines.append(
        "  To remove orphans, run:\n"
        "    sqlite3 data/tracker.sqlite3 "
        f"\"DELETE FROM game_logs WHERE player_mlb_id NOT IN ({id_list}); "
        f"DELETE FROM season_stats WHERE player_mlb_id NOT IN ({id_list}); "
        f"DELETE FROM players WHERE mlb_id NOT IN ({id_list});\""
    )
    logger.warning("\n".join(lines))


def get_cached_is_active(cur) -> dict[int, bool]:
    """Return {mlb_id: is_active} as cached from the last profile fetch."""
    cur.execute("SELECT mlb_id, is_active FROM players")
    return {row[0]: bool(row[1]) for row in cur.fetchall()}


def get_incomplete_history_ids(cur) -> set[int]:
    """全歷史同步有請求失敗、下次要重做一次全歷史抓取的球員（``history_synced = 0``）。"""
    cur.execute("SELECT mlb_id FROM players WHERE history_synced = 0")
    return {row[0] for row in cur.fetchall()}

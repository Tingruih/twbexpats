"""players-table queries shared across pipelines."""

import sqlite3


def warn_orphaned_players(conn: sqlite3.Connection, roster_ids: set[int]):
    """Print a warning for any players in the DB that are not in the current roster.

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
    print(f"  WARNING: {len(orphans)} DB player(s) not in current roster (won't appear on site):")
    for mlb_id, name_en, name_tw in orphans:
        label = f"{name_tw} / {name_en}" if name_tw else name_en
        print(f"    {mlb_id}  {label}")
    print(
        "  To remove orphans, run:\n"
        "    sqlite3 data/tracker.sqlite3 "
        "\"DELETE FROM game_logs WHERE player_mlb_id NOT IN "
        f"({','.join(str(i) for i in roster_ids)}); "
        "DELETE FROM season_stats WHERE player_mlb_id NOT IN "
        f"({','.join(str(i) for i in roster_ids)}); "
        "DELETE FROM players WHERE mlb_id NOT IN "
        f"({','.join(str(i) for i in roster_ids)});\""
    )


def get_positions(cur, mlb_ids) -> dict[int, str]:
    """Return {mlb_id: position} for the given players (empty string if unknown)."""
    positions: dict[int, str] = {}
    for mlb_id in mlb_ids:
        cur.execute("SELECT position FROM players WHERE mlb_id = ?", (mlb_id,))
        row = cur.fetchone()
        positions[mlb_id] = (row[0] if row else "") or ""
    return positions


def get_cached_is_active(cur) -> dict[int, bool]:
    """Return {mlb_id: is_active} as cached from the last profile fetch."""
    cur.execute("SELECT mlb_id, is_active FROM players")
    return {row[0]: bool(row[1]) for row in cur.fetchall()}

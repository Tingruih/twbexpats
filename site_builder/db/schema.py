"""Database schema creation and forward migrations."""

import sqlite3


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mlb_id INTEGER NOT NULL UNIQUE,
            name_en TEXT NOT NULL,
            name_tw TEXT NOT NULL DEFAULT '',
            team TEXT NOT NULL DEFAULT 'N/A',
            level TEXT NOT NULL DEFAULT 'Minors',
            position TEXT NOT NULL DEFAULT '',
            height TEXT NOT NULL DEFAULT '',
            weight INTEGER,
            birth_date TEXT,
            birth_city TEXT NOT NULL DEFAULT '',
            birth_country TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            bat_side TEXT NOT NULL DEFAULT '',
            pitch_hand TEXT NOT NULL DEFAULT '',
            latest_transaction TEXT NOT NULL DEFAULT '',
            roster_status TEXT NOT NULL DEFAULT '',
            roster_status_code TEXT NOT NULL DEFAULT '',
            roster_is_active INTEGER NOT NULL DEFAULT 0,
            team_id INTEGER,
            transactions_json TEXT NOT NULL DEFAULT '[]',
            next_game_json TEXT NOT NULL DEFAULT '{}',
            next_game_updated_at TEXT,
            next_game_for_season INTEGER
        );

        CREATE TABLE IF NOT EXISTS season_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_mlb_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            league_name TEXT NOT NULL DEFAULT '',
            sport_level TEXT NOT NULL DEFAULT '',
            stat_json TEXT NOT NULL DEFAULT '{}',
            fielding_json TEXT NOT NULL DEFAULT '[]',
            UNIQUE(player_mlb_id, year, team_name)
        );

        CREATE TABLE IF NOT EXISTS game_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_mlb_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            game_id INTEGER NOT NULL,
            opponent TEXT NOT NULL,
            is_home INTEGER,
            stats_json TEXT NOT NULL DEFAULT '{}',
            pitches_json TEXT NOT NULL DEFAULT '[]',
            UNIQUE(player_mlb_id, game_id)
        );

        CREATE TABLE IF NOT EXISTS playbyplay_processed (
            game_pk INTEGER PRIMARY KEY,
            processed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tjstats_park_factors (
            year INTEGER NOT NULL,
            level TEXT NOT NULL,
            team_name TEXT NOT NULL,
            pf_final REAL NOT NULL,
            league TEXT NOT NULL,
            UNIQUE(year, level, team_name)
        );

        CREATE TABLE IF NOT EXISTS tjstats_league_constants (
            year INTEGER NOT NULL,
            level_code TEXT NOT NULL,
            league TEXT NOT NULL,
            lg_woba REAL NOT NULL,
            lg_r_pa REAL NOT NULL,
            UNIQUE(year, level_code, league)
        );

        CREATE TABLE IF NOT EXISTS league_fip_constants (
            year INTEGER NOT NULL,
            sport_level TEXT NOT NULL,
            league_name TEXT NOT NULL DEFAULT '',
            fip_constant REAL NOT NULL,
            UNIQUE(year, sport_level, league_name)
        );

        CREATE INDEX IF NOT EXISTS idx_season_stats_player_year
            ON season_stats(player_mlb_id, year);
        CREATE INDEX IF NOT EXISTS idx_game_logs_player_date
            ON game_logs(player_mlb_id, date);
    """)
    # Forward-migration: add pitches_json column if it does not yet exist
    # (needed for databases created before Statcast support).
    try:
        conn.execute("ALTER TABLE game_logs ADD COLUMN pitches_json TEXT NOT NULL DEFAULT '[]'")
    except sqlite3.OperationalError:
        pass  # column already exists
    # Forward-migration: add sport_level column to game_logs if it does not yet exist.
    try:
        conn.execute("ALTER TABLE game_logs ADD COLUMN sport_level TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already exists
    # Forward-migration: add roster_status_code/roster_is_active columns to players
    # if they do not yet exist (needed for richer status-pill classification).
    try:
        conn.execute("ALTER TABLE players ADD COLUMN roster_status_code TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        conn.execute("ALTER TABLE players ADD COLUMN roster_is_active INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # column already exists
    # Forward-migration: track whether hit_coord backfill has been attempted for this
    # player-game row. Prevents re-fetching games where the API genuinely has no
    # hit coordinates (pre-2019 MLB, low-level MiLB).
    try:
        conn.execute(
            "ALTER TABLE game_logs ADD COLUMN hit_coord_checked INTEGER NOT NULL DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()

"""Database schema creation and forward migrations."""

import sqlite3


def _add_column(conn: sqlite3.Connection, table: str, column_ddl: str) -> None:
    """``ALTER TABLE ... ADD COLUMN``，欄位已存在時略過。

    只吞 "duplicate column name"：sqlite3 把「資料庫被鎖住」「磁碟已滿」也歸成
    OperationalError，整類吞掉的話 migration 失敗會被當成欄位已存在。
    """
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_ddl}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e):
            raise


def _require_game_logs_role(conn: sqlite3.Connection) -> None:
    """既有 game_logs 沒有 ``role`` 欄位時中止。

    ``role`` 加入後唯一鍵變成 (球員, 比賽, 角色)，舊表的唯一鍵與逐球資料
    （依主要角色抽取、打席中換人歸屬錯誤）都無法就地轉換，必須刪除 DB 從頭重建
    （見 docs/db_schema.md §8）。在這裡擋下，避免 CI 拿舊 DB 靜默寫出錯誤資料；
    這是結構檢查，不做任何回補。
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(game_logs)")}
    if columns and "role" not in columns:
        raise SystemExit(
            "Error: game_logs has no 'role' column (database predates the "
            "batter/pitcher role split). Delete the database and rebuild it with "
            "'python build.py all'."
        )


def init_db(conn: sqlite3.Connection):
    _require_game_logs_role(conn)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mlb_id INTEGER NOT NULL UNIQUE,
            name_en TEXT NOT NULL,
            name_tw TEXT NOT NULL DEFAULT '',
            team TEXT NOT NULL DEFAULT 'N/A',
            level TEXT NOT NULL DEFAULT 'Minors',
            level_year INTEGER,
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
            next_game_for_season INTEGER,
            history_synced INTEGER NOT NULL DEFAULT 1
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
            game_type TEXT NOT NULL,
            -- positions.PITCHER / positions.BATTER：gameLog API 對該角色有 split 才有這一列，
            -- 同場又投又打是兩列；stats_json、pitches_json、events_json、pbp_version 都只屬於該角色
            role TEXT NOT NULL,
            sport_level TEXT NOT NULL DEFAULT '',
            stats_json TEXT NOT NULL DEFAULT '{}',
            pitches_json TEXT NOT NULL DEFAULT '[]',
            events_json TEXT NOT NULL DEFAULT '[]',
            -- 逐球資料的抽取版本（見 constants.PBP_EXTRACT_VERSION）；0 = 尚未抓到完賽資料
            pbp_version INTEGER NOT NULL DEFAULT 0,
            UNIQUE(player_mlb_id, game_id, role)
        );

        -- playbyplay_processed 以 game_pk 為單位記錄已抓過的比賽，球員後來才加入
        -- 名冊時會漏抓；改由 game_logs.pbp_version 逐 (球員, 比賽) 判斷後不再讀取
        -- （見 sync/statcast.py 的 _games_to_fetch）
        DROP TABLE IF EXISTS playbyplay_processed;

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
            lg_era REAL NOT NULL DEFAULT 0,
            UNIQUE(year, sport_level, league_name)
        );

        CREATE INDEX IF NOT EXISTS idx_season_stats_player_year
            ON season_stats(player_mlb_id, year);
        CREATE INDEX IF NOT EXISTS idx_game_logs_player_date
            ON game_logs(player_mlb_id, date);
    """)
    # Forward-migration: add roster_status_code/roster_is_active columns to players
    # if they do not yet exist (needed for richer status-pill classification).
    _add_column(conn, "players", "roster_status_code TEXT NOT NULL DEFAULT ''")
    _add_column(conn, "players", "roster_is_active INTEGER NOT NULL DEFAULT 0")
    # Forward-migration: add lg_era to league_fip_constants if it does not
    # yet exist. Existing rows keep the DEFAULT 0, which
    # league_constant.pitching._load() treats as a cache miss (its
    # `lg_era > 0` filter), so they self-heal via one live refetch — no
    # backfill script needed.
    _add_column(conn, "league_fip_constants", "lg_era REAL NOT NULL DEFAULT 0")
    # Forward-migration: 全歷史同步（首次同步或 sync 指令）是否每個請求都成功。
    # 既有列預設 1（視為已完成）；sync/players.py 在全歷史抓取有失敗時寫 0，
    # 下次 refresh 會再走一次全歷史抓取（見 _run_pipeline）。
    _add_column(conn, "players", "history_synced INTEGER NOT NULL DEFAULT 1")
    # Forward-migration: players.level 對應的球季，level_display() 靠它決定
    # 顯示 A+ 還是 A(Adv)。既有列為 NULL，下一次 sync/refresh 的
    # level/team UPDATE（sync/players.py）會寫入。
    _add_column(conn, "players", "level_year INTEGER")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS play_videos (
            game_pk INTEGER NOT NULL,
            play_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            mp4_url TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            UNIQUE(game_pk, play_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS game_content_processed (
            game_pk INTEGER PRIMARY KEY,
            processed_at TEXT NOT NULL,
            videos_found INTEGER NOT NULL DEFAULT 0
        )
    """)
    # 過去球季的逐年抓取登記（見 db/season_fetches.py）。新表不需回填：
    # 空表代表「全部沒抓過」，下一次執行會把每個過去球季各抓一次。
    conn.execute("""
        CREATE TABLE IF NOT EXISTS season_fetches (
            source TEXT NOT NULL,
            subject TEXT NOT NULL,
            year INTEGER NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (source, subject, year)
        )
    """)
    conn.commit()

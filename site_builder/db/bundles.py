"""Full player data-bundle loading for the site build."""

import datetime
import sqlite3

from ..constants import REGULAR_SEASON_GAME_TYPE
from ..levels import is_mlb
from ..positions import is_pitcher_position
from ..roster import categorize_roster_status
from ..stats.core.selectors import has_appearance
from ..util.dates import parse_date
from ..util.json import loads_json_dict, loads_json_list
from ..util.obj import Obj
from .season_stats import load_player_season_rows


def load_player_bundle(cur, player_row: sqlite3.Row):
    """Load a complete player data bundle from SQLite."""
    player = Obj(dict(player_row))
    player.transactions_json = loads_json_list(player.transactions_json)
    player.next_game_json = loads_json_dict(player.next_game_json)
    player.is_pitcher = is_pitcher_position(player.position)
    player.birth_date = parse_date(player.birth_date)

    today = datetime.date.today()
    if player.birth_date:
        player.age = (
            today.year
            - player.birth_date.year
            - (
                (today.month, today.day)
                < (player.birth_date.month, player.birth_date.day)
            )
        )
    else:
        player.age = None

    player.status_category = categorize_roster_status(
        player.roster_status_code, bool(player.roster_is_active), bool(player.is_active)
    )
    player.status_display = player.roster_status or ("Active" if player.is_active else "Inactive")

    # Season stats
    stats = load_player_season_rows(cur, player.mlb_id)
    player.latest_stat = stats[0] if stats else None
    player.available_years = sorted({s.year for s in stats}, reverse=True)
    # Drives headshot CDN tier selection: pick the level the player actually
    # appeared in during their most recent season with game action (not just
    # any level they've ever reached), so the tier tried first is the one
    # MLB most recently had a reason to update.
    latest_played = next((s for s in stats if has_appearance(s)), None)
    player.latest_level_is_mlb = bool(latest_played and is_mlb(latest_played.sport_level))

    # Game logs — pitches_json may not exist on older DBs (before Statcast support)
    has_pitches_col = False
    try:
        cur.execute("SELECT pitches_json FROM game_logs LIMIT 0")
        has_pitches_col = True
    except sqlite3.OperationalError:
        # no such column：舊資料庫尚未跑過 init_db 的 migration
        pass

    if has_pitches_col:
        log_sql = (
            "SELECT date, game_id, opponent, is_home, stats_json, sport_level, game_type, "
            "pitches_json "
            "FROM game_logs WHERE player_mlb_id = ? ORDER BY date DESC"
        )
    else:
        log_sql = (
            "SELECT date, game_id, opponent, is_home, stats_json, sport_level, game_type "
            "FROM game_logs WHERE player_mlb_id = ? ORDER BY date DESC"
        )

    cur.execute(log_sql, (player.mlb_id,))
    logs = []
    for row in cur.fetchall():
        log = Obj()
        log.date = parse_date(row[0])
        log.game_id = row[1]
        log.opponent = row[2]
        log.is_home = None if row[3] is None else bool(row[3])
        log.stats_json = loads_json_dict(row[4])
        log.sport_level = row[5] or ""
        log.game_type = row[6]
        log.is_postseason = log.game_type != REGULAR_SEASON_GAME_TYPE
        log.pitches_json = loads_json_list(row[7]) if has_pitches_col else []
        logs.append(log)

    return player, stats, logs

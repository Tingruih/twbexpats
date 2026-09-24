"""Pipeline A: player profile / season stats / game-log sync."""

import datetime
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from ..api import (
    FetchError,
    get_game_logs,
    get_next_game,
    get_player_advanced_stats,
    get_player_profile,
    get_player_stats,
)
from ..constants import GAME_LOG_GAME_TYPES, PLAYER_FETCH_WORKERS, SEASON_YEAR
from ..db.players import (
    get_cached_is_active,
    get_incomplete_history_ids,
    warn_orphaned_players,
)
from ..db.schema import init_db
from ..db.season_stats import (
    load_player_season_rows,
    load_season_row,
    players_with_existing_stats,
    save_season_row,
)
from ..levels import MINORS_KEY, sport_to_tier_key
from ..roster import (
    STATUS_INACTIVE,
    categorize_roster_status,
    is_active_player,
    parse_roster_from_file,
)
from ..stats.core.selectors import highest_level_row
from ..util.json import dumps_json
from ..util.log import describe_exc
from ..util.numbers import safe_float, safe_int
from ..util.obj import Obj
from .field_maps import apply_advanced_fields, apply_yearbyyear_fields

logger = logging.getLogger(__name__)


def _is_first_sync(mlb_id: int, synced_ids: set[int]) -> bool:
    """Whether *mlb_id* still needs a full-history fetch.

    ``synced_ids`` holds players that have season_stats rows *and* whose last
    full-history fetch completed (see ``_run_pipeline``); anyone else --
    never synced, or a previous full fetch had a request fail -- is treated
    as a first sync.
    """
    return mlb_id not in synced_ids


# ── Parallel data fetching ──


def _fetch_player_data(
    pconf: dict, year: int, fetch_all_years: bool = True
) -> Optional[dict]:
    """Fetch all API data for one player (no DB writes). Thread-safe.

    Args:
        pconf: Player configuration dict from roster.
        year: The target/current season year.
        fetch_all_years: If True (sync mode), fetch game logs for ALL historical
            years. If False (update mode), only fetch the current year's logs
            for a faster update.

    A failed profile request raises ``FetchError`` (the caller logs it and
    skips the player). Every later request is caught here: the part is
    recorded in ``failed_parts`` and left out of the bundle, so the writer
    keeps the old DB values for it instead of overwriting them with nothing.
    """
    mlb_id = pconf["mlb_id"]
    name_tw = pconf.get("name_tw", "")
    failed_parts: list[str] = []

    def fetch_part(part: str, fn, *args, **kwargs):
        """呼叫一個 API；失敗時記 warning、登記到 failed_parts，回 None。"""
        try:
            return fn(*args, **kwargs)
        except FetchError as e:
            failed_parts.append(part)
            logger.warning(
                "%s (%s): %s fetch failed: %s", name_tw, mlb_id, part, describe_exc(e)
            )
            return None

    profile = get_player_profile(mlb_id)
    # 查無此 ID：多半是 roster.json 的 mlb_id 打錯
    if not profile:
        logger.warning("No profile for %s (%s); check mlb_id in roster", mlb_id, name_tw)
        return None

    status_category = categorize_roster_status(
        profile.get("roster_status_code", ""),
        bool(profile.get("roster_is_active", False)),
        bool(profile.get("is_active", True)),
    )
    if status_category == STATUS_INACTIVE and not fetch_all_years:
        # Player has left the organization (Released/Retired/Voluntarily
        # Retired) and has already been synced before (fetch_all_years=False
        # means the caller already has season_stats for this player) --
        # their historical stats won't change further. Refresh just the
        # profile (so status/team info stays current) and skip the heavier
        # stats/advanced-stats/game-log/next-game fetches. A first-time sync
        # (fetch_all_years=True) always runs the full fetch below so newly
        # added retired players get their history backfilled once.
        return {
            "pconf": pconf,
            "profile": profile,
            "status_category": status_category,
            "stats_groups": [],
            "adv_groups": [],
            "log_groups": {},
            # 刻意清空：離隊球員不該再顯示下一場比賽
            "next_game": None,
            "next_game_ok": True,
            "years_with_data": set(),
            "full_history": False,
            "failed_parts": failed_parts,
        }

    # yearByYear stats
    stats_groups = fetch_part("yearByYear", get_player_stats, mlb_id) or []

    # Determine years with data for advanced/gamelog fetches
    years_with_data = set()
    for sg in stats_groups:
        if sg.get("type", {}).get("displayName", "") != "yearByYear":
            continue
        for split in sg.get("splits", []):
            yr = safe_int(split.get("season"))
            if yr:
                years_with_data.add(yr)

    # seasonAdvanced stats
    years_to_fetch = sorted(years_with_data) if years_with_data else [year]
    if not fetch_all_years:
        # update mode: only fetch advanced stats for the current year
        years_to_fetch = [year]
    adv_groups = fetch_part(
        "seasonAdvanced", get_player_advanced_stats, mlb_id, years=years_to_fetch
    ) or []

    # Game logs — in sync mode fetch ALL historical years so the game log
    # tab shows data for every season, not just the current one.
    if fetch_all_years:
        fetch_years = sorted(years_with_data) if years_with_data else [year]
    else:
        # update mode: only refresh the current year's logs (fast)
        fetch_years = [year]

    log_groups = {}
    for y in fetch_years:
        logs = fetch_part(f"gameLog {y}", get_game_logs, mlb_id, y)
        # 失敗的年份不放進 log_groups，該年既有的 game_logs 列維持原樣
        if logs is not None:
            log_groups[y] = logs

    # Next game -- skip for inactive (retired/released) players even during
    # a first-time backfill, since profile.team_id reflects their *last*
    # team and would otherwise show that team's schedule as "next game".
    next_game = None
    team_id = profile.get("team_id")
    if team_id and status_category != STATUS_INACTIVE:
        next_game = fetch_part("nextGame", get_next_game, team_id)

    return {
        "pconf": pconf,
        "profile": profile,
        "status_category": status_category,
        "stats_groups": stats_groups,
        "adv_groups": adv_groups,
        "log_groups": log_groups,
        "next_game": next_game,
        # get_next_game 回 None 也可能是「七天內沒比賽」，只有抓取失敗才保留舊值
        "next_game_ok": "nextGame" not in failed_parts,
        "years_with_data": years_with_data,
        "full_history": fetch_all_years,
        "failed_parts": failed_parts,
    }


def _write_player_to_db(conn: sqlite3.Connection, bundle: dict, year: int):
    """Write one player's fetched data into SQLite."""
    cur = conn.cursor()
    pconf = bundle["pconf"]
    profile = bundle["profile"]
    mlb_id = pconf["mlb_id"]
    name_tw = pconf.get("name_tw", "")

    # Upsert player profile
    cur.execute(
        "INSERT INTO players "
        "(mlb_id, name_en, name_tw, team, level, position, "
        " height, weight, birth_date, birth_city, birth_country, is_active, "
        " bat_side, pitch_hand, latest_transaction, roster_status, "
        " roster_status_code, roster_is_active, team_id, "
        " transactions_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(mlb_id) DO UPDATE SET "
        " name_en=excluded.name_en, name_tw=excluded.name_tw, "
        " position=excluded.position, "
        " height=excluded.height, weight=excluded.weight, "
        " birth_date=excluded.birth_date, birth_city=excluded.birth_city, "
        " birth_country=excluded.birth_country, is_active=excluded.is_active, "
        " bat_side=excluded.bat_side, pitch_hand=excluded.pitch_hand, "
        " latest_transaction=excluded.latest_transaction, "
        " roster_status=excluded.roster_status, "
        " roster_status_code=excluded.roster_status_code, "
        " roster_is_active=excluded.roster_is_active, team_id=excluded.team_id, "
        " transactions_json=excluded.transactions_json",
        (
            profile.get("mlb_id"),
            profile.get("full_name", ""),
            name_tw,
            profile.get("current_team_name") or "N/A",
            profile.get("current_team_level") or MINORS_KEY,
            profile.get("position", ""),
            profile.get("height", ""),
            profile.get("weight"),
            profile.get("birth_date"),
            profile.get("birth_city", ""),
            profile.get("birth_country", ""),
            1 if profile.get("is_active", True) else 0,
            profile.get("bat_side", ""),
            profile.get("pitch_hand", ""),
            profile.get("latest_transaction", ""),
            profile.get("roster_status", ""),
            profile.get("roster_status_code", ""),
            1 if profile.get("roster_is_active", False) else 0,
            profile.get("team_id"),
            dumps_json(profile.get("transactions_json", [])),
        ),
    )

    # yearByYear stats
    for stat_group in bundle["stats_groups"]:
        group_name = stat_group.get("group", {}).get("displayName", "").lower()
        stat_type = stat_group.get("type", {}).get("displayName", "")
        if stat_type != "yearByYear":
            continue

        for split in stat_group.get("splits", []):
            yr = safe_int(split.get("season"))
            stat = split.get("stat", {})
            team_name = split.get("team", {}).get("name", "")
            if not yr or not team_name:
                continue

            row = load_season_row(cur, mlb_id, yr, team_name)
            stat_doc = row["stat_json"]
            fielding_doc = row["fielding_json"]

            # Only overwrite gp from hitting/pitching; fielding splits have per-position
            # gamesPlayed which would otherwise clobber the correct total.
            if group_name != "fielding":
                stat_doc["gp"] = safe_int(stat.get("gamesPlayed"))
            apply_yearbyyear_fields(stat_doc, group_name, stat)

            if group_name == "fielding":
                pos_abbr = split.get("position", {}).get("abbreviation", "")
                if pos_abbr:
                    entry = {
                        "position": pos_abbr,
                        "gp": safe_int(stat.get("gamesPlayed")),
                        "gs": safe_int(stat.get("gamesStarted")),
                        "innings": safe_float(stat.get("innings")),
                        "assists": safe_int(stat.get("assists")),
                        "putouts": safe_int(stat.get("putOuts")),
                        "errors": safe_int(stat.get("errors")),
                        "chances": safe_int(stat.get("chances")),
                        # API 分母為零時給 ".---"，safe_float 轉成 None
                        "fielding_pct": safe_float(stat.get("fielding")),
                        "dp": safe_int(stat.get("doublePlays")),
                        "tp": safe_int(stat.get("triplePlays")),
                        "throwing_errors": safe_int(stat.get("throwingErrors")),
                        "range_factor_game": safe_float(stat.get("rangeFactorPerGame")),
                        "range_factor_9": safe_float(stat.get("rangeFactorPer9Inn")),
                    }
                    fielding_doc = [
                        f for f in fielding_doc if f.get("position") != pos_abbr
                    ]
                    fielding_doc.append(entry)

            save_season_row(
                cur,
                mlb_id,
                yr,
                team_name,
                split.get("league", {}).get("name", ""),
                # splits[].sport：{id, abbreviation}，abbreviation 隨年代變（A(Adv)）
                sport_to_tier_key(split.get("sport")),
                stat_doc,
                fielding_doc,
            )

    # seasonAdvanced stats
    for stat_group in bundle["adv_groups"]:
        group_name = stat_group.get("group", {}).get("displayName", "").lower()
        for split in stat_group.get("splits", []):
            yr = safe_int(split.get("season"))
            team_name = split.get("team", {}).get("name", "")
            if not yr or not team_name:
                continue

            row = load_season_row(cur, mlb_id, yr, team_name)
            stat_doc = row["stat_json"]
            apply_advanced_fields(stat_doc, group_name, split.get("stat", {}))

            save_season_row(
                cur,
                mlb_id,
                yr,
                team_name,
                row["league_name"],
                row["sport_level"],
                stat_doc,
                row["fielding_json"],
            )

    # Update level/team（覆寫上方 upsert 寫入的 level/team 初值）
    # 退役／離隊球員的 currentTeam 仍會回傳最後待過的球隊（例如 2003 年就離隊的
    # 球員仍掛 Sarasota Red Sox），照用會把 level_year 寫成今年，層級顯示成新制名稱；
    # 所以只有現役球員（與 render 分流首頁/退役頁同一個 is_active_player 定義）才信 currentTeam
    season_rows = load_player_season_rows(cur, mlb_id)
    player_view = Obj(transactions_json=profile.get("transactions_json", []))
    if (
        profile.get("current_team_level")
        and profile.get("current_team_name")
        and is_active_player(player_view, season_rows, year)
    ):
        # currentTeam 是球員「現在」的球隊，對應的是目標球季
        cur.execute(
            "UPDATE players SET level=?, level_year=?, team=? WHERE mlb_id=?",
            (profile["current_team_level"], year, profile["current_team_name"], mlb_id),
        )
    elif season_rows:
        # 非現役或沒有 currentTeam：取最近一季，交給 highest_level_row
        # 優先挑有出賽的列、再取最高層級（與退役頁標章同一條規則，只是範圍限最近一季）
        latest_year = season_rows[0].year  # load_player_season_rows 依年度新到舊排序
        best = highest_level_row([s for s in season_rows if s.year == latest_year])
        cur.execute(
            "UPDATE players SET level=?, level_year=?, team=? WHERE mlb_id=?",
            (best.sport_level or MINORS_KEY, best.year, best.team_name or "N/A", mlb_id),
        )
    # 兩者皆無（非現役且沒有任何 season_stats）：不更新，保留 players 原有的 level/team

    # Game logs
    for y, log_groups in bundle["log_groups"].items():
        for log_group in log_groups:
            if log_group.get("type", {}).get("displayName", "") != "gameLog":
                continue
            group_sport_level = sport_to_tier_key(log_group.get("sport"))
            for split in log_group.get("splits", []):
                game_date = split.get("date")
                game_pk = split.get("game", {}).get("gamePk")
                if not game_date or not game_pk:
                    continue
                game_type = split.get("gameType", "")
                if game_type not in GAME_LOG_GAME_TYPES:
                    # e.g. "P" — a duplicate label of an F/D/L/W game
                    continue
                # Prefer split-level sport, fall back to group-level
                split_sport_level = (
                    sport_to_tier_key(split.get("sport")) or group_sport_level
                )
                cur.execute(
                    "INSERT INTO game_logs "
                    "(player_mlb_id, date, game_id, opponent, is_home, stats_json, sport_level, "
                    " game_type) "
                    "VALUES (?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(player_mlb_id, game_id) DO UPDATE SET "
                    " date=excluded.date, opponent=excluded.opponent, "
                    " is_home=excluded.is_home, stats_json=excluded.stats_json, "
                    " sport_level = CASE WHEN excluded.sport_level != '' "
                    "   THEN excluded.sport_level ELSE game_logs.sport_level END, "
                    " game_type=excluded.game_type",
                    (
                        mlb_id,
                        game_date,
                        game_pk,
                        split.get("opponent", {}).get("name", "Unknown"),
                        1 if split.get("isHome") else 0,
                        dumps_json(split.get("stat", {})),
                        split_sport_level,
                        game_type,
                    ),
                )

    # Next game snapshot -- 抓取失敗時整段略過：寫入 {} 會蓋掉上次的下一場比賽，
    # 而 next_game_updated_at 又顯示剛更新，頁面看起來像「確定沒有比賽」
    if bundle["next_game_ok"]:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur.execute(
            "UPDATE players SET next_game_json=?, next_game_updated_at=?, "
            "next_game_for_season=? WHERE mlb_id=?",
            (dumps_json(bundle["next_game"] or {}), now, year, mlb_id),
        )

    # 全歷史抓取只要有一個請求失敗就標記未完成，下次執行仍會走全歷史路徑
    # （_run_pipeline 把 history_synced = 0 的球員排除在 synced_ids 外）；
    # 否則下次只抓當年，失敗那幾年的比賽紀錄/進階數據永遠補不回來
    if bundle["full_history"]:
        cur.execute(
            "UPDATE players SET history_synced=? WHERE mlb_id=?",
            (0 if bundle["failed_parts"] else 1, mlb_id),
        )

    conn.commit()


# ── Public entry point ──


def _run_pipeline(
    db_path: str,
    roster_file: str,
    year: int,
    only_player: Optional[int] = None,
    fetch_all_years: bool = True,
    mode_label: str = "Sync",
):
    """Shared fetch-and-write pipeline used by both sync and update."""
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_file)
    init_db(conn)

    players_config = parse_roster_from_file(roster_file)
    if only_player is not None:
        players_config = [p for p in players_config if p.get("mlb_id") == only_player]

    # Players with no season_stats rows yet have never been synced. Force a
    # full historical fetch for them even on an update/refresh run, so
    # newly added players (e.g. retired players added straight to the
    # roster) get backfilled automatically on the next pipeline run.
    synced_ids = players_with_existing_stats(conn) - get_incomplete_history_ids(
        conn.cursor()
    )
    cached_is_active = get_cached_is_active(conn.cursor())

    # Players cached as is_active=False (the API's "active" flag, set the
    # last time their profile was fetched) have permanently left affiliated
    # ball and won't come back, so an update run skips them entirely --
    # no profile/status re-fetch, no further steps. A full-history run
    # (sync / --full-history) re-fetches them too: that is the only way to
    # pick up MLB's retroactive corrections to a retired player's history. Players cached as
    # is_active=True keep going through _fetch_player_data, which refreshes
    # the profile and -- based on the *new* status -- either continues with
    # the full fetch (still active) or skips the heavier stats/log fetches
    # (e.g. just released, possibly RET/RL/VL). A first-time sync (no
    # season_stats yet) always runs the full fetch so newly added retired
    # players get backfilled once, and --player always forces a fetch
    # regardless of cached status.
    players_to_fetch = []
    for pconf in players_config:
        mlb_id = pconf["mlb_id"]
        if (
            only_player is None
            and not fetch_all_years
            and cached_is_active.get(mlb_id) is False
            and not _is_first_sync(mlb_id, synced_ids)
        ):
            logger.info("  skipped %s (inactive, status cached)", pconf.get("name_tw", mlb_id))
            continue
        players_to_fetch.append(pconf)

    total = len(players_to_fetch)
    logger.info(
        "%s: %d players into %s (max %d parallel, all_years=%s)",
        mode_label, total, db_file, PLAYER_FETCH_WORKERS, fetch_all_years,
    )

    # Phase 1: Fetch all data in parallel
    bundles = []
    with ThreadPoolExecutor(max_workers=PLAYER_FETCH_WORKERS) as executor:
        future_to_pconf = {
            executor.submit(
                _fetch_player_data,
                pconf,
                year,
                fetch_all_years or _is_first_sync(pconf["mlb_id"], synced_ids),
            ): pconf
            for pconf in players_to_fetch
        }
        failed_players = 0
        for i, future in enumerate(as_completed(future_to_pconf), 1):
            pconf = future_to_pconf[future]
            name = pconf.get("name_tw", pconf["mlb_id"])
            try:
                result = future.result()
            except FetchError as e:
                # profile 抓不到就整位跳過；DB 內既有資料不動，下次執行再抓
                failed_players += 1
                logger.warning(
                    "  [%d/%d] %s (%s): profile fetch failed, player skipped: %s",
                    i, total, name, pconf["mlb_id"], describe_exc(e),
                )
                continue
            except Exception:
                failed_players += 1
                logger.exception("  [%d/%d] fetch failed for %s (%s)", i, total, name, pconf["mlb_id"])
                continue
            if not result:
                logger.info("  [%d/%d] skipped %s (no profile)", i, total, name)
                continue
            bundles.append(result)
            note = ""
            if result["status_category"] == STATUS_INACTIVE:
                if _is_first_sync(pconf["mlb_id"], synced_ids):
                    note = " (inactive: first-time backfill)"
                elif fetch_all_years:
                    note = " (inactive: full re-sync)"
                else:
                    note = " (inactive: profile only)"
            if result["failed_parts"]:
                # 個別失敗已在 _fetch_player_data 各記一行 warning，這裡彙總成一行
                logger.warning(
                    "  [%d/%d] fetched %s%s -- INCOMPLETE, failed: %s",
                    i, total, name, note, ", ".join(result["failed_parts"]),
                )
            else:
                logger.info("  [%d/%d] fetched %s%s", i, total, name, note)

    # Phase 2: Write to DB sequentially
    saved = 0
    for bundle in bundles:
        name = bundle["pconf"].get("name_tw", bundle["profile"].get("full_name"))
        try:
            _write_player_to_db(conn, bundle, year)
            saved += 1
            logger.info("  saved %s", name)
        except Exception:
            logger.exception("  DB write failed for %s (%s)", name, bundle["pconf"]["mlb_id"])

    incomplete = sum(1 for b in bundles if b["failed_parts"])
    logger.info(
        "%s: %d/%d players saved (%d incomplete, %d failed to fetch)",
        mode_label, saved, total, incomplete, failed_players,
    )

    # After a full sync (not a single-player run), check for orphaned DB entries
    # that are no longer referenced by the current roster.
    if only_player is None:
        roster_ids = {p["mlb_id"] for p in parse_roster_from_file(roster_file)}
        warn_orphaned_players(conn, roster_ids)

    conn.close()
    logger.info("%s complete", mode_label)


def sync_database(
    db_path: str,
    roster_file: str,
    only_player: Optional[int] = None,
):
    """Full sync: fetch ALL historical years of stats + game logs for every player.

    Use this to build the database from scratch or ensure complete historical data.
    Slower than update_database because it fetches game logs for every season,
    and it also re-fetches retired players that an update run skips.
    Wired to build.py's ``sync`` / ``all`` and ``refresh --full-history``.
    """
    _run_pipeline(
        db_path=db_path,
        roster_file=roster_file,
        year=SEASON_YEAR,
        only_player=only_player,
        fetch_all_years=True,
        mode_label="Sync",
    )


def update_database(
    db_path: str,
    roster_file: str,
    only_player: Optional[int] = None,
):
    """Fast update: refresh player profiles and current-year stats/logs only.

    Use this for daily/regular updates during the season. It fetches yearByYear
    stats (all years) for the season-stats table, but only downloads game logs
    for the current year, making it significantly faster than a full sync.
    """
    _run_pipeline(
        db_path=db_path,
        roster_file=roster_file,
        year=SEASON_YEAR,
        only_player=only_player,
        fetch_all_years=False,
        mode_label="Update",
    )

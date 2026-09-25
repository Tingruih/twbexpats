"""Pipeline B：playByPlay 逐球資料抓取 → game_logs 快取 → Statcast 聚合。

``sync_statcast`` 依序執行：
  1. ``_games_to_fetch``：找出 ``pbp_version`` 落後的 (球員, 比賽, 角色)
  2. ``_fetch_games``：每場比賽只抓一次 live feed，平行依每一列的角色抽取
  3. ``_write_pitch_logs``：寫回 game_logs，完賽的比賽才標記版本
  4. ``_aggregate_statcast``：重算名冊每位球員每個角色、每個 (年, 層級) 的
     Statcast，寫進對應層級 season_stats 列的 ``statcast`` / ``p_statcast``
  5. ``sync_season_advanced``（``sync/advanced.py``）：FIP / WAR / wRC+ / xWPCT
  6. ``fetch_highlight_videos``：MLB 精華影片

第 4 步每次都重算全部歷史，不只本次新抓的比賽：公式調整後才會套用到舊資料。
但其中的 expectedStatistics 與第 5 步的 sabermetrics / FIP 常數是外部 API 數據，
依 ``db/season_fetches.py`` 的規則只抓當季與未抓過的過去球季。

game_logs 每個角色一列（``role``），逐球資料只屬於該列的角色：投手列只有本人
投出的球、打者列只有本人實際面對的球，兩者不會混在一起計算。

逐球資料是否需要（重）抓，只看 ``game_logs.pbp_version < PBP_EXTRACT_VERSION``：
  - 比賽已完賽且抽取成功：寫入資料並標記目前版本，之後不再抓
  - 比賽進行中或暫停：照樣寫入目前抽到的部分資料，但不標記版本，下次重抓
  - live feed 抓取失敗：什麼都不寫，下次重抓
  - ``extract.py`` 改了欄位：把 ``PBP_EXTRACT_VERSION`` 加 1，每場重抓剛好一次
"""

import datetime
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import NamedTuple, Optional

from ..api import (
    FetchError,
    get_game_content,
    get_game_play_by_play,
    get_player_expected_stats,
)
from ..api.content import extract_play_videos
from ..constants import CONTENT_RETRY_DAYS, GAME_FETCH_WORKERS, PBP_EXTRACT_VERSION
from ..db.game_logs import load_all_pitches_for_player
from ..db.season_fetches import (
    EXPECTED_STATS,
    P_EXPECTED_STATS,
    FetchedSet,
    load_fetched,
    mark_fetched,
    needs_fetch,
)
from ..db.play_videos import (
    content_fetch_candidates,
    mark_content_processed,
    save_play_videos,
)
from ..db.schema import init_db
from ..db.season_stats import save_season_row
from ..league_constant.pitching import PitchingConstants
from ..levels import MLB_KEY, is_mlb, sport_to_tier_key
from ..positions import BATTER, PITCHER, ROLES, role_field, stat_group_for_role
from ..roster import build_roster_map
from ..stats.batter_statcast import compute_batter_statcast
from ..stats.pitcher_statcast import compute_pitcher_statcast
from ..util.json import dumps_json, loads_json_dict, loads_json_list
from ..util.log import describe_exc
from ..util.numbers import safe_float, safe_int
from .advanced import sync_season_advanced
from .extract import extract_pitch_logs

logger = logging.getLogger(__name__)


# expectedStatistics 在 season_fetches 的登記來源，依角色分開（見 db/season_fetches.py）
_EXPECTED_SOURCES = {BATTER: EXPECTED_STATS, PITCHER: P_EXPECTED_STATS}

# 每個角色的 Statcast 聚合函式
_COMPUTE_STATCAST = {BATTER: compute_batter_statcast, PITCHER: compute_pitcher_statcast}


class FetchedGame(NamedTuple):
    """一場比賽的抽取結果；``pitches`` / ``events`` 以 ``(mlb_id, role)`` 為 key。

    ``is_final`` 為 False 時資料只到抓取當下為止（比賽進行中或暫停）。
    """

    pitches: dict[tuple[int, str], list[dict]]
    events: dict[tuple[int, str], list[dict]]
    sport_level: str
    is_final: bool


# ── Phase 1 ──────────────────────────────────────────────────────────────


def _games_to_fetch(cur, roster_ids: list[int]) -> dict[int, list[tuple[int, str]]]:
    """``{game_pk: [(mlb_id, role), ...]}``，``pbp_version`` 落後需要抓的比賽。

    以 game_logs 的「球員 × 比賽 × 角色」列為單位判斷，球員後來才加入名冊也能補抓；
    角色取自列本身，不看球員的主要守位。
    """
    placeholders = ",".join("?" * len(roster_ids))
    cur.execute(
        f"SELECT game_id, player_mlb_id, role FROM game_logs "
        f"WHERE player_mlb_id IN ({placeholders}) AND pbp_version < ?",
        [*roster_ids, PBP_EXTRACT_VERSION],
    )
    game_to_players: dict[int, list[tuple[int, str]]] = {}
    for gpk, mlb_id, role in cur.fetchall():
        game_to_players.setdefault(gpk, []).append((mlb_id, role))
    return game_to_players


# ── Phase 2 ──────────────────────────────────────────────────────────────


def _fetch_and_extract_game(
    game_pk: int, players_in_game: list[tuple[int, str]]
) -> Optional[FetchedGame]:
    """抓一場比賽的 live feed，為 ``players_in_game`` 的每個 (球員, 角色) 抽取逐球與非投球事件。

    每一列只抽自己的角色；抽不到就是空的，不改用另一個角色重抽——那樣會把
    投手當打者看到的球算進投手 Statcast（反之亦然）。同場又投又打的球員在
    game_logs 本來就有兩列，各自抽取。
    層級取自 ``gameData.teams.home.sport``；live feed 抓不到時回 None。
    """
    game_data = get_game_play_by_play(game_pk)
    # live feed 抓取失敗
    if not game_data:
        return None
    game_info = game_data.get("gameData", {})
    # gameData.status.abstractGameState：進行中、延遲、暫停（codedGameState T/U）
    # 都是 "Live"；Final / Game Over / 提前結束才是 "Final"。排程在美西晚間執行，
    # 常抓到進行中的比賽，這時只有前幾局的資料（見 _write_pitch_logs 如何處理）。
    is_final = game_info.get("status", {}).get("abstractGameState") == "Final"
    sport_obj = game_info.get("teams", {}).get("home", {}).get("sport", {})
    fetched = FetchedGame({}, {}, sport_to_tier_key(sport_obj), is_final)
    for mlb_id, role in players_in_game:
        pitches, events = extract_pitch_logs(game_data, mlb_id, role)
        fetched.pitches[(mlb_id, role)] = pitches
        fetched.events[(mlb_id, role)] = events
    return fetched


def _fetch_games(
    game_to_players: dict[int, list[tuple[int, str]]]
) -> dict[int, FetchedGame]:
    """平行抓取每場比賽，回 ``{game_pk: FetchedGame}``；抓取失敗的比賽不在結果內。"""
    fetched: dict[int, FetchedGame] = {}
    failed = 0
    total = len(game_to_players)
    with ThreadPoolExecutor(max_workers=GAME_FETCH_WORKERS) as executor:
        future_to_gpk = {
            executor.submit(_fetch_and_extract_game, gpk, players): gpk
            for gpk, players in game_to_players.items()
        }
        for i, future in enumerate(as_completed(future_to_gpk), 1):
            gpk = future_to_gpk[future]
            # 兩種失敗都不放進 fetched：不寫任何東西，pbp_version 不變，下次重抓
            try:
                game = future.result()
            except FetchError as e:
                failed += 1
                logger.warning(
                    "  live feed fetch failed for game_pk=%s: %s", gpk, describe_exc(e)
                )
                game = None
            except Exception:
                failed += 1
                logger.exception("  Statcast extract failed for game_pk=%s", gpk)
                game = None
            if game is not None:
                fetched[gpk] = game
            if i % 25 == 0 or i == total:
                logger.info("  [%d/%d] games fetched", i, total)
    in_progress = sum(1 for g in fetched.values() if not g.is_final)
    if in_progress:
        logger.info("  %d game(s) not final yet; partial data saved, will re-fetch", in_progress)
    if failed:
        logger.warning("  %d/%d game(s) failed to fetch; will retry next run", failed, total)
    return fetched


# ── Phase 3 ──────────────────────────────────────────────────────────────


def _write_pitch_logs(conn, fetched: dict[int, FetchedGame]) -> int:
    """把抽取結果寫回 game_logs，回寫入的 (球員, 比賽, 角色) 列數。

    未完賽的比賽照樣寫入目前的部分資料（網站先顯示），但 ``pbp_version``
    保持原值，``_games_to_fetch`` 下次會再選到，完賽後覆寫成完整資料。
    """
    cur = conn.cursor()
    written = 0
    for gpk, game in fetched.items():
        version = PBP_EXTRACT_VERSION if game.is_final else None
        for (mlb_id, role), pitches in game.pitches.items():
            cur.execute(
                "UPDATE game_logs SET pitches_json = ?, events_json = ?, "
                # live feed 沒給層級時保留主同步已寫入的 sport_level
                "sport_level = CASE WHEN ? != '' THEN ? ELSE sport_level END, "
                "pbp_version = COALESCE(?, pbp_version) "
                "WHERE player_mlb_id = ? AND game_id = ? AND role = ?",
                (
                    dumps_json(pitches),
                    dumps_json(game.events.get((mlb_id, role)) or []),
                    game.sport_level, game.sport_level,
                    version,
                    mlb_id, gpk, role,
                ),
            )
            written += 1
    conn.commit()
    return written


# ── Phase 4 ──────────────────────────────────────────────────────────────


def _parse_expected_stats(exp_groups: list) -> dict[tuple[int, str], dict]:
    """``/people/{id}/stats?stats=expectedStatistics`` → ``{(year, level): {xba, ...}}``。

    這個端點每年只回一筆整季 split（轉隊球員也不分隊，已對 Yu Chang 2022
    驗證），不會有 sabermetrics 那種逐隊覆寫問題。
    """
    expected: dict[tuple[int, str], dict] = {}
    for grp in exp_groups:
        for sp in grp.get("splits", []):
            yr = safe_int(sp.get("season"))
            if not yr:
                continue
            stat = sp.get("stat", {})
            fields = {
                "xba": safe_float(stat.get("avg")),
                "xslg": safe_float(stat.get("slg")),
                "xwoba": safe_float(stat.get("woba")),
                "xwobacon": safe_float(stat.get("wobaCon")),
            }
            # MiLB 一律回 0.0（API 不提供），全為 0/缺值即視為沒有資料
            if not any(fields.values()):
                continue
            # 只查 MLB 端點，splits[].sport 缺漏時也必定是 MLB
            level = sport_to_tier_key(sp.get("sport")) or MLB_KEY
            expected[(yr, level)] = fields
    return expected


def _compute_role_statcast(
    mlb_id: int,
    role: str,
    pitches_by_year_level: dict[tuple, list[dict]],
    fetched: FetchedSet,
    full_history: bool,
) -> tuple[dict, list[int]]:
    """一個角色的逐 (年, 層級) Statcast 聚合，加上該角色的 expectedStatistics。

    回 ``({(year, level): {"statcast": ..., "expected_stats": ...}}, 成功抓取的年份)``。
    expectedStatistics 帶該角色的 ``group``，依 ``db/season_fetches.py`` 的規則只抓
    當季與未登記的過去球季；沒抓的年份 ``expected_stats`` 為 None，
    ``_attach_statcast`` 會保留既有值。
    """
    # expectedStatistics 對 MiLB 一律回 0，只查該角色有 MLB 逐球資料的年份
    mlb_years = sorted({
        yr for yr, lvl in pitches_by_year_level
        if is_mlb(lvl) and needs_fetch(fetched, mlb_id, yr, force=full_history)
    })
    expected: dict[tuple[int, str], dict] = {}
    fetched_years: list[int] = []
    if mlb_years:
        try:
            expected = _parse_expected_stats(get_player_expected_stats(
                mlb_id, years=mlb_years, group=stat_group_for_role(role),
            ))
            # 回應裡沒有的年份（2015 年以前沒有 expected stats）也算抓過
            fetched_years = mlb_years
        except FetchError as e:
            # 不寫 expected 也不登記，_attach_statcast 保留既有值，下次重試
            logger.warning(
                "expectedStatistics (%s) fetch failed for %s years=%s: %s",
                role, mlb_id, mlb_years, describe_exc(e),
            )

    compute = _COMPUTE_STATCAST[role]
    return {
        (yr, lvl): {
            "statcast": compute(pitches),
            "expected_stats": expected.get((yr, lvl)),
        }
        for (yr, lvl), pitches in pitches_by_year_level.items()
    }, fetched_years


def _compute_player_statcast(
    mlb_id: int,
    db_path: str,
    fetched: dict[str, FetchedSet],
    full_history: bool,
) -> tuple[int, dict[str, dict], dict[str, list[int]]]:
    """平行 worker：讀逐球快取 → 每個有逐球資料的角色各自聚合（見 ``_compute_role_statcast``）。

    自開唯讀 SQLite 連線，不寫 DB。``fetched`` 為 ``{role: 該角色 expected 的登記}``。
    回 ``(mlb_id, {role: {(year, level): {...}}}, {role: 成功抓取的年份})``；
    沒有逐球資料的角色不會出現在結果中（不設門檻，投手上場打擊一次也會算）。
    """
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        pitches_by_role = {
            role: load_all_pitches_for_player(conn.cursor(), mlb_id, role)
            for role in ROLES
        }
    finally:
        conn.close()

    results: dict[str, dict] = {}
    fetched_years: dict[str, list[int]] = {}
    for role, pitches_by_year_level in pitches_by_role.items():
        # 這個角色沒有任何逐球資料
        if not pitches_by_year_level:
            continue
        results[role], fetched_years[role] = _compute_role_statcast(
            mlb_id, role, pitches_by_year_level, fetched[role], full_history
        )
    return mlb_id, results, fetched_years


def _attach_statcast(
    cur,
    mlb_id: int,
    role: str,
    year: int,
    level: str,
    statcast_data: dict,
    expected_stats: Optional[dict],
) -> None:
    """把一個角色、一個 (年, 層級) 的 Statcast 與 expected stats 寫進對應層級的 season_stats 列。

    寫入 ``role_field(role, "statcast")`` / ``role_field(role, "expected")``
    （打擊 ``statcast`` / ``expected``，投球 ``p_statcast`` / ``p_expected``），
    同一列的另一個角色不受影響。
    同年打過多個層級的球員，每個層級各拿自己的數據。``level`` 為空字串
    （``load_all_pitches_for_player`` 無法判定層級的舊資料）時，只在該年
    只有一列時寫入，否則無從判斷該寫哪一列，直接略過。
    轉隊球員同層級有多列時，每一列都寫同一份整季聚合，
    所以 ``render/pages.py`` 的 ``_merge_level_rows`` 不需要合併 Statcast。
    """
    cur.execute(
        "SELECT team_name, league_name, sport_level, stat_json, fielding_json "
        "FROM season_stats WHERE player_mlb_id = ? AND year = ?",
        (mlb_id, year),
    )
    rows = cur.fetchall()
    if level:
        # 兩邊都是 sport_to_tier_key() 寫入的 tier key，直接比字串
        targets = [r for r in rows if r[2] == level]
    else:
        targets = rows if len(rows) == 1 else []

    for team_name, league_name, row_level, stat_json, fielding_json in targets:
        stat_doc = loads_json_dict(stat_json)
        stat_doc[role_field(role, "statcast")] = statcast_data
        if expected_stats:
            stat_doc[role_field(role, "expected")] = expected_stats
        save_season_row(
            cur, mlb_id, year, team_name, league_name, row_level,
            stat_doc, loads_json_list(fielding_json),
        )


def _aggregate_statcast(
    conn,
    db_path: str,
    roster_map: dict,
    *,
    full_history: bool = False,
) -> None:
    """平行重算名冊每位球員每個角色的 Statcast，主執行緒依序寫回 season_stats。"""
    logger.info("  aggregating statcast per player-role-year-level (%d workers) ...", GAME_FETCH_WORKERS)
    cur = conn.cursor()
    # 在主執行緒讀一次，worker 只讀不寫
    fetched = {role: load_fetched(cur, _EXPECTED_SOURCES[role]) for role in ROLES}
    with ThreadPoolExecutor(max_workers=GAME_FETCH_WORKERS) as executor:
        future_to_id = {
            executor.submit(
                _compute_player_statcast, mlb_id, db_path, fetched, full_history,
            ): mlb_id
            for mlb_id in roster_map
        }
        for future in as_completed(future_to_id):
            mlb_id = future_to_id[future]
            name = roster_map[mlb_id].get("name_tw", str(mlb_id))
            try:
                _, results, fetched_years = future.result()
                if not results:
                    continue
                for role, by_year_level in results.items():
                    for (yr, lvl), data in by_year_level.items():
                        _attach_statcast(
                            cur, mlb_id, role, yr, lvl,
                            data["statcast"], data["expected_stats"],
                        )
                    mark_fetched(
                        cur, _EXPECTED_SOURCES[role], mlb_id, fetched_years.get(role, [])
                    )
                conn.commit()
                logger.info(
                    "    %s: aggregated %s",
                    name,
                    ", ".join(f"{role} {len(r)} season-level(s)" for role, r in results.items()),
                )
            except Exception:
                logger.exception("  Statcast aggregation failed for %s", name)


# ── Phase 6 ──────────────────────────────────────────────────────────────


def fetch_highlight_videos(conn, roster_ids, *, now_iso=None) -> int:
    """抓 MLB ``/content`` 的精華影片 mp4 URL，以 play_id 快取；回寫入影片數。

    Baseball Savant 影片由前端按需解析，不在這裡預抓歷史 playId。
    """
    now_iso = now_iso or datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = conn.cursor()
    retry_cutoff = (
        datetime.date.today() - datetime.timedelta(days=CONTENT_RETRY_DAYS)
    ).isoformat()
    candidates = content_fetch_candidates(cur, roster_ids, retry_cutoff)
    if not candidates:
        return 0

    logger.info("Statcast: fetching highlight content for %d MLB game(s) ...", len(candidates))
    contents: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=GAME_FETCH_WORKERS) as executor:
        future_to_gpk = {
            executor.submit(get_game_content, game_pk): game_pk
            for game_pk in candidates
        }
        for future in as_completed(future_to_gpk):
            game_pk = future_to_gpk[future]
            # 失敗的比賽不放進 contents、不標記已處理：標成「0 部影片」的話，
            # 超過 CONTENT_RETRY_DAYS 的比賽就永遠不會再抓
            try:
                contents[game_pk] = future.result()
            except FetchError as exc:
                logger.warning(
                    "content fetch failed for game_pk=%s: %s", game_pk, describe_exc(exc)
                )
            except Exception:
                logger.exception("content fetch failed for game_pk=%s", game_pk)

    written = 0
    for game_pk, content in contents.items():
        videos = extract_play_videos(content)
        save_play_videos(cur, game_pk, videos, now_iso)
        mark_content_processed(cur, game_pk, len(videos), now_iso)
        written += len(videos)
    conn.commit()
    logger.info(
        "  saved %d play video(s) across %d/%d game(s)", written, len(contents), len(candidates)
    )
    return written


# ── 入口 ──────────────────────────────────────────────────────────────────


def sync_statcast(
    db_path: str,
    roster_file: str,
    only_player: Optional[int] = None,
    update_constants: bool = False,
    full_history: bool = False,
):
    """抓取缺少的 playByPlay、重算 Statcast 與進階數據（流程見模組 docstring）。

    當季的外部數據不論旗標每次都重抓。``update_constants``（``--update-constants``）
    強制重抓過去球季的投手 FIP 常數（見 league_constant.pitching）；
    ``full_history``（``--full-history``）強制重抓過去球季的 expectedStatistics
    與 sabermetrics。
    """
    conn = sqlite3.connect(Path(db_path))
    init_db(conn)
    cur = conn.cursor()

    roster_map = build_roster_map(roster_file)
    if only_player is not None:
        roster_map = {k: v for k, v in roster_map.items() if k == only_player}
    if not roster_map:
        logger.info("Statcast: no matching players in roster")
        conn.close()
        return
    roster_ids = list(roster_map)

    game_to_players = _games_to_fetch(cur, roster_ids)
    logger.info(
        "Statcast: %d players, %d unique games to fetch (%d player-game-role rows to update)",
        len(roster_ids), len(game_to_players), sum(map(len, game_to_players.values())),
    )
    if not game_to_players:
        logger.info("  no new games to fetch; recomputing statcast from existing pitch data ...")

    fetched = _fetch_games(game_to_players)
    logger.info("  wrote pitch logs for %d player-game-role rows", _write_pitch_logs(conn, fetched))

    _aggregate_statcast(conn, db_path, roster_map, full_history=full_history)

    pitching_constants = PitchingConstants(conn, force_refresh=update_constants)
    sync_season_advanced(conn, roster_ids, pitching_constants, full_history=full_history)

    fetch_highlight_videos(conn, roster_ids)

    conn.close()
    logger.info("Statcast sync complete")

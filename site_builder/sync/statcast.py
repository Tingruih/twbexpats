"""Pipeline B: play-by-play fetch + Statcast aggregation into season_stats."""

import datetime
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from ..api import (
    get_game_play_by_play,
    get_game_sport_level,
    get_player_expected_stats,
    get_player_sabermetrics,
)
from ..constants import GAME_FETCH_WORKERS
from ..db.fip_constants_cache import get_fip_constants
from ..db.game_logs import load_all_pitches_for_player
from ..db.schema import init_db
from ..db.season_stats import save_season_row
from ..levels import sport_obj_to_abbr
from ..roster import build_roster_map
from ..stats.advanced.fip import compute_fip
from ..stats.advanced.xwpct import compute_xwpct
from ..stats.batter_statcast import compute_batter_statcast
from ..stats.pitcher_statcast import compute_pitcher_statcast
from ..util.json import dumps_json, loads_json_dict, loads_json_list
from ..util.numbers import safe_float, safe_int
from .extract import extract_pitch_logs

logger = logging.getLogger(__name__)


def _fetch_and_extract_game(
    game_pk: int, players_in_game: list[tuple[int, str]]
) -> tuple[dict[int, list[dict]], str]:
    """Fetch one game's live feed and extract pitches for every relevant player.

    Args:
        game_pk: the game primary key.
        players_in_game: list of (mlb_id, position) tuples — players we
                         care about that appeared in this game.

    Returns:
        A 2-tuple of:
          - {mlb_id: [pitch_dict, ...]}  (may be empty per player)
          - sport_level string (e.g. "MLB", "AAA") extracted from the live feed,
            or "" if unavailable.
    """
    game_data = get_game_play_by_play(game_pk)
    out: dict[int, list[dict]] = {}
    if not game_data:
        return out, ""
    sport_obj = (
        game_data.get("gameData", {})
        .get("teams", {})
        .get("home", {})
        .get("sport", {})
    )
    sport_level: str = sport_obj_to_abbr(sport_obj)
    for mlb_id, position in players_in_game:
        role = "pitcher" if position == "P" else "batter"
        pitches = extract_pitch_logs(game_data, mlb_id, role)
        if not pitches:
            # try the opposite role as fallback (two-way / misconfigured roster)
            alt = "batter" if role == "pitcher" else "pitcher"
            pitches = extract_pitch_logs(game_data, mlb_id, alt)
        out[mlb_id] = pitches
    return out, sport_level


def _pitches_need_hit_coord_backfill(pitches: list[dict]) -> bool:
    in_play = [p for p in pitches if p.get("is_in_play")]
    if not in_play:
        return False
    return all(
        p.get("hit_coord_x") is None or p.get("hit_coord_y") is None
        for p in in_play
    )


def _merge_statcast_into_season(
    cur,
    mlb_id: int,
    year: int,
    position: str,
    statcast_data: dict,
    fip_constants_lookup,
    sport_level: str = "",
    sabermetrics: Optional[dict] = None,
    expected_stats: Optional[dict] = None,
):
    """Merge computed Statcast + sabermetrics + expected-stats into season_stats.

    ``statcast_data`` is written only to rows whose sport_level matches
    ``sport_level`` (when provided and non-empty). This ensures that players
    who played at multiple levels in the same year get per-level Statcast data
    rather than the same season-aggregate written to every row.

    When ``sport_level`` is empty (legacy data with unresolved levels):
      - If there is exactly ONE season_stats row for the year, write to it.
      - If there are MULTIPLE rows, skip writing statcast to prevent the bug
        where identical combined data appears for every level.

    ``sabermetrics`` (MLB-only) and ``expected_stats`` are also written only
    to the row whose sport_level matches ``sport_level`` (not broadcast to all
    rows). This prevents shuttle-player rows at MiLB levels from receiving
    MLB-derived aggregate stats.

    ``fip_constants_lookup(sport_level, year) -> {league_name: fip_constant}``
    resolves the MiLB FIP constant per-league (see db.fip_constants_cache);
    callers should memoize it across a whole sync run so the same
    (level, year) isn't re-fetched for every player.
    """
    cur.execute(
        "SELECT team_name, league_name, sport_level, stat_json, fielding_json "
        "FROM season_stats WHERE player_mlb_id = ? AND year = ?",
        (mlb_id, year),
    )
    rows = cur.fetchall()
    if not rows:
        return

    is_pitcher = position == "P"

    # wRC+ 與 WAR 是整個賽季的合計數值，並非隸屬於某支球隊。
    # 當球員在賽季中途轉隊時，資料庫同一年度會存在多筆 MLB 記錄（每支球隊各一筆）。
    # 若將相同的合計數值寫入每一筆記錄，畫面上會出現重複的欄位，導致資料顯示錯誤。
    # 因此使用旗標追蹤是否已寫入過，確保 wRC+ 與 WAR 只寫入該年度第一筆 MLB 記錄。
    saber_written = False

    for row in rows:
        team_name = row[0]
        league_name = row[1]
        row_sport_level = row[2]
        stat_doc = loads_json_dict(row[3])
        fielding_doc = loads_json_list(row[4])

        # Write statcast only to the matching level row.
        # If sport_level is empty (unresolved legacy data), only write when
        # there is a single row for the year (unambiguous).
        if sport_level:
            if row_sport_level == sport_level:
                stat_doc["statcast"] = statcast_data
        elif len(rows) == 1:
            stat_doc["statcast"] = statcast_data
        # else: multiple rows + unknown level → skip to avoid duplicates

        # Attach sabermetrics (MLB only) — only write to the matching sport_level row.
        # Sabermetrics are always fetched from the MLB endpoint; broadcasting them
        # to MiLB rows of the same year would be misleading.
        if sabermetrics and row_sport_level == "MLB":
            if not sport_level or row_sport_level == sport_level:
                stat_doc["saber"] = sabermetrics

        # Attach expected stats — only write to the matching sport_level row.
        # MiLB expected stats are all 0.0 (API limitation), so valid data only
        # arrives for MLB rows; still guard by sport_level match for correctness.
        if expected_stats:
            if sport_level and row_sport_level == sport_level:
                stat_doc["expected"] = expected_stats
            elif not sport_level and len(rows) == 1:
                stat_doc["expected"] = expected_stats

        # Compute FIP (MiLB path) if we have enough inputs
        if is_pitcher and row_sport_level and row_sport_level != "MLB":
            ip = stat_doc.get("ip")
            league_constants = fip_constants_lookup(row_sport_level, year)
            c_fip = league_constants.get(league_name) or league_constants.get("")
            fip_val = compute_fip(
                hr=stat_doc.get("p_hr"),
                bb=stat_doc.get("bb"),
                hbp=stat_doc.get("p_hbp"),
                k=stat_doc.get("so"),
                ip=safe_float(ip),
                c_fip=c_fip,
            )
            if fip_val is not None:
                # Store FIP rounded for display, but feed the raw value into
                # xwpct so the downstream stat isn't computed off a truncated FIP.
                stat_doc["fip"] = round(fip_val, 2)
                stat_doc["xwpct"] = compute_xwpct(fip_val, row_sport_level, year)
        elif is_pitcher and row_sport_level == "MLB" and sabermetrics:
            fip_val = safe_float(sabermetrics.get("fip"))
            if fip_val is not None:
                stat_doc["fip"] = round(fip_val, 2)
                stat_doc["xfip"] = safe_float(sabermetrics.get("xfip"))
                stat_doc["war"] = safe_float(sabermetrics.get("war"))
                stat_doc["xwpct"] = compute_xwpct(fip_val, "MLB", year)
        elif not is_pitcher and row_sport_level == "MLB" and sabermetrics:
            if not saber_written:
                # API 回傳的 sabermetrics 是整季合計，與球隊無關。
                # 只將 WAR 與 wRC+ 寫入該年度遇到的第一筆 MLB 記錄，
                # 避免轉隊球員的每支球隊記錄都出現相同數值。
                # 寫入完畢後將旗標設為 True，後續同年度的 MLB 記錄不再寫入。
                stat_doc["war"] = safe_float(sabermetrics.get("war"))
                wrc_plus_val = safe_int(sabermetrics.get("wRcPlus"))
                if wrc_plus_val is not None:
                    stat_doc["wrc_plus"] = wrc_plus_val
                saber_written = True

        save_season_row(
            cur, mlb_id, year, team_name,
            league_name, row_sport_level, stat_doc, fielding_doc,
        )


def _compute_player_statcast_bundle(
    mlb_id: int,
    db_path: str,
    position: str,
) -> tuple[int, Optional[dict]]:
    """Parallel worker: load pitches + fetch API stats + compute statcast.

    Opens its own SQLite connection for reads; performs no DB writes.
    Returns (mlb_id, {(year, sport_level): {statcast, sabermetrics, expected_stats}})
    or (mlb_id, None) when the player has no pitch data.
    """
    conn = sqlite3.connect(db_path, timeout=30)
    cur = conn.cursor()
    try:
        pitches_by_year_level = load_all_pitches_for_player(cur, mlb_id)
        if not pitches_by_year_level:
            return mlb_id, None

        years = sorted({k[0] for k in pitches_by_year_level.keys()})

        cur.execute(
            "SELECT COUNT(*) FROM season_stats WHERE player_mlb_id = ? AND sport_level = 'MLB'",
            (mlb_id,),
        )
        has_mlb_stats = (cur.fetchone() or [0])[0] > 0
    finally:
        conn.close()

    is_pitcher = position == "P"
    saber_by_year: dict[int, dict] = {}
    expected_by_year: dict[tuple, dict] = {}

    if has_mlb_stats:
        try:
            target_group = "pitching" if is_pitcher else "hitting"
            saber_groups = get_player_sabermetrics(mlb_id, years=years)
            for grp in saber_groups:
                if grp.get("group", {}).get("displayName", "").lower() != target_group:
                    continue
                for sp in grp.get("splits", []):
                    yr = safe_int(sp.get("season"))
                    if yr:
                        saber_by_year[yr] = sp.get("stat", {})
        except Exception as e:
            logger.warning("sabermetrics fetch failed for %s: %s", mlb_id, e)

    try:
        group = "pitching" if is_pitcher else "hitting"
        exp_groups = get_player_expected_stats(mlb_id, years=years, group=group)
        for grp in exp_groups:
            for sp in grp.get("splits", []):
                yr = safe_int(sp.get("season"))
                if yr:
                    stat = sp.get("stat", {})
                    xba = safe_float(stat.get("avg"))
                    xslg = safe_float(stat.get("slg"))
                    xwoba = safe_float(stat.get("woba"))
                    xwobacon = safe_float(stat.get("wobaCon"))
                    if not any([xba, xslg, xwoba, xwobacon]):
                        continue
                    split_sport_level = (
                        sp.get("sport", {}).get("abbreviation", "") or "MLB"
                    )
                    expected_by_year[(yr, split_sport_level)] = {
                        "xba": xba,
                        "xslg": xslg,
                        "xwoba": xwoba,
                        "xwobacon": xwobacon,
                    }
    except Exception as e:
        logger.warning("expectedStats fetch failed for %s: %s", mlb_id, e)

    results: dict[tuple, dict] = {}
    for (yr, lvl), pitches in pitches_by_year_level.items():
        if is_pitcher:
            statcast_data = compute_pitcher_statcast(pitches)
        else:
            statcast_data = compute_batter_statcast(pitches)
        results[(yr, lvl)] = {
            "statcast": statcast_data,
            "sabermetrics": saber_by_year.get(yr),
            "expected_stats": expected_by_year.get((yr, lvl)),
        }

    return mlb_id, results


def sync_statcast(
    db_path: str,
    roster_file: str,
    year: int,
    only_player: Optional[int] = None,
    update_constants: bool = False,
):
    """Fetch playByPlay for every un-processed game and compute Statcast.

    Pipeline:
      1. Load roster map (mlb_id -> player config from roster.json).
      2. For each player: collect all (game_pk, date) from game_logs where
         pitches_json is empty AND game_pk is not in playbyplay_processed.
      3. Group by game_pk (one fetch per unique game, parallelised).
      4. Extract pitches for every roster player in that game.
      5. Write pitches_json back to game_logs (per-player row), mark game_pk
         as processed.
      6. For each affected player-year, recompute Statcast aggregates and
         merge into season_stats.stat_json. Also fetch sabermetrics (MLB)
         and expectedStatistics (all levels).

    ``update_constants`` forces a fresh fetch of the MiLB FIP constants for
    *past* seasons too (see db.fip_constants_cache) — the current season's
    constants are always fetched fresh regardless, since its league totals
    keep changing as games are played.
    """
    db_file = Path(db_path)
    conn = sqlite3.connect(db_file)
    init_db(conn)
    cur = conn.cursor()

    fip_constants_cache: dict[tuple[str, int], dict[str, float]] = {}

    def _fip_constants(sport_level: str, yr: int) -> dict[str, float]:
        key = (sport_level, yr)
        if key not in fip_constants_cache:
            fip_constants_cache[key] = get_fip_constants(
                conn, sport_level, yr, force_refresh=update_constants
            )
        return fip_constants_cache[key]

    roster_map = build_roster_map(roster_file)
    if only_player is not None:
        roster_map = {k: v for k, v in roster_map.items() if k == only_player}

    if not roster_map:
        print("Statcast: no matching players in roster")
        conn.close()
        return

    # Pull position for each roster player from the DB (fallback to empty)
    positions: dict[int, str] = {}
    for mlb_id in roster_map:
        cur.execute("SELECT position FROM players WHERE mlb_id = ?", (mlb_id,))
        row = cur.fetchone()
        positions[mlb_id] = (row[0] if row else "") or ""

    # ── Phase 0: backfill sport_level for historical game_logs ──
    # Historical rows written before sport_level tracking was added will have
    # sport_level=''. Find them (scoped to the current roster selection), fetch
    # the level from a lightweight live-feed call, and fill it in.  Once
    # filled, subsequent runs skip this entirely.
    placeholders = ",".join("?" * len(roster_map))
    cur.execute(
        f"SELECT DISTINCT game_id FROM game_logs "
        f"WHERE player_mlb_id IN ({placeholders}) AND sport_level = '' "
        f"AND pitches_json != '[]' AND pitches_json != 'null' AND pitches_json IS NOT NULL",
        list(roster_map.keys()),
    )
    backfill_game_ids = [row[0] for row in cur.fetchall() if row[0] is not None]

    if backfill_game_ids:
        print(
            f"Statcast: backfilling sport_level for {len(backfill_game_ids)} "
            f"historical game(s) ..."
        )
        backfill_levels: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=GAME_FETCH_WORKERS) as executor:
            future_to_gpk = {
                executor.submit(get_game_sport_level, gpk): gpk
                for gpk in backfill_game_ids
            }
            for future in as_completed(future_to_gpk):
                gpk = future_to_gpk[future]
                try:
                    lvl = future.result()
                    backfill_levels[gpk] = lvl
                except Exception as e:
                    logger.warning(
                        "backfill sport_level failed for game_pk=%s: %s", gpk, e
                    )
        for gpk, lvl in backfill_levels.items():
            if lvl:
                cur.execute(
                    "UPDATE game_logs SET sport_level = ? "
                    "WHERE game_id = ? AND sport_level = ''",
                    (lvl, gpk),
                )
        conn.commit()
        filled = sum(1 for v in backfill_levels.values() if v)
        print(f"  backfilled sport_level for {filled}/{len(backfill_game_ids)} games")

    # ── Phase 1: build list of (game_pk, [players in game]) to fetch ──
    game_to_players: dict[int, list[tuple[int, str]]] = {}
    target_count = 0  # count of player-game rows needing pitch data

    for mlb_id in roster_map:
        cur.execute(
            "SELECT game_id, pitches_json, hit_coord_checked FROM game_logs "
            "WHERE player_mlb_id = ?",
            (mlb_id,),
        )
        for gpk, pitches_json, hit_coord_checked in cur.fetchall():
            if gpk is None:
                continue
            needs_fetch = pitches_json in (None, "[]")
            if not needs_fetch and not hit_coord_checked:
                needs_fetch = _pitches_need_hit_coord_backfill(
                    loads_json_list(pitches_json)
                )
            if not needs_fetch:
                continue
            target_count += 1
            game_to_players.setdefault(gpk, []).append((mlb_id, positions.get(mlb_id, "")))

    total_games = len(game_to_players)
    print(
        f"Statcast: {len(roster_map)} players, {total_games} unique games to fetch "
        f"({target_count} player-game rows to update)"
    )
    if total_games == 0:
        print("  no new games to fetch; recomputing statcast from existing pitch data ...")

    # ── Phase 2: parallel fetch + extract ──
    extracted: dict[tuple[int, int], list[dict]] = {}  # (player_id, game_pk) -> pitches
    game_sport_levels: dict[int, str] = {}  # game_pk -> sport_level
    with ThreadPoolExecutor(max_workers=GAME_FETCH_WORKERS) as executor:
        future_to_gpk = {
            executor.submit(_fetch_and_extract_game, gpk, players): gpk
            for gpk, players in game_to_players.items()
        }
        for i, future in enumerate(as_completed(future_to_gpk), 1):
            gpk = future_to_gpk[future]
            try:
                result, sport_level = future.result()
                game_sport_levels[gpk] = sport_level
                for mlb_id, pitches in result.items():
                    extracted[(mlb_id, gpk)] = pitches
                if i % 25 == 0 or i == total_games:
                    print(f"  [{i}/{total_games}] games fetched")
            except Exception as e:
                print(f"  game {gpk} failed: {e}")
                logger.exception("Statcast fetch failed for game_pk=%s", gpk)

    # ── Phase 3: write pitch logs back to DB ──
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    affected_years_by_player: dict[int, set[int]] = {}

    for (mlb_id, gpk), pitches in extracted.items():
        # Look up the game's date so we know which year is affected
        cur.execute(
            "SELECT date FROM game_logs WHERE player_mlb_id = ? AND game_id = ?",
            (mlb_id, gpk),
        )
        row = cur.fetchone()
        if not row:
            continue
        date_str = row[0] or ""
        yr = None
        if len(date_str) >= 4:
            try:
                yr = int(date_str[:4])
            except ValueError:
                pass

        lvl = game_sport_levels.get(gpk, "")
        # Empty pitch list means the player didn't appear at the plate in this
        # game (AB=0, PA=0: defensive sub, pinch runner, DNP).  Write JSON null
        # instead of '[]' so Phase 1's needs_fetch check won't mistake it for
        # "not yet fetched" and trigger an infinite re-fetch loop.
        stored_pitches = dumps_json(pitches) if pitches else "null"
        # Only overwrite sport_level when we got a valid one from the live
        # feed; otherwise preserve whatever the main sync already stored.
        if lvl:
            cur.execute(
                "UPDATE game_logs SET pitches_json = ?, sport_level = ?, hit_coord_checked = 1 "
                "WHERE player_mlb_id = ? AND game_id = ?",
                (stored_pitches, lvl, mlb_id, gpk),
            )
        else:
            cur.execute(
                "UPDATE game_logs SET pitches_json = ?, hit_coord_checked = 1 "
                "WHERE player_mlb_id = ? AND game_id = ?",
                (stored_pitches, mlb_id, gpk),
            )
        if yr is not None:
            affected_years_by_player.setdefault(mlb_id, set()).add(yr)

    # Mark games as processed
    for gpk in game_to_players:
        cur.execute(
            "INSERT OR REPLACE INTO playbyplay_processed (game_pk, processed_at) "
            "VALUES (?, ?)",
            (gpk, now),
        )
    conn.commit()
    print(f"  wrote pitch logs for {len(extracted)} player-games")

    # ── Phase 4: parallel compute + API fetch, then sequential DB write ──
    print(f"  aggregating statcast per player-year-level ({GAME_FETCH_WORKERS} workers) ...")
    with ThreadPoolExecutor(max_workers=GAME_FETCH_WORKERS) as executor:
        future_to_mlb_id = {
            executor.submit(
                _compute_player_statcast_bundle,
                mlb_id,
                str(db_file),
                positions.get(mlb_id, ""),
            ): mlb_id
            for mlb_id in roster_map
        }
        for future in as_completed(future_to_mlb_id):
            mlb_id = future_to_mlb_id[future]
            name = roster_map[mlb_id].get("name_tw", str(mlb_id))
            try:
                _, results = future.result()
                if not results:
                    continue
                position = positions.get(mlb_id, "")
                for (yr, lvl), data in results.items():
                    _merge_statcast_into_season(
                        cur,
                        mlb_id=mlb_id,
                        year=yr,
                        position=position,
                        statcast_data=data["statcast"],
                        fip_constants_lookup=_fip_constants,
                        sport_level=lvl,
                        sabermetrics=data["sabermetrics"],
                        expected_stats=data["expected_stats"],
                    )
                conn.commit()
                print(f"    {name}: aggregated {len(results)} season-level(s)")
            except Exception as e:
                print(f"  error for {name}: {e}")
                logger.exception("Statcast aggregation failed for %s", name)

    conn.close()
    print("Statcast sync complete")

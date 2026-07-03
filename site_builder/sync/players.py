"""Pipeline A: player profile / season stats / game-log sync."""

import datetime
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from ..api import (
    get_game_logs,
    get_next_game,
    get_player_advanced_stats,
    get_player_profile,
    get_player_stats,
)
from ..constants import PLAYER_FETCH_WORKERS
from ..db.players import get_cached_is_active, warn_orphaned_players
from ..db.schema import init_db
from ..db.season_stats import (
    load_season_row,
    players_with_existing_stats,
    save_season_row,
)
from ..levels import TIERS
from ..roster import categorize_roster_status, parse_roster_from_file
from ..util.json import dumps_json
from ..util.numbers import safe_float, safe_int
from .field_maps import apply_advanced_fields, apply_yearbyyear_fields

logger = logging.getLogger(__name__)


def _is_first_sync(mlb_id: int, synced_ids: set[int]) -> bool:
    """A player with no season_stats rows yet is being synced for the first time."""
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
    """
    mlb_id = pconf["mlb_id"]
    name_tw = pconf.get("name_tw", "")

    profile = get_player_profile(mlb_id)
    if not profile:
        logger.warning("No profile for %s (%s)", mlb_id, name_tw)
        return None

    status_category = categorize_roster_status(
        profile.get("roster_status_code", ""),
        bool(profile.get("roster_is_active", False)),
        bool(profile.get("is_active", True)),
    )
    if status_category == "inactive" and not fetch_all_years:
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
            "next_game": None,
            "years_with_data": set(),
        }

    # yearByYear stats
    stats_groups = []
    try:
        stats_groups = get_player_stats(mlb_id)
    except Exception as e:
        logger.warning("yearByYear failed for %s: %s", mlb_id, e)

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
    adv_groups = []
    try:
        years_to_fetch = sorted(years_with_data) if years_with_data else [year]
        if not fetch_all_years:
            # update mode: only fetch advanced stats for the current year
            years_to_fetch = [year]
        adv_groups = get_player_advanced_stats(
            mlb_id, years=years_to_fetch
        )
    except Exception as e:
        logger.warning("seasonAdvanced failed for %s: %s", mlb_id, e)

    # Game logs — in sync mode fetch ALL historical years so the game log
    # tab shows data for every season, not just the current one.
    if fetch_all_years:
        fetch_years = sorted(years_with_data) if years_with_data else [year]
    else:
        # update mode: only refresh the current year's logs (fast)
        fetch_years = [year]

    log_groups = {}
    for y in fetch_years:
        try:
            log_groups[y] = get_game_logs(mlb_id, y)
        except Exception as e:
            logger.warning("gameLog failed for %s/%s: %s", mlb_id, y, e)

    # Next game -- skip for inactive (retired/released) players even during
    # a first-time backfill, since profile.team_id reflects their *last*
    # team and would otherwise show that team's schedule as "next game".
    next_game = None
    try:
        team_id = profile.get("team_id")
        if team_id and status_category != "inactive":
            next_game = get_next_game(team_id)
    except Exception as e:
        logger.warning("next-game failed for %s: %s", mlb_id, e)

    return {
        "pconf": pconf,
        "profile": profile,
        "status_category": status_category,
        "stats_groups": stats_groups,
        "adv_groups": adv_groups,
        "log_groups": log_groups,
        "next_game": next_game,
        "years_with_data": years_with_data,
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
            profile.get("current_team_level") or "Minors",
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
                        "fielding_pct": str(stat.get("fielding", "")),
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
                split.get("sport", {}).get("abbreviation", ""),
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

    # Update level/team
    if not profile.get("current_team_level") or not profile.get("current_team_name"):
        # Rank every raw sport_level spelling (incl. historical ones like
        # "A(Adv)" / "A(Short)") via the single level registry, so the "latest
        # level" pick orders pre-2021 rows correctly too.
        level_order_sql = " ".join(
            f"WHEN '{alias}' THEN {t.rank}"
            for t in TIERS
            for alias in t.aliases
        )
        cur.execute(
            f"SELECT sport_level, team_name FROM season_stats "
            f"WHERE player_mlb_id = ? "
            f"ORDER BY year DESC, CASE sport_level {level_order_sql} ELSE 50 END ASC "
            f"LIMIT 1",
            (mlb_id,),
        )
        latest = cur.fetchone()
        if latest:
            cur.execute(
                "UPDATE players SET level=?, team=? WHERE mlb_id=?",
                (latest[0] or "Minors", latest[1] or "N/A", mlb_id),
            )
    else:
        cur.execute(
            "UPDATE players SET level=?, team=? WHERE mlb_id=?",
            (
                profile.get("current_team_level") or "Minors",
                profile.get("current_team_name") or "N/A",
                mlb_id,
            ),
        )

    # Game logs
    for y, log_groups in bundle["log_groups"].items():
        for log_group in log_groups:
            if log_group.get("type", {}).get("displayName", "") != "gameLog":
                continue
            group_sport_level = log_group.get("sport", {}).get("abbreviation", "")
            for split in log_group.get("splits", []):
                game_date = split.get("date")
                game_pk = split.get("game", {}).get("gamePk")
                if not game_date or not game_pk:
                    continue
                # Prefer split-level sport, fall back to group-level
                split_sport_level = (
                    split.get("sport", {}).get("abbreviation", "")
                    or group_sport_level
                )
                cur.execute(
                    "INSERT INTO game_logs "
                    "(player_mlb_id, date, game_id, opponent, is_home, stats_json, sport_level) "
                    "VALUES (?,?,?,?,?,?,?) "
                    "ON CONFLICT(player_mlb_id, game_id) DO UPDATE SET "
                    " date=excluded.date, opponent=excluded.opponent, "
                    " is_home=excluded.is_home, stats_json=excluded.stats_json, "
                    " sport_level = CASE WHEN excluded.sport_level != '' "
                    "   THEN excluded.sport_level ELSE game_logs.sport_level END",
                    (
                        mlb_id,
                        game_date,
                        game_pk,
                        split.get("opponent", {}).get("name", "Unknown"),
                        1 if split.get("isHome") else 0,
                        dumps_json(split.get("stat", {})),
                        split_sport_level,
                    ),
                )

    # Next game snapshot
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur.execute(
        "UPDATE players SET next_game_json=?, next_game_updated_at=?, "
        "next_game_for_season=? WHERE mlb_id=?",
        (dumps_json(bundle["next_game"] or {}), now, year, mlb_id),
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
    synced_ids = players_with_existing_stats(conn)
    cached_is_active = get_cached_is_active(conn.cursor())

    # Players cached as is_active=False (the API's "active" flag, set the
    # last time their profile was fetched) have permanently left affiliated
    # ball and won't come back, so skip them entirely on subsequent runs --
    # no profile/status re-fetch, no further steps. Players cached as
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
            and cached_is_active.get(mlb_id) is False
            and not _is_first_sync(mlb_id, synced_ids)
        ):
            print(f"  skipped {pconf.get('name_tw', mlb_id)} (inactive, status cached)")
            continue
        players_to_fetch.append(pconf)

    total = len(players_to_fetch)
    print(
        f"{mode_label}: {total} players into {db_file} "
        f"(max {PLAYER_FETCH_WORKERS} parallel, all_years={fetch_all_years})"
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
        for i, future in enumerate(as_completed(future_to_pconf), 1):
            pconf = future_to_pconf[future]
            name = pconf.get("name_tw", pconf["mlb_id"])
            try:
                result = future.result()
                if result:
                    bundles.append(result)
                    if result.get("status_category") == "inactive":
                        if _is_first_sync(pconf["mlb_id"], synced_ids):
                            print(f"  [{i}/{total}] fetched {name} (inactive: first-time backfill)")
                        elif fetch_all_years:
                            print(f"  [{i}/{total}] fetched {name} (inactive: full re-sync)")
                        else:
                            print(f"  [{i}/{total}] fetched {name} (inactive: profile only)")
                    else:
                        print(f"  [{i}/{total}] fetched {name}")
                else:
                    print(f"  [{i}/{total}] skipped {name} (no profile)")
            except Exception as e:
                print(f"  [{i}/{total}] error {name}: {e}")
                logger.exception("Fetch failed for %s", name)

    # Phase 2: Write to DB sequentially
    for bundle in bundles:
        name = bundle["pconf"].get("name_tw", bundle["profile"].get("full_name"))
        try:
            _write_player_to_db(conn, bundle, year)
            print(f"  saved {name}")
        except Exception as e:
            print(f"  DB write error for {name}: {e}")
            logger.exception("DB write failed for %s", name)

    # After a full sync (not a single-player run), check for orphaned DB entries
    # that are no longer referenced by the current roster.
    if only_player is None:
        roster_ids = {p["mlb_id"] for p in parse_roster_from_file(roster_file)}
        warn_orphaned_players(conn, roster_ids)

    conn.close()
    print(f"{mode_label} complete")


def sync_database(
    db_path: str,
    roster_file: str,
    year: int,
    only_player: Optional[int] = None,
):
    """Full sync: fetch ALL historical years of stats + game logs for every player.

    Use this to build the database from scratch or ensure complete historical data.
    Slower than update_database because it fetches game logs for every season.
    """
    _run_pipeline(
        db_path=db_path,
        roster_file=roster_file,
        year=year,
        only_player=only_player,
        fetch_all_years=True,
        mode_label="Sync",
    )


def update_database(
    db_path: str,
    roster_file: str,
    year: int,
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
        year=year,
        only_player=only_player,
        fetch_all_years=False,
        mode_label="Update",
    )

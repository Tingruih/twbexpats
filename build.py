"""
Taiwan MLB Tracker — build pipeline.

Usage:
    python build.py sync                # full sync: fetch ALL years of data for ALL players
    python build.py statcast            # fetch playByPlay + compute Statcast aggregates
    python build.py refresh             # update stats & Statcast, then build site
    python build.py build               # generate static site from existing database
    python build.py all                 # refresh --full-history (first-time / backfill)

Commands:
    sync     Fetches yearByYear stats AND game logs for every historical season,
             retired players included. Use this the first time or to backfill
             complete game log history.
    statcast Fetches playByPlay for every un-processed game, extracts pitch-level
             data, and computes Statcast aggregates (Whiff%, arsenal, etc.) plus
             FIP / WAR / wRC+ / xWPCT. Run after sync; games whose pitch data is
             already cached in game_logs are not re-fetched.
    refresh  Three-step daily update pipeline:
               1. update_database  — yearByYear stats (all seasons) + current-year
                                     game logs only (fast path).
               2. sync_statcast    — fetch playByPlay for any new unprocessed games
                                     and recompute Statcast / FIP / expected stats.
               3. build_static_site — render HTML to the dist/ directory.
             Use this for daily/CI updates — requires an existing database.
    build    Reads the SQLite database and renders HTML to the dist/ directory.
    all      Same as ``refresh --full-history``.

Re-fetch rules (per-season data from external APIs):
    The current season (constants.SEASON_YEAR) is always re-fetched. A past
    season is fetched until it succeeds once and then reused; two flags force
    past seasons to be fetched again:

    --full-history      per-player history: game logs and seasonAdvanced
                        for every season, retired players, MLB
                        expectedStatistics and sabermetrics
                        (refresh / statcast; implied by sync and all)
    --update-constants  per-level league constants: MLB team pitching totals
                        (FIP constant / lgERA) and tjstats.ca park factors /
                        league constants (wRC+)
                        (statcast / refresh / build / all)

Options:
    python build.py sync     --player 678906   # single player only
    python build.py statcast --player 678906   # single player only
    python build.py refresh  --player 678906   # single player only
    python build.py build    --base-url /twbexpats/
    python build.py build    --site-url https://example.com/  # canonical/sitemap 網域
    python build.py refresh  --full-history      # re-fetch every past season
    python build.py refresh  --update-constants  # re-fetch past league constants
"""

import argparse
import logging
import sys

from site_builder.constants import SITE_URL
from site_builder.util.log import log_run_summary, setup_logging

logger = logging.getLogger(__name__)

SITE_URL_HELP = (
    "Public site URL for canonical/sitemap/JSON-LD (default: constants.SITE_URL; "
    "CI passes actions/configure-pages base_url)"
)


def cmd_sync(args):
    from site_builder.sync import sync_database

    sync_database(
        db_path=args.db,
        roster_file=args.roster,
        only_player=args.player,
    )


def cmd_build(args):
    from site_builder.render import build_static_site

    build_static_site(
        db_path=args.db,
        output_dir=args.output,
        base_url=args.base_url,
        site_url=args.site_url,
        roster_file=args.roster,
        update_constants=args.update_constants,
    )


def cmd_statcast(args):
    """Fetch playByPlay for all un-processed games and compute Statcast aggregates."""
    from site_builder.sync import sync_statcast

    sync_statcast(
        db_path=args.db,
        roster_file=args.roster,
        only_player=args.player,
        update_constants=args.update_constants,
        full_history=args.full_history,
    )


def cmd_refresh(args):
    """Three-step daily update: basic stats → Statcast → build."""
    from site_builder.sync import sync_database, update_database

    # --full-history 的球員資料階段就是 sync（全部年份 + 已退休球員）
    update_players = sync_database if args.full_history else update_database
    update_players(
        db_path=args.db,
        roster_file=args.roster,
        only_player=args.player,
    )
    cmd_statcast(args)
    cmd_build(args)


def cmd_all(args):
    if args.player is not None:
        logger.warning(
            "'all --player %s' only syncs one player.\n"
            "  sync and statcast will be restricted to that player, but build\n"
            "  renders all roster players. On a fresh database this means all\n"
            "  other player pages will be empty.\n"
            "  For a full first-time setup run: python build.py all (no --player).\n"
            "  For a single-player backfill run: python build.py sync --player <id>\n"
            "    then: python build.py statcast --player <id> --full-history\n"
            "    then: python build.py build",
            args.player,
        )
    args.full_history = True
    cmd_refresh(args)


def main():
    parser = argparse.ArgumentParser(
        description="Taiwan MLB Tracker — sync data & build static site",
    )
    sub = parser.add_subparsers(dest="command")

    # 各子命令共用的旗標組；每個子命令只掛它用得到的組
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default="data/tracker.sqlite3", help="SQLite path")
    common.add_argument(
        "--roster", default="src/data/roster.json", help="Roster JSON path"
    )

    player = argparse.ArgumentParser(add_help=False)
    player.add_argument(
        "--player", type=int, default=None,
        help="Single MLB ID only (also re-fetches a retired player)",
    )

    site = argparse.ArgumentParser(add_help=False)
    site.add_argument("--output", default="dist", help="Output directory")
    site.add_argument("--base-url", default="/", help="Site base URL (e.g. /repo/)")
    site.add_argument("--site-url", default=SITE_URL, help=SITE_URL_HELP)

    constants = argparse.ArgumentParser(add_help=False)
    constants.add_argument(
        "--update-constants",
        action="store_true",
        help="Re-fetch past-season league constants (MLB team pitching totals "
        "for FIP/lgERA, tjstats.ca park factors/league constants for wRC+) "
        "instead of reusing the cached SQLite values; the current season's "
        "MLB constants are always re-fetched",
    )

    history = argparse.ArgumentParser(add_help=False)
    history.add_argument(
        "--full-history",
        action="store_true",
        help="Re-fetch every past season of per-player data (game logs, "
        "seasonAdvanced, retired players, expectedStatistics, sabermetrics) "
        "instead of only the current season plus never-fetched seasons",
    )

    sub.add_parser(
        "sync",
        parents=[common, player],
        help="Full sync: fetch ALL years of stats + game logs for every player",
    ).set_defaults(func=cmd_sync)

    sub.add_parser(
        "statcast",
        parents=[common, player, constants, history],
        help="Fetch playByPlay for un-processed games and compute Statcast aggregates",
    ).set_defaults(func=cmd_statcast)

    sub.add_parser(
        "refresh",
        parents=[common, player, site, constants, history],
        help="Update stats + Statcast, then build the static site (daily pipeline)",
    ).set_defaults(func=cmd_refresh)

    sub.add_parser(
        "build",
        parents=[common, site, constants],
        help="Generate static HTML site from existing database",
    ).set_defaults(func=cmd_build)

    sub.add_parser(
        "all",
        parents=[common, player, site, constants],
        help="refresh --full-history (first-time / backfill pipeline)",
    ).set_defaults(func=cmd_all)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # site_builder 內的進度訊息走 logger.info；未設定 handler 時 logging 只會
    # 透過 lastResort 輸出 WARNING 以上，進度訊息會全部消失，因此在 CLI 進入點統一設定。
    setup_logging()
    try:
        args.func(args)
    finally:
        # 中途例外也要印摘要；exit code 不受 WARNING 數量影響（API 暫時失敗時 DB 保留舊值，下次重抓）
        log_run_summary()


if __name__ == "__main__":
    main()

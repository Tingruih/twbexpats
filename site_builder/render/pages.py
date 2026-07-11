"""Static site builder: reads SQLite data and renders Jinja2 templates to HTML."""

import datetime
import re
import shutil
import sqlite3
from pathlib import Path

from ..constants import DEFAULT_ROSTER_FILE, MIN_WRC_YEAR, STATIC_DIR, WRC_LEVELS
from ..db.bundles import load_player_bundle
from ..db.play_videos import load_video_map
from ..db.players import warn_orphaned_players
from ..db.schema import init_db
from ..graph.season_trend import (
    BATTER_TREND_STAT_OPTIONS,
    PITCHER_TREND_STAT_OPTIONS,
    build_batter_trend_by_year,
    build_pitcher_trend_by_year,
)
from ..levels import level_rank
from ..roster import is_active_player, parse_roster_from_file
from ..stats.advanced.wrc_plus import annotate_wrc_plus
from ..stats.combine import combine_statcast_dicts
from ..stats.core.annotate import annotate_computed_stats
from ..stats.core.career import (
    compute_career,
    compute_season_combined,
    compute_year_groups,
)
from ..stats.core.selectors import has_appearance, highest_level_row
from ..util.dates import TW_TZ
from ..util.units import height_to_cm, lbs_to_kg
from .env import create_jinja_env
from .pitch_log import write_pitch_log_files
from .seo import (
    RETIRED_SEO_DESCRIPTION,
    RETIRED_SEO_TITLE,
    SITE_DESCRIPTION,
    SITE_TITLE,
    index_structured_data,
    player_canonical_path,
    player_description,
    player_display_name,
    player_structured_data,
    write_robots,
    write_sitemap,
)


def _pick_display_stat(stats_current, player):
    """Pick the stat row to show on the player card / detail hero strip.

    Priority:
    1. Exact team match — handles players who've been at multiple teams at
       the same level (e.g. demoted back to a different AA club).
    2. Current level match — handles demotions where player.level has changed.
    3. Highest level with appearances — fallback / original behaviour for
       promotions where the player hasn't appeared at the new level yet.

    ``stats_current`` must already be filtered to the target year + has_appearance,
    and sorted by level_order ascending (highest level first).
    """
    if not stats_current:
        return None
    # 1. Exact current-team match
    for s in stats_current:
        if s.team_name == player.team:
            return s
    # 2. Current level match (takes the highest-level team at that level)
    for s in stats_current:
        if s.sport_level == player.level:
            return s
    # 3. Fallback: highest level played with appearances
    return stats_current[0]


_CSS_IMPORT_RE = re.compile(r"""^\s*@import\s+["']([^"']+)["']\s*;\s*$""")


def _inline_css_imports(css_path: Path, seen=None) -> str:
    """Recursively inline a CSS file's ``@import`` statements.

    Returns the flattened stylesheet with every ``@import "x.css";`` replaced by
    the referenced file's (also-flattened) contents, preserving declaration
    order so the cascade is identical.  Each file is inlined at most once, which
    guards against accidental import cycles.
    """
    if seen is None:
        seen = set()
    css_path = css_path.resolve()
    if css_path in seen or not css_path.is_file():
        return ""
    seen.add(css_path)
    parts = []
    for line in css_path.read_text(encoding="utf-8").splitlines(keepends=True):
        match = _CSS_IMPORT_RE.match(line)
        if match:
            child = css_path.parent / match.group(1)
            parts.append(_inline_css_imports(child, seen))
        else:
            parts.append(line)
    return "".join(parts)


def _bundle_css(static_out_dir: Path):
    """Flatten ``style.css``'s ``@import`` graph into a single file.

    The source CSS stays modular (one concern per file) for maintainability, but
    the CSS ``@import`` chain is render-blocking *and* serial — the browser must
    download & parse ``style.css`` before it even discovers the ~24 imported
    files, then fetches them one after another.  Inlining them at build time
    turns that waterfall into a single request without changing the source.
    """
    entry = static_out_dir / "css" / "style.css"
    if not entry.is_file():
        return
    flattened = _inline_css_imports(entry)
    entry.write_text(flattened, encoding="utf-8")


def build_static_site(
    db_path: str,
    year: int,
    output_dir: str,
    base_url: str = "/",
    roster_file: str | None = None,
    update_constants: bool = False,
):
    """Build the complete static site from SQLite data.

    Only renders players whose MLB IDs appear in ``roster_file``.  If
    ``roster_file`` is None the default roster path is used so stale DB
    entries left over from ID changes are never published to the site.

    ``update_constants`` forces a fresh scrape of tjstats.ca for the wRC+
    park-factor/league-constant cache, overwriting any cached values for the
    seasons involved (see ``db.tjstats_cache``).
    """
    if roster_file is None:
        roster_file = str(DEFAULT_ROSTER_FILE)

    roster_ids: set[int] = {
        p["mlb_id"] for p in parse_roster_from_file(roster_file)
    }

    out_dir = Path(output_dir).resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Copy static files from src/static
    if STATIC_DIR.is_dir():
        shutil.copytree(STATIC_DIR, out_dir / "static")
        # Flatten the CSS @import waterfall into a single style.css request.
        _bundle_css(out_dir / "static")

    env = create_jinja_env(base_url=base_url)
    normalized_base_url = env.globals["base_url"]
    absolute_url = env.globals["absolute_url"]

    # Build timestamp in UTC+8
    now_utc8 = datetime.datetime.now(TW_TZ)
    env.globals["build_time"] = now_utc8.strftime("%Y-%m-%d %H:%M")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Idempotent (CREATE TABLE IF NOT EXISTS only) — ensures the TJStats
    # cache tables exist even when `build` runs against a database created
    # before they were added, without touching any existing data.
    init_db(conn)

    # Verify the database has been populated by a prior sync
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='players'")
    if not cur.fetchone():
        conn.close()
        raise SystemExit(
            f"Error: database '{db_path}' has no 'players' table. "
            "Run 'python build.py sync' first."
        )

    if roster_ids:
        placeholders = ",".join("?" * len(roster_ids))
        cur.execute(
            f"SELECT * FROM players WHERE mlb_id IN ({placeholders}) ORDER BY name_en",
            list(roster_ids),
        )
    else:
        cur.execute("SELECT * FROM players ORDER BY name_en")
    rows = cur.fetchall()

    if roster_ids:
        warn_orphaned_players(conn, roster_ids)

    bundles = [load_player_bundle(cur, row) for row in rows]
    videos_by_game = load_video_map(cur)

    # Compute TJBat+ (wRC+) for qualifying batters before any page rendering
    # so both the active-player and retired-player detail pages (which both
    # read from `bundles`) see the annotated wrc_plus/wrc_plus_calc fields.
    annotate_wrc_plus(bundles, conn, force_refresh=update_constants)

    # ── Split active vs. retired ──
    # Active = has a season_stats row for `year` OR a transaction dated this
    # year. Everyone else is rendered on the dedicated /retired page.
    active_bundles = []
    retired_bundles = []
    for bundle in bundles:
        player, stats, _logs = bundle
        if is_active_player(player, stats, year):
            active_bundles.append(bundle)
        else:
            retired_bundles.append(bundle)

    # ── Index page (active players only) ──
    index_template = env.get_template("index.j2")
    player_data = []
    for player, stats, logs in active_bundles:
        stats_current = [s for s in stats if s.year == year and has_appearance(s)]
        stats_current.sort(key=lambda x: x.level_order)
        # Find the most recent game date for sorting
        last_game_date = None
        for log in logs:
            if log.date:
                last_game_date = log.date
                break  # logs are already sorted descending
        # Year that `player.level` (the badge) corresponds to: the most recent
        # season row (stats are sorted -year, level_order). Drives era-aware
        # display so e.g. a 2026 High-A badge reads "A+".
        level_year = stats[0].year if stats else year
        player_data.append(
            {
                "player": player,
                "stat": _pick_display_stat(stats_current, player),
                "level_year": level_year,
                "last_game_date": last_game_date,
            }
        )
    player_data.sort(key=lambda x: level_rank(x["player"].level))

    index_html = index_template.render(
        player_data=player_data,
        current_sort="level",
        default_season_year=year,
        nav_active="index",
        seo_title=SITE_TITLE,
        seo_description=SITE_DESCRIPTION,
        canonical_url=absolute_url(""),
        og_type="website",
        structured_data=index_structured_data(absolute_url, player_data),
    )
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")

    # ── Retired page ──
    # Cards default to all-years/all-levels combined career stats, and the
    # level badge shows the highest level the player ever reached.
    retired_template = env.get_template("retired.j2")
    retired_data = []
    for player, stats, logs in retired_bundles:
        career = compute_career(stats, level_filter=None)
        # Badge shows the highest level ever reached, displayed with the
        # period-accurate name for the year it was reached (e.g. a 2018 High-A
        # peak reads "A(Adv)", not "A+").
        best = highest_level_row(stats)
        badge_level = best.sport_level if best else None
        badge_year = best.year if best else None
        last_game_date = next((log.date for log in logs if log.date), None)
        retired_data.append(
            {
                "player": player,
                "stat": career,
                "badge_level": badge_level,
                "badge_year": badge_year,
                "last_game_date": last_game_date,
            }
        )
    # Highest level first; ties broken by most recent appearance.
    retired_data.sort(
        key=lambda x: (
            level_rank(x["badge_level"]),
            -(x["last_game_date"].toordinal() if x["last_game_date"] else 0),
        )
    )

    retired_html = retired_template.render(
        player_data=retired_data,
        nav_active="retired",
        seo_title=RETIRED_SEO_TITLE,
        seo_description=RETIRED_SEO_DESCRIPTION,
        canonical_url=absolute_url("retired/"),
        og_type="website",
    )
    # Write as retired/index.html (not retired.html) so the extension-less
    # /retired URL resolves on both GitHub Pages and a plain http.server
    # (which redirects /retired → /retired/ → index.html).
    retired_dir = out_dir / "retired"
    retired_dir.mkdir(parents=True, exist_ok=True)
    (retired_dir / "index.html").write_text(retired_html, encoding="utf-8")

    # ── Player detail pages ──
    player_template = env.get_template("player_detail.j2")
    retired_ids = {p.mlb_id for p, _, _ in retired_bundles}
    for player, all_stats, all_logs in bundles:
        is_retired = player.mlb_id in retired_ids
        selected_year = year

        logs_by_year = {}
        for log in all_logs:
            if not log.date:
                continue
            y = log.date.year
            logs_by_year.setdefault(y, []).append(log)

        for y in logs_by_year:
            logs_by_year[y].sort(key=lambda g: g.date, reverse=True)

        available_log_years = sorted(logs_by_year.keys(), reverse=True)
        game_logs = logs_by_year.get(selected_year, [])

        # Chart data
        if player.is_pitcher:
            player_trend_by_year = build_pitcher_trend_by_year(logs_by_year)
            trend_stat_options = PITCHER_TREND_STAT_OPTIONS
        else:
            player_trend_by_year = build_batter_trend_by_year(logs_by_year)
            trend_stat_options = BATTER_TREND_STAT_OPTIONS

        all_stats = annotate_computed_stats(all_stats)
        stats_year_groups = compute_year_groups(all_stats)

        # Career aggregations
        milb_career = compute_career(all_stats, level_filter="milb")
        mlb_career = compute_career(all_stats, level_filter="mlb")
        total_career = compute_career(all_stats, level_filter=None)

        # Next game validity
        snapshot_valid = (
            isinstance(player.next_game_json, dict)
            and bool(player.next_game_json)
            and (
                player.next_game_for_season in (None, year)
                or (player.next_game_for_season or 0) >= datetime.date.today().year
            )
        )
        next_game = player.next_game_json if snapshot_valid else None

        next_game_updated_at = None
        if player.next_game_updated_at:
            try:
                dt = datetime.datetime.fromisoformat(player.next_game_updated_at)
                next_game_updated_at = dt.strftime("%Y-%m-%d %H:%M UTC")
            except ValueError:
                next_game_updated_at = player.next_game_updated_at

        # Current season stats
        stats_current = [s for s in all_stats if s.year == year and has_appearance(s)]
        stats_current.sort(key=lambda x: x.level_order)
        latest_team_stat = _pick_display_stat(stats_current, player)
        season_combined = (
            compute_season_combined(all_stats, year) if stats_current else None
        )

        # Fielding data
        all_fielding = []
        for s in all_stats:
            if s.fielding_json:
                for f in s.fielding_json:
                    entry = dict(f)
                    entry["year"] = s.year
                    entry["team_name"] = s.team_name
                    entry["sport_level"] = s.sport_level
                    all_fielding.append(entry)

        # ── Statcast context ──
        write_pitch_log_files(
            logs_by_year,
            out_dir,
            normalized_base_url,
            player.mlb_id,
            videos_by_game=videos_by_game,
        )

        # Season-level Statcast data keyed by year → list of {sport_level, team_name, sc}
        statcast_by_year: dict[int, list] = {}
        for s in all_stats:
            raw_sc = s.get("statcast")
            if raw_sc:
                sc = dict(raw_sc)
                if player.is_pitcher:
                    # pitch_movement is already computed per level by the statcast
                    # pipeline and stored on this row's statcast dict; just ensure
                    # the key exists for older rows predating that field.
                    sc.setdefault("pitch_movement", {})
                statcast_by_year.setdefault(s.year, []).append({
                    "sport_level": s.sport_level,
                    "team_name": s.team_name,
                    "sc": sc,
                    "stat": s,
                })
            elif (
                not player.is_pitcher
                and s.year >= MIN_WRC_YEAR
                and s.sport_level in WRC_LEVELS
            ):
                # No real Statcast data for this row, but it may still carry a
                # computed wRC+ (annotate_wrc_plus, above). Inject a near-empty
                # entry so the Statcast Overview section can still surface it
                # instead of silently dropping the year.
                has_wrc = (
                    s.get("wrc_plus_calc") if s.sport_level == "MLB" else s.get("wrc_plus")
                ) is not None
                if has_wrc:
                    statcast_by_year.setdefault(s.year, []).append({
                        "sport_level": s.sport_level,
                        "team_name": s.team_name,
                        "sc": {},
                        "stat": s,
                    })
        # For years with multiple levels, prepend a combined summary entry so the
        # summary row in the template can display real weighted-average values.
        for yr_key, yr_entries in statcast_by_year.items():
            if len(yr_entries) > 1:
                combined_sc = combine_statcast_dicts(yr_entries)
                yr_entries.insert(0, {
                    "sport_level": "_combined",
                    "team_name": "合計",
                    "sc": combined_sc,
                    "stat": None,
                })

        statcast_available = bool(statcast_by_year)

        # Determine available Statcast years (sorted desc)
        available_statcast_years = sorted(statcast_by_year.keys(), reverse=True)

        context = {
            "player": player,
            "all_stats": all_stats,
            "stats_year_groups": stats_year_groups,
            "years": player.available_years,
            "selected_year": selected_year,
            "game_logs": game_logs,
            "logs_by_year": logs_by_year,
            "available_log_years": available_log_years,
            "player_trend_by_year": player_trend_by_year,
            "trend_stat_options": trend_stat_options,
            "is_pitcher": player.is_pitcher,
            "milb_career": milb_career,
            "mlb_career": mlb_career,
            "total_career": total_career,
            "next_game": next_game,
            "next_game_updated_at": next_game_updated_at,
            "transactions": player.transactions_json or [],
            "all_fielding": all_fielding,
            "height_cm": height_to_cm(player.height),
            "weight_kg": lbs_to_kg(player.weight),
            "latest_team_stat": latest_team_stat,
            "season_combined": season_combined,
            "statcast_by_year": statcast_by_year,
            "statcast_available": statcast_available,
            "available_statcast_years": available_statcast_years,
            "seo_title": f"{player_display_name(player)} 數據 | TwbExpats",
            "seo_description": player_description(player),
            "canonical_url": absolute_url(player_canonical_path(player, is_retired)),
            "og_type": "profile",
            "structured_data": player_structured_data(absolute_url, player, is_retired),
            "nav_active": "retired" if is_retired else "index",
        }

        html = player_template.render(**context)
        if is_retired:
            player_dir = out_dir / "retired" / "player" / str(player.mlb_id)
        else:
            player_dir = out_dir / "player" / str(player.mlb_id)
        player_dir.mkdir(parents=True, exist_ok=True)
        (player_dir / "index.html").write_text(html, encoding="utf-8")

    # ── 404 page ──
    template_404 = env.get_template("404.j2")
    (out_dir / "404.html").write_text(template_404.render(), encoding="utf-8")

    # ── Search engine discovery files ──
    sitemap_urls = [
        {
            "loc": absolute_url(""),
            "lastmod": now_utc8.date().isoformat(),
        },
        {
            "loc": absolute_url("retired/"),
            "lastmod": now_utc8.date().isoformat(),
        },
    ]
    for player, _, logs in bundles:
        last_game_date = next((log.date for log in logs if log.date), None)
        sitemap_urls.append(
            {
                "loc": absolute_url(player_canonical_path(player, player.mlb_id in retired_ids)),
                "lastmod": (last_game_date or now_utc8.date()).isoformat(),
            }
        )
    write_sitemap(out_dir, sitemap_urls)
    write_robots(out_dir, absolute_url("sitemap.xml"))

    # ── GitHub Pages marker ──
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    conn.close()
    print(f"Built {len(bundles)} player pages + index to {out_dir}")

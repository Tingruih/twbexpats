"""Static site builder: reads SQLite data and renders Jinja2 templates to HTML."""

import datetime
import re
import shutil
import sqlite3
from pathlib import Path

from ..constants import DEFAULT_ROSTER_FILE, STATIC_DIR
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
from ..league_constant.batting import BattingConstants, publishes_constants
from ..levels import level_rank, resolve_tier
from ..roster import is_active_player, parse_roster_from_file
from ..stats.advanced.wrc_plus import annotate_wrc_plus
from ..stats.advanced.xwpct import compute_xwpct
from ..stats.batter_statcast import compute_batter_statcast
from ..stats.core.aggregate import aggregate_stats
from ..stats.core.annotate import annotate_computed_stats, annotate_row
from ..stats.core.career import (
    compute_career,
    compute_season_combined,
    compute_year_groups,
)
from ..stats.core.innings import ip_to_outs
from ..stats.core.selectors import has_appearance, highest_level_row
from ..stats.pitcher_statcast import compute_pitcher_statcast
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


# Per-pitch-type / chart payloads that the previous weighted-average combiner
# wrote unconditionally, whether or not they meant anything for the player's
# role.  ``compute_*_statcast()`` only emits the keys its role actually has, so
# the pooled "_combined" dict is padded back out to the same key set: templates
# that reach for the other role's key keep getting an empty container instead of
# a Jinja ``Undefined`` (which raises the moment anything iterates it).
_COMBINED_EMPTY_DEFAULTS = {
    "pitch_arsenal": list,
    "pitch_outcomes": list,
    "vs_pitch_types": list,
    "vs_pitch_groups": list,
    "pitch_usage_by_count": dict,
    "pitch_group_usage_by_count": dict,
    "pitcher_bat_side_splits": dict,
    "batter_pitch_hand_splits": dict,
    "pitch_plinko": dict,
    "pitch_movement": dict,
}


def _statcast_row_qualifies(player, s) -> bool:
    """Whether a season_stats row belongs in the Statcast section at all.

    Real Statcast data always qualifies.  A batter row without it still does
    when it carries a computed wRC+ (see ``annotate_wrc_plus``), so the
    Statcast Overview can surface that value instead of dropping the year.
    """
    if s.get("statcast"):
        return True
    if player.is_pitcher or not publishes_constants(s.sport_level, s.year):
        return False
    field = "wrc_plus_calc" if s.sport_level == "MLB" else "wrc_plus"
    return s.get(field) is not None


def _first_not_none(rows, field):
    """First non-None value of *field* across *rows* (None when there is none)."""
    for row in rows:
        value = row.get(field)
        if value is not None:
            return value
    return None


def _merge_level_rows(rows):
    """Collapse one (year, level) group's season_stats rows into a single row.

    A player traded inside the same level gets one season_stats row per club,
    and every one of them stores the *same* whole-season Statcast aggregate —
    so the Statcast half needs no merging at all.  The season_stats-derived
    columns do:

    - counting stats are re-summed and their rates recomputed (``aggregate_stats``
      + ``annotate_row``);
    - FIP is IP-weighted.  FIP = numerator/IP + C, so an IP-weighted mean is
      exactly "sum the numerator, IP-weight C" — identical to recomputing from
      pooled pitches when the clubs share a league, and off only by the spread
      in C when they don't;
    - xWPCT is re-derived from the merged FIP rather than averaged, against
      the group's lg_era.  lg_era is one number for the whole level, so every
      row in the group carries the same value and it is simply picked up from
      whichever row has it (same treatment as war/xfip below) — IP-weighting
      a constant would be meaningless, and re-resolving it from
      league_constant would be a second lookup for a number already stored;
    - whole-season values that only ever live on one row of the group (WAR,
      xwOBA, API wRC+) are picked up wherever they happen to sit.
    """
    if len(rows) == 1:
        return rows[0]

    merged = aggregate_stats(rows)
    merged["year"] = rows[0].year
    merged["sport_level"] = rows[0].sport_level
    merged["level_order"] = rows[0].level_order
    merged["team_name"] = " / ".join(r.team_name for r in rows if r.team_name)
    merged["np"] = merged.get("pitches")
    annotate_row(merged)

    lg_era = _first_not_none(rows, "lg_era")
    merged["lg_era"] = lg_era

    fip_weighted = 0.0
    total_outs = 0
    for row in rows:
        fip = row.get("fip")
        outs = ip_to_outs(row.get("ip"))
        if fip is not None and outs:
            fip_weighted += fip * outs
            total_outs += outs
    if total_outs:
        fip = fip_weighted / total_outs
        merged["fip"] = round(fip, 2)
        merged["xwpct"] = compute_xwpct(fip, lg_era)

    for field in ("war", "xfip", "expected", "saber"):
        merged[field] = _first_not_none(rows, field)

    # wRC+：API 的整季合計值（只有 MLB 有，且只寫在該組其中一列）直接取用；
    # 自算值取 annotate_wrc_plus() 以合併後打擊數據重算的 group 值——把各隊的
    # wRC+ 平均是錯的，wOBA 是比率，必須先加總計數再重算。
    if rows[0].sport_level == "MLB":
        merged["wrc_plus"] = _first_not_none(rows, "wrc_plus")
        merged["wrc_plus_calc"] = _first_not_none(rows, "wrc_plus_calc_group")
    else:
        merged["wrc_plus"] = _first_not_none(rows, "wrc_plus_group")

    return merged


def _pooled_year_pitches(logs) -> dict[int, list[dict]]:
    """``{year: [pitch, ...]}`` pooled across every level played that year.

    Reuses the pitch dicts ``load_player_bundle`` already parsed into memory for
    the pitch-log pages, so pooling costs no extra DB read and no extra JSON
    parse — only the aggregation pass itself.
    """
    by_year: dict[int, list[dict]] = {}
    for log in logs:
        if not log.date or not log.pitches_json:
            continue
        by_year.setdefault(log.date.year, []).extend(log.pitches_json)
    return by_year


def _build_statcast_entries(player, stats, logs) -> dict[int, list]:
    """Season Statcast entries keyed by year.

    Each entry is ``{sport_level, team_name, sc, stat}``.  Level rows are
    deduplicated by (year, tier) — mid-season trades inside one level would
    otherwise print the same season aggregate once per club (and emit duplicate
    DOM ids) — and merged by :func:`_merge_level_rows`.

    A year spanning 2+ levels also gets a ``_combined`` entry whose ``sc`` is
    that year's raw pitches pooled across every level, run through the *same*
    ``compute_*_statcast()`` the per-level rows use.  Never a weighted average
    of already-aggregated values: each column has its own denominator, so one
    shared weight cannot be right for all of them, and a percentile like EV90
    cannot be recovered by any weighting at all.  A single-level year gets no
    combined entry.

    The ``_combined`` sentinel and its position at the head of the year's list
    are the contract the arsenal / plinko / movement blocks read; the three
    summary tables move it to the end of the year themselves.
    """
    rows_by_year_tier: dict[int, dict[str, list]] = {}
    for s in stats:
        tier = resolve_tier(s.sport_level)
        tier_key = tier.key if tier else s.sport_level
        rows_by_year_tier.setdefault(s.year, {}).setdefault(tier_key, []).append(s)

    pooled: dict[int, list[dict]] | None = None
    statcast_by_year: dict[int, list] = {}

    for year, by_tier in rows_by_year_tier.items():
        entries = []
        for rows in by_tier.values():
            if not any(_statcast_row_qualifies(player, r) for r in rows):
                continue
            sc = dict(_first_not_none(rows, "statcast") or {})
            if player.is_pitcher:
                # pitch_movement is already computed per level by the statcast
                # pipeline and stored on this row's statcast dict; just ensure
                # the key exists for older rows predating that field.
                sc.setdefault("pitch_movement", {})
            merged = _merge_level_rows(rows)
            entries.append({
                "sport_level": merged.sport_level,
                "team_name": merged.team_name,
                "sc": sc,
                "stat": merged,
            })
        if not entries:
            continue
        entries.sort(key=lambda e: level_rank(e["sport_level"]))

        if len(entries) > 1:
            if pooled is None:
                pooled = _pooled_year_pitches(logs)
            compute = (
                compute_pitcher_statcast if player.is_pitcher
                else compute_batter_statcast
            )
            combined_sc = compute(pooled.get(year, []))
            for key, empty in _COMBINED_EMPTY_DEFAULTS.items():
                combined_sc.setdefault(key, empty())
            entries.insert(0, {
                "sport_level": "_combined",
                "team_name": "合計",
                "sc": combined_sc,
                "stat": None,
            })
        statcast_by_year[year] = entries

    return statcast_by_year


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
    seasons involved (see ``league_constant.batting``).
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
    annotate_wrc_plus(
        bundles, BattingConstants(conn, force_refresh=update_constants).for_level
    )

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

        # Season-level Statcast entries keyed by year (one row per level, plus a
        # pooled "_combined" entry for years spanning 2+ levels).
        statcast_by_year = _build_statcast_entries(player, all_stats, all_logs)
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

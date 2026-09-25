"""Static site builder: reads SQLite data and renders Jinja2 templates to HTML."""

import copy
import datetime
import logging
import re
import shutil
import sqlite3
from pathlib import Path

from markupsafe import Markup

from ..constants import DEFAULT_ROSTER_FILE, SEASON_YEAR, SITE_URL, STATIC_DIR
from ..db.bundles import load_player_bundle, load_role_game_logs
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
from ..levels import COMBINED_LEVEL, is_mlb, level_rank
from ..positions import BATTER, PITCHER, ROLES, primary_role, project_role, role_field
from ..roster import is_active_player, parse_roster_from_file
from ..stats.advanced.wrc_plus import annotate_wrc_plus
from ..stats.advanced.xwpct import compute_xwpct
from ..stats.batter_statcast import compute_batter_statcast
from ..stats.core.aggregate import aggregate_stats
from ..stats.core.annotate import annotate_computed_stats, annotate_row
from ..stats.core.career import (
    compute_career,
    compute_year_groups,
)
from ..stats.core.innings import ip_to_outs
from ..stats.core.selectors import appeared_roles, has_appearance, highest_level_row
from ..stats.pitcher_statcast import compute_pitcher_statcast
from ..util.dates import TW_TZ
from ..util.numbers import safe_int
from ..util.units import height_to_cm, lbs_to_kg
from .env import create_jinja_env
from .pitch_log import write_pitch_log_files
from .urls import RETIRED_INDEX_PATH, player_page_path
from .seo import (
    RETIRED_SEO_DESCRIPTION,
    RETIRED_SEO_TITLE,
    SITE_DESCRIPTION,
    SITE_TITLE,
    index_structured_data,
    player_description,
    player_display_name,
    player_structured_data,
    write_robots,
    write_sitemap,
)

logger = logging.getLogger(__name__)

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


def _statcast_row_qualifies(is_pitcher: bool, s) -> bool:
    """Whether a season_stats row belongs in the Statcast section at all.

    Real Statcast data always qualifies.  A batter row without it still does
    when it carries a computed wRC+ (see ``annotate_wrc_plus``), so the
    Statcast Overview can surface that value instead of dropping the year.
    """
    if s.get("statcast"):
        return True
    if is_pitcher or not publishes_constants(s.sport_level, s.year):
        return False
    field = "wrc_plus_calc" if is_mlb(s.sport_level) else "wrc_plus"
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
    - whole-season values (WAR, xFIP, API wRC+, xwOBA) are identical on every
      MLB row of the year (``sync/advanced.py`` writes the season-total
      sabermetrics to each club's row), so any non-null one is taken.
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
        # 各列存的是未捨入 FIP（sync/advanced.py），加權結果同樣不捨入，由模板顯示時捨入
        fip = fip_weighted / total_outs
        merged["fip"] = fip
        merged["xwpct"] = compute_xwpct(fip, lg_era)

    for field in ("war", "xfip", "expected", "saber"):
        merged[field] = _first_not_none(rows, field)

    # wRC+：API 的整季合計值（只有 MLB 有，該年每一隊的列都相同）直接取用；
    # 自算值取 annotate_wrc_plus() 以合併後打擊數據重算的 group 值——把各隊的
    # wRC+ 平均是錯的，wOBA 是比率，必須先加總計數再重算。
    if is_mlb(rows[0].sport_level):
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
        if not log.date or not log.pitches_json or log.is_postseason:
            continue
        by_year.setdefault(log.date.year, []).extend(log.pitches_json)
    return by_year


def _build_statcast_entries(is_pitcher: bool, stats, logs) -> dict[int, list]:
    """Season Statcast entries keyed by year.

    ``is_pitcher`` 是「這個檢視」的角色，不是球員的主要守位：雙角色球員的
    次要角色檢視也走這裡（見 :func:`_build_role_view`）。

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
        rows_by_year_tier.setdefault(s.year, {}).setdefault(s.sport_level, []).append(s)

    pooled: dict[int, list[dict]] | None = None
    statcast_by_year: dict[int, list] = {}

    for year, by_tier in rows_by_year_tier.items():
        entries = []
        for rows in by_tier.values():
            if not any(_statcast_row_qualifies(is_pitcher, r) for r in rows):
                continue
            sc = dict(_first_not_none(rows, "statcast") or {})
            if is_pitcher:
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
                compute_pitcher_statcast if is_pitcher
                else compute_batter_statcast
            )
            combined_sc = compute(pooled.get(year, []))
            for key, empty in _COMBINED_EMPTY_DEFAULTS.items():
                combined_sc.setdefault(key, empty())
            entries.insert(0, {
                "sport_level": COMBINED_LEVEL,
                "team_name": "合計",
                "sc": combined_sc,
                "stat": None,
            })
        statcast_by_year[year] = entries

    return statcast_by_year


def _page_roles(player, stats) -> list[str]:
    """球員頁要提供的角色檢視，主要角色在前。

    只有投打兩個角色都有出賽紀錄（``appeared_roles``）才回傳兩個角色、頁面
    才出現投手/打者切換；其餘球員只有主要角色，頁面輸出與拆分前相同。
    """
    primary = primary_role(player.position)
    appeared = set()
    for row in stats:
        appeared |= appeared_roles(row)
    if len(appeared) < len(ROLES):
        return [primary]
    return [primary] + [r for r in ROLES if r != primary]


def _row_in_role(row, role: str) -> bool:
    """某列 season_stats 是否列在 ``role`` 的檢視裡。``row`` 必須是投影前的原始列。

    先看 ``appeared_roles``（打擊 PA、投球 BF/IP）。都沒有時退回看該角色自己的
    出賽數（``gp`` / ``p_gp``）：只守備沒打席的代守（如 2021 林子偉在雙城的 1 場）
    只屬於打擊 group，不該在投手檢視多出一整排空白。兩個角色出賽數也都沒有
    （登錄在隊上但沒上場）才兩個檢視都保留，跟單一角色球員頁的行為一致。
    """
    roles = appeared_roles(row)
    if roles:
        return role in roles
    played = {r for r in ROLES if (row.get(role_field(r, "gp")) or 0) > 0}
    return role in played or not played


def _logs_in_role(logs_by_role: dict, role: str) -> list:
    """``role`` 檢視要列的逐場紀錄（``logs_by_role``：角色 → 該角色的 game_logs）。

    每場比賽把兩個角色的 gameLog split 合成一列，交給 :func:`_row_in_role` 判斷，
    規則與成績表的列一致。gameLog API 對球員有投球的每一場都會另外回一筆
    hitting split（``gamesPlayed`` 1、``plateAppearances`` 0 等全為 0），不經過這層
    判斷的話，打者檢視會多出這些沒上場打擊的比賽（沒有逐球資料，也會讓年份/層級
    選單多出成績表沒有的選項）。只代守、代跑的野手當場沒有投球 split，仍留在打者檢視。
    """
    box_by_game: dict = {}
    for r, logs in logs_by_role.items():
        for log in logs:
            box_by_game.setdefault(log.game_id, {})[r] = log.stats_json

    def in_role(game_id) -> bool:
        box = box_by_game[game_id]
        # gameLog 端點 stats[].splits[].stat（見 docs/data_sources.md）；
        # 該場沒有這個角色的 split 時為空 dict，下面的欄位都取到 None
        hitting = box.get(BATTER, {})
        pitching = box.get(PITCHER, {})
        row = {
            "pa": safe_int(hitting.get("plateAppearances")),
            "bf": safe_int(pitching.get("battersFaced")),
            "ip": pitching.get("inningsPitched"),
            role_field(BATTER, "gp"): safe_int(hitting.get("gamesPlayed")),
            role_field(PITCHER, "gp"): safe_int(pitching.get("gamesPlayed")),
        }
        return _row_in_role(row, role)

    return [log for log in logs_by_role[role] if in_role(log.game_id)]


def _fielding_in_role(fielding: list, role: str) -> list:
    """``role`` 檢視要列的守備列：依該列守位（``stats[].splits[].position.abbreviation``）
    對應的角色分到投手或打者檢視（``P`` 歸投手，其餘含 ``DH`` 歸打者）。"""
    return [f for f in fielding if primary_role(f.get("position")) == role]


def _build_role_view(stats, logs, role: str, player, year: int,
                     fielding: list, hero_fallback: bool = False) -> dict:
    """一個角色檢視（投手或打者）的樣板變數。

    ``stats`` 必須已經投影到 ``role``（``positions.project_role``），``logs`` 必須
    只含該角色的 game_logs，``fielding`` 必須只含該角色的守備列。回傳的 key 就是
    樣板裡隨角色變動的那些變數；
    雙角色球員的次要角色用同一組 key 另外渲染一份（見 build_static_site）。

    ``hero_fallback``：當季沒有這個角色的出賽時，hero 數據列改顯示最近一個有
    出賽的球季，並以 ``latest_team_stat_year`` 標出年份。只給次要角色用——
    主要角色維持「當季沒出賽就不顯示」，單一角色球員頁不受影響。
    """
    is_pitcher = role == PITCHER

    logs_by_year = {}
    for log in logs:
        if not log.date:
            continue
        logs_by_year.setdefault(log.date.year, []).append(log)
    for y in logs_by_year:
        logs_by_year[y].sort(key=lambda g: g.date, reverse=True)
    available_log_years = sorted(logs_by_year.keys(), reverse=True)

    if is_pitcher:
        player_trend_by_year = build_pitcher_trend_by_year(logs_by_year)
        trend_stat_options = PITCHER_TREND_STAT_OPTIONS
    else:
        player_trend_by_year = build_batter_trend_by_year(logs_by_year)
        trend_stat_options = BATTER_TREND_STAT_OPTIONS

    stats = annotate_computed_stats(stats)
    stats_year_groups = compute_year_groups(stats)

    stats_current = [s for s in stats if s.year == year and has_appearance(s)]
    stats_current.sort(key=lambda x: x.level_order)
    latest_team_stat = _pick_display_stat(stats_current, player)
    latest_team_stat_year = None
    if latest_team_stat is None and hero_fallback:
        played = [s for s in stats if has_appearance(s)]
        if played:
            latest_team_stat_year = max(s.year for s in played)
            latest_rows = sorted(
                (s for s in played if s.year == latest_team_stat_year),
                key=lambda x: x.level_order,
            )
            latest_team_stat = _pick_display_stat(latest_rows, player)
    # 本季合計直接取成績表的年度合計列，不另外重算（見 compute_year_groups）
    season_combined = (
        next((g["summary"] for g in stats_year_groups if g["year"] == year), None)
        if stats_current else None
    )

    # Season-level Statcast entries keyed by year (one row per level, plus a
    # pooled "_combined" entry for years spanning 2+ levels).
    statcast_by_year = _build_statcast_entries(is_pitcher, stats, logs)

    return {
        "role": role,
        "is_pitcher": is_pitcher,
        "all_stats": stats,
        "all_fielding": fielding,
        "stats_year_groups": stats_year_groups,
        "game_logs": logs_by_year.get(year, []),
        "logs_by_year": logs_by_year,
        "available_log_years": available_log_years,
        "player_trend_by_year": player_trend_by_year,
        "trend_stat_options": trend_stat_options,
        "milb_career": compute_career(stats, level_filter="milb"),
        "mlb_career": compute_career(stats, level_filter="mlb"),
        "total_career": compute_career(stats, level_filter=None),
        "latest_team_stat": latest_team_stat,
        "latest_team_stat_year": latest_team_stat_year,
        "season_combined": season_combined,
        "statcast_by_year": statcast_by_year,
        "statcast_available": bool(statcast_by_year),
        "available_statcast_years": sorted(statcast_by_year.keys(), reverse=True),
    }


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
    output_dir: str,
    base_url: str = "/",
    roster_file: str | None = None,
    update_constants: bool = False,
    site_url: str = SITE_URL,
):
    """Build the complete static site from SQLite data.

    Only renders players whose MLB IDs appear in ``roster_file``.  If
    ``roster_file`` is None the default roster path is used so stale DB
    entries left over from ID changes are never published to the site.

    ``update_constants`` forces a fresh scrape of tjstats.ca for the wRC+
    park-factor/league-constant cache, overwriting any cached values for the
    seasons involved (see ``league_constant.batting``).

    ``base_url`` 是站內連結前綴（本機預覽用 ``/``）；``site_url`` 是對外正式網址，
    只用於 canonical/og:url/sitemap/robots/JSON-LD，本機 build 也指向正式站。
    """
    if roster_file is None:
        roster_file = str(DEFAULT_ROSTER_FILE)
    # 「當季」與 sync 端同一個定義（constants.SEASON_YEAR）
    year = SEASON_YEAR

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

    env = create_jinja_env(base_url=base_url, site_url=site_url)
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
    # 必須在下面的角色投影之前：雙角色球員次要角色檢視的列從這時的原始列
    # 複製，才會帶著 wRC+（wRC+ 只讀打擊欄位，不受投影影響）。
    annotate_wrc_plus(
        bundles, BattingConstants(conn, force_refresh=update_constants).for_level
    )

    # 雙角色球員的次要角色檢視：投影前先複製原始列（投影會就地覆寫 gp / war 等，
    # 之後就讀不回打擊的值），渲染球員頁時再投影到該角色
    # 每個角色要列的列（_row_in_role）也要在投影前判斷，投影後 gp 已被覆寫
    page_roles: dict[int, list[str]] = {}
    raw_stats: dict[int, list] = {}
    role_rows: dict[int, dict[str, list[int]]] = {}
    for player, stats, _logs in bundles:
        page_roles[player.mlb_id] = _page_roles(player, stats)
        if len(page_roles[player.mlb_id]) > 1:
            raw_stats[player.mlb_id] = copy.deepcopy(stats)
            role_rows[player.mlb_id] = {
                role: [i for i, row in enumerate(stats) if _row_in_role(row, role)]
                for role in ROLES
            }

    # season_stats 的打擊/投球拆分欄位（gp / p_gp、war / p_war 等）投影到主要角色：
    # 之後的合併、生涯加總、首頁/退役頁卡片與樣板一律讀不帶前綴的 key
    for player, stats, _logs in bundles:
        role = primary_role(player.position)
        for row in stats:
            project_role(row, role)

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
        player_data.append(
            {
                "player": player,
                "stat": _pick_display_stat(stats_current, player),
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
        canonical_url=absolute_url(RETIRED_INDEX_PATH),
        og_type="website",
    )
    # Write as retired/index.html (not retired.html) so the extension-less
    # /retired URL resolves on both GitHub Pages and a plain http.server
    # (which redirects /retired → /retired/ → index.html).
    retired_dir = out_dir / RETIRED_INDEX_PATH
    retired_dir.mkdir(parents=True, exist_ok=True)
    (retired_dir / "index.html").write_text(retired_html, encoding="utf-8")

    # ── Player detail pages ──
    player_template = env.get_template("player_detail.j2")
    role_alt_template = env.get_template("partials/role_alt_views.j2")
    retired_ids = {p.mlb_id for p, _, _ in retired_bundles}
    for player, all_stats, all_logs in bundles:
        is_retired = player.mlb_id in retired_ids
        selected_year = year
        roles = page_roles[player.mlb_id]
        multi_role = len(roles) > 1

        # Fielding data（all_stats 未依角色篩選，每一列的守備都在這裡）
        all_fielding = []
        for s in all_stats:
            if s.fielding_json:
                for f in s.fielding_json:
                    entry = dict(f)
                    entry["year"] = s.year
                    entry["team_name"] = s.team_name
                    entry["sport_level"] = s.sport_level
                    all_fielding.append(entry)

        # 雙角色球員：逐場紀錄與守備也跟成績表一樣只列該角色的部分
        # （_logs_in_role / _fielding_in_role）；單一角色球員照舊全部列出
        role_logs = {roles[0]: all_logs}
        if multi_role:
            for role in roles[1:]:
                role_logs[role] = load_role_game_logs(cur, player.mlb_id, role)
            role_logs = {role: _logs_in_role(role_logs, role) for role in roles}

        primary_stats = (
            [all_stats[i] for i in role_rows[player.mlb_id][roles[0]]]
            if multi_role else all_stats
        )
        primary_view = _build_role_view(
            primary_stats, role_logs[roles[0]], roles[0], player, year,
            fielding=_fielding_in_role(all_fielding, roles[0]) if multi_role else all_fielding,
        )
        write_pitch_log_files(
            primary_view["logs_by_year"],
            out_dir,
            normalized_base_url,
            player.mlb_id,
            videos_by_game=videos_by_game,
        )

        # 次要角色：從投影前的原始列複製一份投影到該角色，game_logs 為上面另讀的該角色列
        alt_views = []
        for role in roles[1:]:
            raw = raw_stats[player.mlb_id]
            role_stats = [raw[i] for i in role_rows[player.mlb_id][role]]
            for row in role_stats:
                project_role(row, role)
            view = _build_role_view(
                role_stats,
                role_logs[role],
                role,
                player,
                year,
                fielding=_fielding_in_role(all_fielding, role),
                # 主要角色 hero 有當季數據（現役）時，次要角色才退回顯示最近一季；
                # 主要角色本身就空（如已退役）時兩邊一致留空，避免只有切過去才有數字
                hero_fallback=primary_view["latest_team_stat"] is not None,
            )
            write_pitch_log_files(
                view["logs_by_year"],
                out_dir,
                normalized_base_url,
                player.mlb_id,
                videos_by_game=videos_by_game,
                role_dir=role,
            )
            alt_views.append(view)

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

        context = {
            "player": player,
            "years": player.available_years,
            "selected_year": selected_year,
            "next_game": next_game,
            "next_game_updated_at": next_game_updated_at,
            "transactions": player.transactions_json or [],
            "height_cm": height_to_cm(player.height),
            "weight_kg": lbs_to_kg(player.weight),
            "seo_title": f"{player_display_name(player)} 數據 | TwbExpats",
            "seo_description": player_description(player),
            "canonical_url": absolute_url(player_page_path(player.mlb_id, is_retired)),
            "og_type": "profile",
            "structured_data": player_structured_data(absolute_url, player, is_retired),
            "nav_active": "retired" if is_retired else "index",
            # 投手/打者切換（player_detail.j2）：roles[0] 為主要角色、預設顯示
            "page_roles": roles if multi_role else [],
        }
        context.update(primary_view)
        # 次要角色的各分頁內容先各自渲染成字串，由 player_detail.j2 包進 <template>
        # （見 role-toggle.js）；共用同一組 key，所以直接覆寫主要角色的變數再渲染
        context["role_alt_views"] = [
            {
                "role": view["role"],
                "html": Markup(role_alt_template.render(**{**context, **view})),
            }
            for view in alt_views
        ]
        context["trend_chart_needed"] = any(
            v["player_trend_by_year"] for v in [primary_view, *alt_views]
        )

        html = player_template.render(**context)
        player_dir = out_dir / player_page_path(player.mlb_id, is_retired)
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
            "loc": absolute_url(RETIRED_INDEX_PATH),
            "lastmod": now_utc8.date().isoformat(),
        },
    ]
    for player, _, logs in bundles:
        last_game_date = next((log.date for log in logs if log.date), None)
        sitemap_urls.append(
            {
                "loc": absolute_url(player_page_path(player.mlb_id, player.mlb_id in retired_ids)),
                "lastmod": (last_game_date or now_utc8.date()).isoformat(),
            }
        )
    write_sitemap(out_dir, sitemap_urls)
    write_robots(out_dir, absolute_url("sitemap.xml"))

    # ── GitHub Pages marker ──
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    conn.close()
    logger.info("Built %d player pages + index to %s", len(bundles), out_dir)

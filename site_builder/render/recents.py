"""/recents 近期出賽分析頁：載視窗 → 組報告 → 產圖 → 渲染 HTML。"""

import datetime
from pathlib import Path

from ..charts.batted import render_ev_la, render_quality_fallback, render_spray
from ..charts.movement_game import render_game_movement
from ..charts.plate import render_game_pitch_map
from ..charts.velocity import render_velocity_sequence
from ..charts.zones import overlay_points_from_pitches, render_hot_zone
from ..db.game_logs import load_all_pitches_for_player
from ..stats.recent.batter_report import build_batter_report
from ..stats.recent.highlights import build_chips, build_notes
from ..stats.recent.pitcher_report import build_pitcher_report
from ..stats.recent.window import WINDOW_DAYS, load_recent_window
from ..stats.recent.zone_stats import compute_zone_stats
from ..util.json import loads_json_dict

RECENTS_SEO_TITLE = "近期出賽分析 | TwbExpats"
RECENTS_SEO_DESCRIPTION = (
    "台灣旅美棒球員近 7 天出賽週報告：球速、球種使用率、選球與擊球品質"
    "的本週 vs 球季變化，附本壘板視角逐球圖表。"
)


def _load_season_statcast(cur, mlb_id: int, year: int, level: str) -> dict:
    cur.execute(
        "SELECT stat_json FROM season_stats "
        "WHERE player_mlb_id = ? AND year = ? AND sport_level = ?",
        (mlb_id, year, level),
    )
    for row in cur.fetchall():
        sc = loads_json_dict(row[0]).get("statcast")
        if sc:
            return sc
    return {}


def _game_title(game, suffix: str) -> str:
    date_s = game["date"].strftime("%m/%d") if game["date"] else ""
    side = "vs" if game["is_home"] else "@"
    return f"{date_s} {side} {game['opponent']} - {suffix}"


def _pitcher_game_charts(game, season_pitches, season_arsenal, chart_dir, url_for):
    charts = {}
    gid = game["game_id"]
    if game["tier"] <= 2:
        name = f"{gid}-pitchmap.png"
        if render_game_pitch_map(game["pitches"], chart_dir / name,
                                 title=_game_title(game, "Pitch locations")):
            charts["pitch_map"] = url_for(name)
        name = f"{gid}-velocity.png"
        if render_velocity_sequence(game["pitches"], chart_dir / name,
                                    season_arsenal=season_arsenal,
                                    title=_game_title(game, "Velocity")):
            charts["velocity"] = url_for(name)
        name = f"{gid}-movement.png"
        if render_game_movement(game["pitches"], season_pitches,
                                chart_dir / name,
                                title=_game_title(game, "Movement")):
            charts["movement"] = url_for(name)
    return charts


def _batter_game_charts(game, season_pitches, chart_dir, url_for):
    charts = {}
    gid = game["game_id"]
    if game["tier"] <= 2:
        name = f"{gid}-pitchmap.png"
        if render_game_pitch_map(game["pitches"], chart_dir / name,
                                 title=_game_title(game, "Pitches seen")):
            charts["pitch_map"] = url_for(name)
        name = f"{gid}-evla.png"
        if render_ev_la(game["pitches"], season_pitches, chart_dir / name,
                        title=_game_title(game, "EV / LA")):
            charts["ev_la"] = url_for(name)
    # spray：hit_coord 各層級都有，Tier 3 也畫
    name = f"{gid}-spray.png"
    if render_spray(game["pitches"], season_pitches, chart_dir / name,
                    title=_game_title(game, "Spray chart")):
        charts["spray"] = url_for(name)
    return charts


def _build_report(cur, window, level, games, year, out_dir, base_url):
    mlb_id = window["mlb_id"]
    is_pitcher = window["is_pitcher"]
    season_pitches = load_all_pitches_for_player(cur, mlb_id).get(
        (year, level), [])
    season = {
        "statcast": _load_season_statcast(cur, mlb_id, year, level),
        "pitches": season_pitches,
    }
    role = "pitcher" if is_pitcher else "batter"
    if is_pitcher:
        report = build_pitcher_report(games, season)
    else:
        report = build_batter_report(games, season)
    report["player"] = {k: v for k, v in window.items() if k != "games"}
    report["level"] = level
    report["chips"] = build_chips(report, role)
    report["notes"] = build_notes(report, role)

    chart_dir = out_dir / "static" / "charts" / "recents" / str(mlb_id)

    def url_for(name: str) -> str:
        return f"{base_url}static/charts/recents/{mlb_id}/{name}"

    season_arsenal = (season["statcast"] or {}).get("pitch_arsenal")
    game_charts = {}
    for g in games:
        if is_pitcher:
            game_charts[g["game_id"]] = _pitcher_game_charts(
                g, season_pitches, season_arsenal, chart_dir, url_for)
        else:
            game_charts[g["game_id"]] = _batter_game_charts(
                g, season_pitches, chart_dir, url_for)
    report["game_charts"] = game_charts

    if not is_pitcher:
        report["zone_chart"] = None
        report["zone_chart_missing_reason"] = None
        zone_stats = compute_zone_stats(season_pitches)
        if zone_stats:
            week_finals = [p for g in games for p in g["pitches"]
                           if p.get("is_pa_final")]
            name = "season-zones.png"
            if render_hot_zone(
                    zone_stats, chart_dir / name,
                    overlay_points=overlay_points_from_pitches(week_finals),
                    title=f"{year} Season AVG by zone"):
                report["zone_chart"] = url_for(name)
        if report["zone_chart"] is None:
            report["zone_chart_missing_reason"] = (
                "此層級無進壘點追蹤資料，無法繪製熱區"
            )
        report["quality_chart"] = None
        if any(g["tier"] == 3 for g in games):
            week_pitches = [p for g in games for p in g["pitches"]]
            name = "week-quality.png"
            if render_quality_fallback(week_pitches, season_pitches,
                                       chart_dir / name,
                                       title="Contact quality - week vs season"):
                report["quality_chart"] = url_for(name)
    return report


def build_recents_page(env, conn, out_dir: Path, year: int,
                       roster_ids: set, *, today=None) -> dict:
    today = today or datetime.date.today()
    base_url = env.globals["base_url"]
    absolute_url = env.globals["absolute_url"]
    cur = conn.cursor()
    windows = load_recent_window(cur, roster_ids, today=today)

    pitcher_reports, batter_reports = [], []
    for window in windows:
        by_level: dict[str, list] = {}
        for g in window["games"]:
            by_level.setdefault(g["sport_level"], []).append(g)
        for level, games in by_level.items():
            report = _build_report(cur, window, level, games, year,
                                   out_dir, base_url)
            (pitcher_reports if window["is_pitcher"]
             else batter_reports).append(report)

    template = env.get_template("recents.j2")
    html = template.render(
        pitcher_reports=pitcher_reports,
        batter_reports=batter_reports,
        date_range={"start": today - datetime.timedelta(days=WINDOW_DAYS),
                    "end": today},
        season_year=year,
        nav_active="recents",
        seo_title=RECENTS_SEO_TITLE,
        seo_description=RECENTS_SEO_DESCRIPTION,
        canonical_url=absolute_url("recents/"),
        og_type="website",
    )
    recents_dir = out_dir / "recents"
    recents_dir.mkdir(parents=True, exist_ok=True)
    (recents_dir / "index.html").write_text(html, encoding="utf-8")
    return {"loc": absolute_url("recents/"), "lastmod": today.isoformat()}

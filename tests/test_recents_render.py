import datetime
import json
import sqlite3
from pathlib import Path

from site_builder.db.schema import init_db
from site_builder.render.env import create_jinja_env
from site_builder.render.recents import build_recents_page
from tests.recent_fixtures import make_pitch, make_untracked_pitch

TODAY = datetime.date(2026, 7, 9)


def _env():
    env = create_jinja_env(base_url="/")
    env.globals["build_time"] = "2026-07-09 00:00"
    return env


def _seed(conn):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO players (mlb_id, name_en, name_tw, team, level, position)"
        " VALUES (678906, 'Kai-Wei Teng', '鄧愷威', 'Sacramento River Cats', 'AAA', 'P')"
    )
    cur.execute(
        "INSERT INTO players (mlb_id, name_en, name_tw, team, level, position)"
        " VALUES (800018, 'Chung-Ao Chuang', '莊陳仲敖', 'Somerset Patriots', 'AA', 'C')"
    )
    pitcher_pitches = [make_pitch(start_speed=95.0) for _ in range(15)]
    pitcher_pitches.append(make_pitch(
        result_code="E", is_in_play=True, is_pa_final=True, pa_event="single",
        pa_event_desc="Single", ev=98.0, la=10.0, trajectory="line_drive"))
    cur.execute(
        "INSERT INTO game_logs (player_mlb_id, date, game_id, opponent, is_home,"
        " stats_json, pitches_json, events_json, sport_level) VALUES"
        " (678906, '2026-07-06', 111, 'BUF', 1,"
        "  '{\"inningsPitched\":\"5.0\",\"earnedRuns\":1,\"strikeOuts\":6,"
        "\"baseOnBalls\":2,\"hits\":4}', ?, '[]', 'AAA')",
        (json.dumps(pitcher_pitches),),
    )
    # AA 打者（Tier 3）＋ 一顆有落點的擊球
    batter_pitches = [make_untracked_pitch() for _ in range(8)]
    batter_pitches.append(make_untracked_pitch(
        is_in_play=True, result_code="E", is_pa_final=True, pa_event="double",
        pa_event_desc="Double", hit_coord_x=180.0, hit_coord_y=90.0,
        trajectory="line_drive", hardness="hard"))
    cur.execute(
        "INSERT INTO game_logs (player_mlb_id, date, game_id, opponent, is_home,"
        " stats_json, pitches_json, events_json, sport_level) VALUES"
        " (800018, '2026-07-07', 222, 'HFD', 0,"
        "  '{\"atBats\":4,\"hits\":2,\"summary\":\"2-4 | 2B\"}', ?, '[]', 'AA')",
        (json.dumps(batter_pitches),),
    )
    cur.execute(
        "INSERT INTO season_stats (player_mlb_id, year, team_name, sport_level,"
        " league_name, stat_json) VALUES (678906, 2026, 'Sacramento River Cats',"
        " 'AAA', 'PCL', ?)",
        (json.dumps({"statcast": {
            "pitch_arsenal": [{"type": "FF", "name": "Four-Seam Fastball",
                               "count": 300, "pct": 0.6, "velo": 94.0,
                               "whiff_pct": 0.2, "chase_pct": 0.3,
                               "zone_pct": 0.5}],
            "whiff_pct": 0.24, "o_swing_pct": 0.29, "zone_pct": 0.5,
            "csw_pct": 0.28, "swstr_pct": 0.11, "z_contact_pct": 0.86,
            "avg_ev": 88.0, "hard_hit_pct": 0.4,
        }}),),
    )
    conn.commit()


def test_build_recents_page(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)
    out = tmp_path / "dist"
    entry = build_recents_page(_env(), conn, out, 2026, {678906, 800018},
                               today=TODAY)
    html = (out / "recents" / "index.html").read_text(encoding="utf-8")
    assert "鄧愷威" in html and "莊陳仲敖" in html
    assert "5.0 IP, 1 ER, 6 K, 2 BB" in html
    assert "近 7 天無出賽紀錄" not in html
    # Tier 3 fallback 文案 + 結果條
    assert "無進壘點追蹤資料" in html
    assert "result-strip" in html
    # 投手圖有產出且被引用
    charts = list((out / "static" / "charts" / "recents" / "678906").glob("*.png"))
    assert charts
    assert "/static/charts/recents/678906/111-pitchmap.png" in html
    assert entry["loc"].endswith("recents/")


def test_build_recents_page_empty(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    out = tmp_path / "dist"
    build_recents_page(_env(), conn, out, 2026, {678906}, today=TODAY)
    html = (out / "recents" / "index.html").read_text(encoding="utf-8")
    assert "近 7 天無出賽紀錄" in html

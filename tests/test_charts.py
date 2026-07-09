"""charts/ 圖表引擎測試：主題常數、result 分類與各 render_* 冒煙測試。"""
from pathlib import Path

from site_builder.charts import style
from site_builder.charts.movement_game import render_game_movement
from site_builder.charts.plate import render_game_pitch_map
from site_builder.charts.velocity import render_velocity_sequence
from site_builder.charts.zones import overlay_points_from_pitches, render_hot_zone
from tests.recent_fixtures import make_pitch, make_untracked_pitch


def test_pitch_color_registry_is_stable():
    assert style.pitch_color("FF") == "#e66767"
    assert style.pitch_color("SL") == "#3987e5"
    assert style.pitch_color("CH") == "#008300"
    assert style.pitch_color(None) == style.NEUTRAL
    assert style.pitch_color("ZZ") == style.NEUTRAL


def test_result_class():
    assert style.result_class({"is_in_play": True, "result_code": "D"}) == "inplay"
    assert style.result_class({"result_code": "S"}) == "whiff"
    assert style.result_class({"result_code": "T"}) == "whiff"  # foul tip 屬揮空
    assert style.result_class({"result_code": "C"}) == "called"
    assert style.result_class({"result_code": "F"}) == "foul"
    assert style.result_class({"result_code": "B", "is_ball": True}) == "ball"


def test_save_chart_writes_png(tmp_path):
    fig, ax = style.new_fig(4, 3)
    ax.plot([0, 1], [0, 1], color=style.ACCENT)
    out = tmp_path / "sub" / "smoke.png"
    style.save_chart(fig, out)
    assert out.is_file() and out.stat().st_size > 1000


def _game_pitches():
    return [
        make_pitch(px=-0.5, pz=2.8),
        make_pitch(px=0.3, pz=2.1, result_code="S"),
        make_pitch(px=0.9, pz=1.5, pitch_type="SL", result_code="F"),
        make_pitch(px=-1.2, pz=3.6, pitch_type="CH", result_code="B",
                   is_strike=False, is_ball=True),
        make_pitch(px=0.1, pz=2.4, result_code="E", is_in_play=True,
                   is_pa_final=True, pa_event="home_run", ev=105.0, la=28.0,
                   trajectory="fly_ball", hit_coord_x=140.0, hit_coord_y=60.0,
                   hit_distance=410, hardness="hard"),
    ]


def test_render_game_pitch_map(tmp_path):
    out = tmp_path / "pitchmap.png"
    assert render_game_pitch_map(_game_pitches(), out, title="07/06 vs BUF") is True
    assert out.is_file() and out.stat().st_size > 5000


def test_render_game_pitch_map_untracked_returns_false(tmp_path):
    out = tmp_path / "no.png"
    assert render_game_pitch_map([make_untracked_pitch()], out) is False
    assert not out.exists()


def _zone_stats():
    zs = {}
    for z in range(1, 10):
        zs[z] = {"n": 30, "swings": 15, "whiffs": 4, "ab": 10, "hits": 3,
                 "avg": 0.300, "swing_pct": 0.5, "whiff_pct": 0.267}
    zs[11] = {"n": 12, "swings": 4, "whiffs": 2, "ab": 2, "hits": 0,
              "avg": 0.0, "swing_pct": 0.333, "whiff_pct": 0.5}  # ab<5 → 遮罩
    return zs


def test_render_hot_zone(tmp_path):
    out = tmp_path / "zones.png"
    overlay = overlay_points_from_pitches([make_pitch(px=0.0, pz=2.5)])
    assert render_hot_zone(_zone_stats(), out, overlay_points=overlay,
                           title="Season AVG by zone") is True
    assert out.is_file() and out.stat().st_size > 5000
    assert len(overlay) == 1
    x, y = overlay[0]
    assert 1.0 < x < 2.0 and 1.0 < y < 2.0  # 正中＝中央格


def test_render_hot_zone_empty(tmp_path):
    assert render_hot_zone({}, tmp_path / "z.png") is False


def test_render_velocity_sequence(tmp_path):
    pitches = (
        [make_pitch(start_speed=94 + i * 0.2, inning=1) for i in range(6)]
        + [make_pitch(pitch_type="SL", start_speed=85.0, inning=2) for _ in range(4)]
    )
    arsenal = [{"type": "FF", "velo": 94.8}, {"type": "SL", "velo": 84.9},
               {"type": "CH", "velo": 88.0}]  # CH 本場沒投 → 不畫線
    out = tmp_path / "velo.png"
    assert render_velocity_sequence(pitches, out, season_arsenal=arsenal) is True
    assert out.stat().st_size > 5000


def test_render_velocity_sequence_untracked(tmp_path):
    assert render_velocity_sequence(
        [make_untracked_pitch() for _ in range(10)], tmp_path / "v.png") is False


def test_render_game_movement(tmp_path):
    game = [make_pitch(hb=8 + i * 0.3, ivb=15 - i * 0.2) for i in range(5)]
    season = [make_pitch(hb=7 + (i % 7) * 0.5, ivb=14 + (i % 5) * 0.4)
              for i in range(40)]
    out = tmp_path / "move.png"
    assert render_game_movement(game, season, out) is True
    assert out.stat().st_size > 5000


def test_render_game_movement_no_data(tmp_path):
    assert render_game_movement([make_untracked_pitch()], [], tmp_path / "m.png") is False

"""charts/ 圖表引擎測試：主題常數、result 分類與各 render_* 冒煙測試。"""
from pathlib import Path

from site_builder.charts import style
from site_builder.charts.plate import render_game_pitch_map
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

"""charts/ 圖表引擎測試：主題常數、result 分類與各 render_* 冒煙測試。"""
from pathlib import Path

from site_builder.charts import style


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

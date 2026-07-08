import pytest

from site_builder.stats.recent.zone_stats import compute_zone_stats
from tests.recent_fixtures import make_pitch, make_untracked_pitch


def _final(zone, event, code="D"):
    return make_pitch(zone=zone, is_pa_final=True, pa_event=event,
                      result_code=code, is_in_play=code in ("D", "E", "X"))


def test_zone_avg_counts_final_pitch_only():
    pitches = [
        make_pitch(zone=5, result_code="S"),               # 揮空，非終結
        _final(5, "single"),
        _final(5, "field_out", code="X"),
        _final(5, "walk", code="B"),                        # 非 AB，不入 AVG
        _final(2, "home_run", code="E"),
        _final(5, "caught_stealing_2b", code="B"),          # NON_PA_EVENT 排除
    ]
    zs = compute_zone_stats(pitches)
    assert zs[5]["ab"] == 2 and zs[5]["hits"] == 1
    assert zs[5]["avg"] == pytest.approx(0.5)
    assert zs[2]["ab"] == 1 and zs[2]["avg"] == pytest.approx(1.0)


def test_zone_swing_whiff_per_pitch():
    pitches = [
        make_pitch(zone=13, result_code="S"),   # swing + whiff
        make_pitch(zone=13, result_code="F"),   # swing
        make_pitch(zone=13, result_code="B", is_strike=False, is_ball=True),
    ]
    zs = compute_zone_stats(pitches)
    assert zs[13]["n"] == 3 and zs[13]["swings"] == 2 and zs[13]["whiffs"] == 1
    assert zs[13]["swing_pct"] == pytest.approx(2 / 3, abs=1e-6)
    assert zs[13]["whiff_pct"] == pytest.approx(0.5)


def test_zone_stats_skips_zoneless():
    assert compute_zone_stats([make_untracked_pitch()]) == {}

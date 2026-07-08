import pytest

from site_builder.stats.recent import derived
from tests.recent_fixtures import make_pitch, make_untracked_pitch


def test_vaa_haa_known_vectors():
    # 期望值以 §0.7 公式手算：vy0=-135, ay=25, vz0=-5, az=-15, vx0=2, ax=-8
    p = make_pitch()
    assert derived.compute_vaa(p) == pytest.approx(-4.817, abs=0.01)
    assert derived.compute_haa(p) == pytest.approx(-0.448, abs=0.01)
    assert derived.compute_vaa(make_untracked_pitch()) is None


def test_effective_velocity_and_decay():
    p = make_pitch(start_speed=95.0, extension=7.5, end_speed=87.5)
    assert derived.effective_velocity(p) == pytest.approx(96.79, abs=0.01)
    assert derived.velocity_decay(p) == pytest.approx(7.5)
    assert derived.effective_velocity(make_pitch(extension=None)) is None


def test_spin_clock():
    assert derived.spin_clock(180) == "12:00"
    assert derived.spin_clock(210) == "1:00"
    assert derived.spin_clock(270) == "3:00"
    assert derived.spin_clock(90) == "9:00"
    assert derived.spin_clock(195) == "12:30"
    assert derived.spin_clock(179) == "12:00"  # 719' 進位回 12:00
    assert derived.spin_clock(None) is None


def test_circular_mean_deg():
    assert derived.circular_mean_deg([350, 10]) == pytest.approx(0.0, abs=0.1)
    assert derived.circular_mean_deg([90, 90]) == pytest.approx(90.0)
    assert derived.circular_mean_deg([]) is None


def test_attack_zone():
    assert derived.attack_zone(make_pitch(px=0.0, pz=2.5)) == "heart"
    assert derived.attack_zone(make_pitch(px=0.9, pz=2.5)) == "shadow"
    assert derived.attack_zone(make_pitch(px=1.5, pz=2.5)) == "chase"
    assert derived.attack_zone(make_pitch(px=2.5, pz=2.5)) == "waste"
    assert derived.attack_zone(make_untracked_pitch()) is None


def test_attack_zone_distribution_and_edge():
    pitches = [make_pitch(px=0.0), make_pitch(px=0.9), make_pitch(px=0.9),
               make_pitch(px=2.5), make_untracked_pitch()]
    dist = derived.attack_zone_distribution(pitches)
    assert dist["n"] == 4
    assert dist["shadow"] == pytest.approx(0.5)
    assert derived.edge_pct(pitches) == pytest.approx(0.5)
    assert derived.attack_zone_distribution([make_untracked_pitch()]) is None


def test_f_strike_pct():
    pitches = [
        make_pitch(pre_balls=0, pre_strikes=0, is_strike=True),
        make_pitch(pre_balls=0, pre_strikes=0, is_strike=False, is_in_play=True),
        make_pitch(pre_balls=0, pre_strikes=0, is_strike=False, is_ball=True),
        make_pitch(pre_balls=1, pre_strikes=0),  # 非首球，不入分母
    ]
    assert derived.f_strike_pct(pitches) == pytest.approx(2 / 3, abs=1e-6)
    assert derived.f_strike_pct([]) is None


def test_derived_by_pitch_type():
    pitches = [make_pitch(), make_pitch(), make_pitch(pitch_type="SL", spin_dir=45.0)]
    out = derived.derived_by_pitch_type(pitches)
    assert set(out) == {"FF", "SL"}
    assert out["FF"]["n"] == 2
    assert out["FF"]["spin_clock"] == "1:00"
    assert out["FF"]["vaa"] == pytest.approx(-4.8, abs=0.05)

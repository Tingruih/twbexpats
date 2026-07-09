from site_builder.stats.recent.highlights import build_chips, build_notes


def _pitcher_report():
    return {
        "pitch_count": 80,
        "week": {"whiff_pct": 0.30, "o_swing_pct": 0.33, "zone_pct": 0.50,
                 "csw_pct": 0.33, "swstr_pct": 0.13, "z_contact_pct": 0.82,
                 "avg_ev": 86.0, "hard_hit_pct": 0.30, "bbe": 12,
                 "f_strike_pct": 0.70,
                 "swings": None},
        "season_available": True,
        "deltas": {
            "arsenal": [
                {"type": "FF", "name": "Four-Seam Fastball", "count": 40,
                 "week_pct": 0.5, "season_pct": 0.55, "usage_delta": -0.05,
                 "week_velo": 95.6, "season_velo": 94.2, "velo_delta": 1.4,
                 "whiff_delta": 0.02, "chase_delta": None, "zone_delta": None,
                 "is_new": False, "is_dropped": False},
                {"type": "ST", "name": "Sweeper", "count": 12,
                 "week_pct": 0.15, "season_pct": None, "usage_delta": 0.15,
                 "week_velo": 84.0, "season_velo": None, "velo_delta": None,
                 "whiff_delta": None, "chase_delta": None, "zone_delta": None,
                 "is_new": True, "is_dropped": False},
            ],
            "discipline": {
                "whiff_pct": {"week": 0.30, "season": 0.25, "delta": 0.05},
                "o_swing_pct": {"week": 0.33, "season": 0.30, "delta": 0.03},
                "zone_pct": {"week": 0.50, "season": 0.50, "delta": 0.0},
                "csw_pct": {"week": 0.33, "season": 0.29, "delta": 0.04},
                "swstr_pct": {"week": 0.13, "season": 0.12, "delta": 0.01},
                "z_contact_pct": {"week": 0.82, "season": 0.85, "delta": -0.03},
                "avg_ev": {"week": 86.0, "season": 89.0, "delta": -3.0},
                "hard_hit_pct": {"week": 0.30, "season": 0.40, "delta": -0.10},
            },
        },
    }


def test_pitcher_chips_and_notes():
    report = _pitcher_report()
    chips = build_chips(report, "pitcher")
    labels = [c["label"] for c in chips]
    assert "FF 均速" in labels
    velo_chip = chips[labels.index("FF 均速")]
    assert velo_chip["cls"] == "up" and velo_chip["good"] is True
    assert velo_chip["delta_str"] == "+1.4 mph"
    # 被打 EV 下降對投手是好事
    ev_chip = next(c for c in chips if c["label"] == "被打 EV")
    assert ev_chip["cls"] == "down" and ev_chip["good"] is True

    notes = build_notes(report, "pitcher")
    assert 1 <= len(notes) <= 4
    assert any("新球種" in n and "Sweeper" in n for n in notes)


def test_small_sample_suppresses_chips():
    report = _pitcher_report()
    report["pitch_count"] = 10  # < usage 門檻 30
    report["deltas"]["arsenal"][0]["count"] = 3  # < velo 門檻 5
    chips = build_chips(report, "pitcher")
    assert all(c["label"] != "FF 均速" for c in chips)


def test_batter_direction_sense():
    report = {
        "pitch_count": 60,
        "week": {"bbe": 8},
        "season_available": True,
        "deltas": {"discipline": {
            "o_swing_pct": {"week": 0.25, "season": 0.32, "delta": -0.07},
            "whiff_pct": {"week": 0.20, "season": 0.26, "delta": -0.06},
            "z_contact_pct": {"week": 0.90, "season": 0.84, "delta": 0.06},
            "swstr_pct": {"week": 0.08, "season": 0.11, "delta": -0.03},
            "zone_pct": {"week": 0.49, "season": 0.49, "delta": 0.0},
            "avg_ev": {"week": 91.0, "season": 88.0, "delta": 3.0},
            "hard_hit_pct": {"week": 0.50, "season": 0.38, "delta": 0.12},
        }},
    }
    chips = build_chips(report, "batter")
    chase = next(c for c in chips if c["label"] == "Chase%")
    assert chase["cls"] == "down" and chase["good"] is True
    ev = next(c for c in chips if c["label"] == "平均 EV")
    assert ev["cls"] == "up" and ev["good"] is True


def test_no_baseline_no_chips():
    assert build_chips({"season_available": False, "deltas": {}}, "pitcher") == []

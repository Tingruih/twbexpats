import pytest

from site_builder.stats.recent.batter_report import build_batter_report
from site_builder.stats.recent.pitcher_report import build_pitcher_report
from site_builder.stats.recent.window import game_tier
from tests.recent_fixtures import make_pitch, make_untracked_pitch


def _pitcher_game(game_id=111, pitches=None):
    pitches = pitches if pitches is not None else _pitcher_pitches()
    return {
        "date": None, "game_id": game_id, "opponent": "BUF", "is_home": True,
        "sport_level": "AAA", "tier": game_tier(pitches), "events": [],
        "stats": {"inningsPitched": "5.1", "earnedRuns": 1, "strikeOuts": 6,
                  "baseOnBalls": 2, "hits": 4, "numberOfPitches": 82},
        "pitches": pitches,
    }


def _pitcher_pitches():
    ps = [make_pitch(start_speed=95.5) for _ in range(8)]
    ps += [make_pitch(pitch_type="ST", pitch_name="Sweeper", start_speed=84.0,
                      result_code="S") for _ in range(4)]
    ps.append(make_pitch(
        result_code="E", is_in_play=True, is_pa_final=True, pa_event="single",
        pa_event_desc="Single", start_speed=95.5, ev=98.0, la=12.0,
        trajectory="line_drive",
        runners=[{"is_scoring_event": True, "earned": True, "rbi": True,
                  "event": "Single", "end_base": "score"}],
    ))
    return ps


def _season_ctx():
    return {
        "statcast": {
            "pitch_arsenal": [
                {"type": "FF", "name": "Four-Seam Fastball", "count": 400,
                 "pct": 0.55, "velo": 94.2, "whiff_pct": 0.22,
                 "chase_pct": 0.28, "zone_pct": 0.52},
                {"type": "SL", "name": "Slider", "count": 290, "pct": 0.40,
                 "velo": 86.0, "whiff_pct": 0.35, "chase_pct": 0.33,
                 "zone_pct": 0.44},
            ],
            "whiff_pct": 0.25, "o_swing_pct": 0.30, "zone_pct": 0.50,
            "csw_pct": 0.29, "swstr_pct": 0.12, "z_contact_pct": 0.85,
            "avg_ev": 89.0, "hard_hit_pct": 0.40,
        },
        "pitches": [make_pitch(start_speed=94.0) for _ in range(30)],
    }


def test_pitcher_report_week_and_deltas():
    report = build_pitcher_report([_pitcher_game()], _season_ctx())
    assert report["tier"] == 1
    assert report["pitch_count"] == 13
    assert report["week"]["ip"] == 5.1
    assert report["games"][0]["summary"] == "5.1 IP, 1 ER, 6 K, 2 BB"
    assert report["season_available"] is True
    ff = next(r for r in report["deltas"]["arsenal"] if r["type"] == "FF")
    assert ff["velo_delta"] == pytest.approx(95.5 - 94.2, abs=0.01)
    assert ff["usage_delta"] is not None
    # ST 季 usage 為 0 → NEW 徽章
    st = next(r for r in report["deltas"]["arsenal"] if r["type"] == "ST")
    assert st["is_new"] is True
    assert len(report["scoring_events"]) == 1


def test_pitcher_report_no_season_baseline():
    report = build_pitcher_report([_pitcher_game()], {"statcast": {}, "pitches": []})
    assert report["season_available"] is False
    assert report["deltas"]["arsenal"] == []


def test_pitcher_report_tier3():
    g = _pitcher_game(pitches=[make_untracked_pitch(result_code="S") for _ in range(20)])
    report = build_pitcher_report([g], {"statcast": {}, "pitches": []})
    assert report["tier"] == 3
    assert report["week"]["arsenal"] == []


def _batter_game():
    ps = [
        make_pitch(pitcher_id=1, batter_id=2, result_code="B", is_strike=False,
                   is_ball=True, zone=12),
        make_pitch(pitcher_id=1, batter_id=2, result_code="S", zone=5,
                   pre_strikes=0),
        make_pitch(pitcher_id=1, batter_id=2, pitch_type="SL", zone=5,
                   pre_strikes=2, result_code="E", is_in_play=True,
                   is_pa_final=True, pa_event="double", pa_event_desc="Double",
                   ev=101.0, la=18.0, trajectory="line_drive",
                   hit_coord_x=180.0, hit_coord_y=90.0, hardness="hard",
                   inning=2),
    ]
    return {
        "date": None, "game_id": 222, "opponent": "SUG", "is_home": False,
        "sport_level": "AAA", "tier": 1, "events": [],
        "stats": {"atBats": 4, "hits": 2, "homeRuns": 0, "rbi": 1,
                  "baseOnBalls": 0, "strikeOuts": 1,
                  "summary": "2-4 | 2B, RBI"},
        "pitches": ps,
    }


def test_batter_report():
    season = {"statcast": {"o_swing_pct": 0.32, "whiff_pct": 0.26,
                           "z_contact_pct": 0.84, "swstr_pct": 0.11,
                           "zone_pct": 0.49, "avg_ev": 88.0,
                           "hard_hit_pct": 0.38},
              "pitches": [make_pitch() for _ in range(20)]}
    report = build_batter_report([_batter_game()], season)
    assert report["week"]["batting_line"]["ab"] == 4
    assert report["week"]["batting_line"]["avg"] == pytest.approx(0.5)
    assert report["week"]["ev"]["max_ev"] == pytest.approx(101.0)
    assert report["two_strike"]["pa"] == 1 and report["two_strike"]["hits"] == 1
    groups = {g["group"] for g in report["group_splits"]}
    assert {"fastball", "breaking"} <= groups
    assert len(report["pa_timeline"]) == 1
    pa = report["pa_timeline"][0]
    assert pa["result"] == "Double" and pa["inning"] == 2
    assert [t for t, _ in pa["sequence"]] == ["FF", "FF", "SL"]

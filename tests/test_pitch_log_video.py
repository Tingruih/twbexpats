import json

from site_builder.render.pitch_log import (
    summarize_pitch_for_display,
    write_pitch_log_files,
)
from site_builder.util.obj import Obj
from tests.recent_fixtures import make_pitch

PID = "b339cea8-e12d-340f-adbc-a655fb63aaed"


def test_summarize_video_gating():
    p = make_pitch()
    plain = summarize_pitch_for_display(p)
    assert "play_id" not in plain and "video" not in plain

    mlb = summarize_pitch_for_display(p, {PID: "https://x/a.mp4"},
                                      include_video=True)
    assert mlb["play_id"] == PID and mlb["video"] == "https://x/a.mp4"

    no_hit = summarize_pitch_for_display(p, {}, include_video=True)
    assert no_hit["play_id"] == PID and "video" not in no_hit


def _log(game_id, level):
    log = Obj()
    log.game_id = game_id
    log.sport_level = level
    log.pitches_json = [make_pitch()]
    return log


def test_write_pitch_log_files_gating(tmp_path):
    mlb_log = _log(776911, "MLB")
    aaa_log = _log(779812, "AAA")
    write_pitch_log_files({2026: [mlb_log, aaa_log]}, tmp_path, "/", 678906,
                          videos_by_game={776911: {PID: "https://x/a.mp4"}})
    mlb_json = json.loads(
        (tmp_path / "data/pitchlogs/678906/776911.json").read_text())
    aaa_json = json.loads(
        (tmp_path / "data/pitchlogs/678906/779812.json").read_text())
    assert mlb_json[0]["video"] == "https://x/a.mp4"
    assert "play_id" not in aaa_json[0] and "video" not in aaa_json[0]

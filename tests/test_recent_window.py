import datetime
import json
import sqlite3

from site_builder.db.schema import init_db
from site_builder.stats.recent.window import game_tier, load_recent_window
from tests.recent_fixtures import make_pitch, make_untracked_pitch

TODAY = datetime.date(2026, 7, 9)


def test_game_tier():
    assert game_tier([make_pitch() for _ in range(10)]) == 1
    mixed = [make_pitch() for _ in range(3)] + [make_untracked_pitch() for _ in range(7)]
    assert game_tier(mixed) == 2
    assert game_tier([make_untracked_pitch() for _ in range(10)]) == 3
    assert game_tier([]) == 3


def _seed(conn):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO players (mlb_id, name_en, name_tw, team, level, position) "
        "VALUES (678906, 'Kai-Wei Teng', '鄧愷威', 'Sacramento River Cats', 'AAA', 'P')"
    )
    pitches = json.dumps([make_pitch(), make_pitch(result_code="S")])
    cur.execute(
        "INSERT INTO game_logs (player_mlb_id, date, game_id, opponent, is_home,"
        " stats_json, pitches_json, events_json, sport_level) VALUES"
        " (678906, '2026-07-06', 111, 'BUF', 1,"
        "  '{\"inningsPitched\": \"5.0\"}', ?, '[]', 'AAA')",
        (pitches,),
    )
    # 視窗外（8 天前）的比賽不得入選
    cur.execute(
        "INSERT INTO game_logs (player_mlb_id, date, game_id, opponent, is_home,"
        " stats_json, pitches_json, events_json, sport_level) VALUES"
        " (678906, '2026-07-01', 110, 'LV', 0, '{}', 'null', '[]', 'AAA')"
    )
    conn.commit()


def test_load_recent_window():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)
    windows = load_recent_window(conn.cursor(), {678906}, today=TODAY)
    assert len(windows) == 1
    w = windows[0]
    assert w["mlb_id"] == 678906 and w["is_pitcher"] is True
    assert [g["game_id"] for g in w["games"]] == [111]
    g = w["games"][0]
    assert g["tier"] == 1 and g["sport_level"] == "AAA"
    assert g["stats"]["inningsPitched"] == "5.0"
    assert len(g["pitches"]) == 2


def test_load_recent_window_empty_roster():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    assert load_recent_window(conn.cursor(), set(), today=TODAY) == []

import sqlite3

from site_builder.db.play_videos import (
    content_fetch_candidates,
    load_video_map,
    mark_content_processed,
    save_play_videos,
)
from site_builder.db.schema import init_db

NOW = "2026-07-09T00:00:00+00:00"


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    cur = conn.cursor()
    # MLB 近期比賽 / MLB 舊比賽 / AAA 比賽
    rows = [
        (678906, "2026-07-06", 776911, "NYM", "MLB"),
        (678906, "2025-08-02", 700001, "SF", "MLB"),
        (678906, "2026-07-05", 779812, "LV", "AAA"),
    ]
    for mlb_id, date, gpk, opp, lvl in rows:
        cur.execute(
            "INSERT INTO game_logs (player_mlb_id, date, game_id, opponent,"
            " stats_json, pitches_json, sport_level) VALUES (?,?,?,?,'{}','[]',?)",
            (mlb_id, date, gpk, opp, lvl),
        )
    conn.commit()
    return conn


def test_candidates_only_mlb_and_unprocessed():
    conn = _conn()
    cur = conn.cursor()
    got = sorted(content_fetch_candidates(cur, [678906], "2026-06-25"))
    assert got == [700001, 776911]  # AAA 排除


def test_retry_window():
    conn = _conn()
    cur = conn.cursor()
    # 兩場都處理過但 0 部影片：只有 retry window 內的比賽重試
    mark_content_processed(cur, 776911, 0, NOW)
    mark_content_processed(cur, 700001, 0, NOW)
    got = content_fetch_candidates(cur, [678906], "2026-06-25")
    assert got == [776911]
    # 找到影片後不再是 candidate
    mark_content_processed(cur, 776911, 3, NOW)
    assert content_fetch_candidates(cur, [678906], "2026-06-25") == []


def test_save_and_load_video_map():
    conn = _conn()
    cur = conn.cursor()
    save_play_videos(cur, 776911, [
        {"play_id": "abc", "title": "t", "mp4_url": "https://x/a.mp4"},
    ], NOW)
    save_play_videos(cur, 776911, [
        {"play_id": "abc", "title": "t", "mp4_url": "https://x/a.mp4"},
    ], NOW)  # REPLACE，不重複
    vm = load_video_map(cur)
    assert vm == {776911: {"abc": "https://x/a.mp4"}}


def test_fetch_highlight_videos(monkeypatch):
    from site_builder.sync import statcast as sync_statcast_mod

    conn = _conn()

    def fake_content(game_pk):
        if game_pk == 776911:
            return {"highlights": {"highlights": {"items": [{
                "guid": "abc", "title": "K",
                "playbacks": [{"name": "mp4Avc", "url": "https://x/k.mp4"}],
            }]}}}
        return {}

    monkeypatch.setattr(sync_statcast_mod, "get_game_content", fake_content)
    written = sync_statcast_mod.fetch_highlight_videos(conn, [678906], now_iso=NOW)
    assert written == 1
    cur = conn.cursor()
    assert load_video_map(cur) == {776911: {"abc": "https://x/k.mp4"}}
    # 700001 標記為 0 部；776911 找到影片 → 不再是 candidate
    cur.execute("SELECT videos_found FROM game_content_processed WHERE game_pk=776911")
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT videos_found FROM game_content_processed WHERE game_pk=700001")
    assert cur.fetchone()[0] == 0

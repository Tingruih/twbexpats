"""play_videos / game_content_processed 查詢（逐球精華影片快取）。"""


def save_play_videos(cur, game_pk: int, videos: list[dict], now_iso: str):
    for v in videos:
        cur.execute(
            "INSERT OR REPLACE INTO play_videos "
            "(game_pk, play_id, title, mp4_url, fetched_at) VALUES (?,?,?,?,?)",
            (game_pk, v["play_id"], v.get("title", ""), v["mp4_url"], now_iso),
        )


def mark_content_processed(cur, game_pk: int, videos_found: int, now_iso: str):
    cur.execute(
        "INSERT OR REPLACE INTO game_content_processed "
        "(game_pk, processed_at, videos_found) VALUES (?,?,?)",
        (game_pk, now_iso, videos_found),
    )


def content_fetch_candidates(cur, roster_ids, retry_cutoff_date: str) -> list[int]:
    """要抓 /content 的 MLB game_pk：從未處理過的，加上「處理過但 0 部影片
    且比賽日期仍在重試窗內」的（Savant/statsapi 精華索引有 1 天以上延遲）。"""
    if not roster_ids:
        return []
    ids = sorted(set(roster_ids))
    placeholders = ",".join("?" * len(ids))
    cur.execute(
        "SELECT DISTINCT g.game_id FROM game_logs g "
        "LEFT JOIN game_content_processed c ON c.game_pk = g.game_id "
        f"WHERE g.sport_level = 'MLB' AND g.player_mlb_id IN ({placeholders}) "
        "AND (c.game_pk IS NULL "
        "     OR (c.videos_found = 0 AND g.date >= ?))",
        [*ids, retry_cutoff_date],
    )
    return [row[0] for row in cur.fetchall() if row[0] is not None]


def load_video_map(cur) -> dict[int, dict[str, str]]:
    cur.execute("SELECT game_pk, play_id, mp4_url FROM play_videos")
    out: dict[int, dict[str, str]] = {}
    for game_pk, play_id, mp4_url in cur.fetchall():
        out.setdefault(game_pk, {})[play_id] = mp4_url
    return out

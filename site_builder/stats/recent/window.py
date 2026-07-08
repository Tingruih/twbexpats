"""近 N 天出賽視窗載入 + 單場資料分級（Tier）判定。"""

import datetime

from ...util.dates import parse_date
from ...util.json import loads_json_dict, loads_json_list

WINDOW_DAYS = 7

# Tier 門檻（plan §0.2）
_T1_RATIO = 0.8
_T2_RATIO = 0.1


def game_tier(pitches: list[dict]) -> int:
    """單場資料等級：1 完整追蹤 / 2 部分 / 3 僅結果。"""
    if not pitches:
        return 3
    tracked = sum(
        1 for p in pitches
        if p.get("px") is not None and p.get("start_speed") is not None
    )
    ratio = tracked / len(pitches)
    if ratio >= _T1_RATIO:
        return 1
    if ratio > _T2_RATIO:
        return 2
    return 3


def load_recent_window(cur, roster_ids, *, today=None, days: int = WINDOW_DAYS):
    """回傳視窗內有出賽的球員清單（結構見 tests/test_recent_window.py）。"""
    if not roster_ids:
        return []
    today = today or datetime.date.today()
    cutoff = (today - datetime.timedelta(days=days)).isoformat()
    ids = sorted(roster_ids)
    placeholders = ",".join("?" * len(ids))
    cur.execute(
        "SELECT g.player_mlb_id, g.date, g.game_id, g.opponent, g.is_home,"
        "       g.sport_level, g.stats_json, g.pitches_json, g.events_json,"
        "       p.name_en, p.name_tw, p.team, p.level, p.position "
        "FROM game_logs g JOIN players p ON p.mlb_id = g.player_mlb_id "
        f"WHERE g.date >= ? AND g.player_mlb_id IN ({placeholders}) "
        "ORDER BY g.player_mlb_id, g.date",
        [cutoff, *ids],
    )
    by_player: dict[int, dict] = {}
    for row in cur.fetchall():
        pitches = loads_json_list(row[7])
        entry = by_player.setdefault(row[0], {
            "mlb_id": row[0],
            "name_en": row[9], "name_tw": row[10],
            "team": row[11], "level": row[12],
            "position": row[13] or "",
            "is_pitcher": (row[13] or "") == "P",
            "games": [],
        })
        entry["games"].append({
            "date": parse_date(row[1]),
            "game_id": row[2],
            "opponent": row[3],
            "is_home": None if row[4] is None else bool(row[4]),
            "sport_level": row[5] or "",
            "stats": loads_json_dict(row[6]),
            "pitches": pitches,
            "events": loads_json_list(row[8]),
            "tier": game_tier(pitches),
        })
    windows = list(by_player.values())
    windows.sort(
        key=lambda w: max(
            (g["date"] for g in w["games"] if g["date"]),
            default=datetime.date.min,
        ),
        reverse=True,
    )
    return windows

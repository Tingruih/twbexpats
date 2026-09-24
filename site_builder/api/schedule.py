"""Team schedule endpoint (next upcoming game)."""

import datetime
from typing import Optional

from ..levels import SCHEDULE_SPORT_IDS
from ..util.dates import TW_TZ
from .client import BASE_URL, get_json


def get_next_game(team_id: int) -> Optional[dict]:
    """Fetch the next upcoming game for a team (7-day window).

    Returns None when no game is scheduled in the window; raises
    ``FetchError`` when the request fails, so the caller can keep the
    previously stored next game instead of blanking it.
    """
    if not team_id:
        return None

    today = datetime.date.today()
    end_date = today + datetime.timedelta(days=7)
    url = (
        f"{BASE_URL}/schedule"
        f"?teamId={team_id}"
        f"&startDate={today.isoformat()}"
        f"&endDate={end_date.isoformat()}"
        # 不帶 sportId 時 /schedule 只查 MLB，小聯盟 teamId 會查不到比賽
        f"&sportId={','.join(map(str, SCHEDULE_SPORT_IDS))}"
    )

    dates = get_json(url).get("dates", [])

    for date_entry in dates:
        for game in date_entry.get("games", []):
            status = game.get("status", {}).get("abstractGameState", "")
            if status != "Preview":
                continue
            away_team = game.get("teams", {}).get("away", {}).get("team", {})
            home_team = game.get("teams", {}).get("home", {}).get("team", {})
            is_home = home_team.get("id") == team_id

            game_time = ""
            game_date_str = game.get("gameDate", "")
            if game_date_str:
                try:
                    dt = datetime.datetime.fromisoformat(
                        game_date_str.replace("Z", "+00:00")
                    )
                    game_time = dt.astimezone(TW_TZ).strftime("%m/%d %H:%M (UTC+8)")
                except ValueError:
                    # gameDate 不是 ISO 格式：直接顯示原字串的日期時間部分
                    game_time = game_date_str[:16]

            return {
                "date": date_entry.get("date", ""),
                "opponent": (
                    away_team.get("name", "")
                    if is_home
                    else home_team.get("name", "")
                ),
                "is_home": is_home,
                "venue": game.get("venue", {}).get("name", ""),
                "game_time": game_time,
                "status": game.get("status", {}).get("detailedState", ""),
            }

    # 七天內沒有尚未開打的比賽
    return None

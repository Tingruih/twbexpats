"""Team schedule endpoint (next upcoming game)."""

import datetime
import logging
from typing import Optional

from ..util.dates import TW_TZ
from .client import BASE_URL, get_json

logger = logging.getLogger(__name__)


def get_next_game(team_id: int) -> Optional[dict]:
    """Fetch the next upcoming game for a team (7-day window)."""
    if not team_id:
        return None

    today = datetime.date.today()
    end_date = today + datetime.timedelta(days=7)
    url = (
        f"{BASE_URL}/schedule"
        f"?teamId={team_id}"
        f"&startDate={today.isoformat()}"
        f"&endDate={end_date.isoformat()}"
        f"&sportId=1,11,12,13,14,15,16"
    )

    try:
        dates = get_json(url).get("dates", [])

        for date_entry in dates:
            for game in date_entry.get("games", []):
                status = game.get("status", {}).get("abstractGameState", "")
                if status == "Preview":
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
                            game_time = dt.astimezone(TW_TZ).strftime(
                                "%m/%d %H:%M (UTC+8)"
                            )
                        except Exception:
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
    except Exception as e:
        logger.warning("Failed to fetch next game for team_id=%s: %s", team_id, e)
        return None

    return None

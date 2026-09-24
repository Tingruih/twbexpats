"""Game play-by-play endpoint.

抓取失敗時丟出 ``FetchError``（見 client.py），由 sync/statcast.py 統一記錄，
該場比賽的 pbp_version 不變，下次執行重抓。
"""

from ..constants import LIVE_FEED_TIMEOUT
from .client import BASE_URL, get_json


def get_game_play_by_play(game_pk: int) -> dict:
    """Fetch the full withMetrics JSON for a single game.

    Returns the raw dict from MLB Stats API. Caller is responsible for
    walking ``liveData.plays.allPlays`` and extracting pitches.
    Raises ``FetchError`` on failure.
    """
    url = f"{BASE_URL}/game/{game_pk}/withMetrics"
    return get_json(url, timeout=LIVE_FEED_TIMEOUT)


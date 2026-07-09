"""Game content endpoint helpers for per-play highlight videos."""

import logging
from .client import BASE_URL, get_json

logger = logging.getLogger(__name__)


def get_game_content(game_pk: int) -> dict:
    """Fetch /game/{pk}/content, returning an empty dict on failure."""
    url = f"{BASE_URL}/game/{game_pk}/content"
    try:
        return get_json(url)
    except Exception as exc:
        logger.warning("game content failed for game_pk=%s: %s", game_pk, exc)
        return {}


def extract_play_videos(content: dict) -> list[dict]:
    """Return highlight items whose guid matches a playId and has an mp4 URL."""
    items = (
        ((content or {}).get("highlights") or {}).get("highlights") or {}
    ).get("items") or []
    out = []
    for item in items:
        guid = item.get("guid")
        if not guid:
            continue

        mp4 = None
        playbacks = item.get("playbacks") or []
        for playback in playbacks:
            name = playback.get("name") or ""
            url = playback.get("url") or ""
            if name.startswith("mp4Avc") and url.endswith(".mp4"):
                mp4 = url
                break
        if not mp4:
            for playback in playbacks:
                url = playback.get("url") or ""
                if url.endswith(".mp4"):
                    mp4 = url
                    break

        if mp4:
            out.append({
                "play_id": guid,
                "title": item.get("title") or "",
                "mp4_url": mp4,
            })
    return out

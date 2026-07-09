"""Game content endpoint — per-play highlight video URLs (MLB only in practice)."""

import logging

from .client import BASE_URL, get_json

logger = logging.getLogger(__name__)


def get_game_content(game_pk: int) -> dict:
    """Fetch /game/{pk}/content. Best-effort: returns {} on failure."""
    url = f"{BASE_URL}/game/{game_pk}/content"
    try:
        return get_json(url)
    except Exception as e:
        logger.warning("game content failed for game_pk=%s: %s", game_pk, e)
        return {}


def extract_play_videos(content: dict) -> list[dict]:
    """Highlight items whose guid == a play's playId, with a direct mp4 URL.

    guid 為 null 的合輯（賽事濃縮/訪談）與只有 HLS 的 item 一律略過。
    """
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
        for pb in playbacks:
            name = pb.get("name") or ""
            url = pb.get("url") or ""
            if name.startswith("mp4Avc") and url.endswith(".mp4"):
                mp4 = url
                break
        if not mp4:
            for pb in playbacks:
                url = pb.get("url") or ""
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

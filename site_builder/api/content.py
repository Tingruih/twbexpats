"""Game content endpoint helpers for per-play highlight videos."""

from .client import BASE_URL, get_json


def get_game_content(game_pk: int) -> dict:
    """Fetch /game/{pk}/content; raises ``FetchError`` on failure.

    失敗不能回 {}：呼叫端會把「沒有影片」記進 game_content_processed，
    超過 CONTENT_RETRY_DAYS 的比賽就永遠不會再抓。
    """
    url = f"{BASE_URL}/game/{game_pk}/content"
    return get_json(url)


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

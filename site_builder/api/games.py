"""Game live-feed endpoints and sport-level helpers."""

import logging

from ..constants import LIVE_FEED_TIMEOUT
from ..levels import sport_id_to_code, sport_name_to_code
from .client import BASE_URL_V11, get_json

logger = logging.getLogger(__name__)


def get_game_play_by_play(game_pk: int) -> dict:
    """Fetch the full live-feed JSON for a single game.

    Returns the raw dict from MLB Stats API. Caller is responsible for
    walking ``liveData.plays.allPlays`` and extracting pitches.
    """
    url = f"{BASE_URL_V11}/game/{game_pk}/feed/live"
    try:
        return get_json(url, timeout=LIVE_FEED_TIMEOUT)
    except Exception as e:
        logger.warning("playByPlay failed for game_pk=%s: %s", game_pk, e)
        return {}


def sport_obj_to_abbr(sport: dict) -> str:
    """Convert an MLB Stats API sport object to an abbreviation string.

    Prefers sportId; falls back to the sport name. Both lookups go through the
    single level registry in ``site_builder.levels``.
    """
    if not sport:
        return ""
    abbr = sport_id_to_code(sport.get("id", 0))
    if abbr:
        return abbr
    return sport_name_to_code(sport.get("name", ""))


def get_game_sport_level(game_pk: int) -> str:
    """Fetch only the sport abbreviation (e.g. 'MLB', 'AAA') for a single game.

    The live-feed ``gameData.game`` node does not expose a sport field; the
    authoritative sport info is at ``gameData.teams.home.sport``.
    Uses a fields-filtered request so the payload is small.

    Returns an empty string on failure.
    """
    url = (
        f"{BASE_URL_V11}/game/{game_pk}/feed/live"
        "?fields=gameData,teams,home,sport,id,name"
    )
    try:
        data = get_json(url)
        sport = (
            data.get("gameData", {})
            .get("teams", {})
            .get("home", {})
            .get("sport", {})
        )
        return sport_obj_to_abbr(sport)
    except Exception as e:
        logger.warning("get_game_sport_level failed for game_pk=%s: %s", game_pk, e)
        return ""

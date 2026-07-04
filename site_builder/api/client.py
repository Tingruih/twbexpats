"""Shared MLB Stats API request plumbing."""

import requests

from ..constants import API_TIMEOUT

BASE_URL = "https://statsapi.mlb.com/api/v1"
# The live feed (play-by-play) lives on the v1.1 API.
BASE_URL_V11 = "https://statsapi.mlb.com/api/v1.1"


def get_json(url: str, timeout: int = API_TIMEOUT) -> dict:
    """GET *url* and return the parsed JSON body; raises on HTTP errors."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

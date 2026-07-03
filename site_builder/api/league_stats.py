"""Team/league aggregate endpoints — MLB Stats API.

Used to compute FIP constants from real league-wide pitching totals instead
of a hand-copied source. Both endpoints return one row per team, so a whole
tier's data comes back in a single call each — no per-player fetching.
"""

import logging

from .client import BASE_URL, get_json

logger = logging.getLogger(__name__)


def fetch_team_league_map(sport_id: int, year: int) -> dict[int, str]:
    """{team_id: league_name} for every team in *sport_id* during *year*.

    api endpoint: /teams?sportId={sport_id}&season={year}
    """
    url = f"{BASE_URL}/teams?sportId={sport_id}&season={year}"
    try:
        teams = get_json(url).get("teams", [])
    except Exception as e:
        logger.warning("teams fetch failed for sportId=%s season=%s: %s", sport_id, year, e)
        return {}
    return {
        t["id"]: t["league"]["name"]
        for t in teams
        if t.get("id") is not None and t.get("league", {}).get("name")
    }


def fetch_team_pitching_totals(sport_id: int, year: int) -> list[dict]:
    """Per-team season pitching totals for every team in *sport_id*/*year*.

    api endpoint: /teams/stats?sportId={sport_id}&stats=season&group=pitching&season={year}

    Returns [{"team_id": int, "hr": int, "bb": int, "hbp": int, "k": int,
    "earned_runs": int, "outs": int}, ...] — the raw counting stats needed to
    solve for a league's FIP constant. Skips any split missing a usable
    "outs" figure (extreme edge case: a team with zero innings pitched).
    """
    url = (
        f"{BASE_URL}/teams/stats?sportId={sport_id}&stats=season"
        f"&group=pitching&season={year}"
    )
    try:
        stats = get_json(url).get("stats", [{}])
        splits = stats[0].get("splits", []) if stats else []
    except Exception as e:
        logger.warning(
            "teams/stats fetch failed for sportId=%s season=%s: %s", sport_id, year, e
        )
        return []

    out = []
    for split in splits:
        team_id = split.get("team", {}).get("id")
        stat = split.get("stat", {})
        outs = stat.get("outs")
        if team_id is None or not outs:
            continue
        out.append({
            "team_id": team_id,
            "hr": stat.get("homeRuns") or 0,
            "bb": stat.get("baseOnBalls") or 0,
            "hbp": stat.get("hitBatsmen") or 0,
            "k": stat.get("strikeOuts") or 0,
            "earned_runs": stat.get("earnedRuns") or 0,
            "outs": outs,
        })
    return out

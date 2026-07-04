"""External data clients (MLB Stats API + tjstats.ca).

Submodules:
    client       — base URLs and the shared GET helper
    players      — player profile endpoint
    stats        — yearByYear / seasonAdvanced / gameLog / sabermetrics / expected
    games        — live-feed (play-by-play) endpoints and sport-level helpers
    schedule     — next-game lookup
    league_stats — team/league aggregate pitching totals (FIP constant inputs)
    tjstats      — TJStats park factors and league constants (HTML scrape)

Public functions are re-exported here so callers can simply
``from site_builder.api import get_player_profile``.
"""

from .games import get_game_play_by_play, get_game_sport_level  # noqa: F401
from .league_stats import fetch_team_league_map, fetch_team_pitching_totals  # noqa: F401
from .players import get_player_profile  # noqa: F401
from .schedule import get_next_game  # noqa: F401
from .stats import (  # noqa: F401
    get_game_logs,
    get_player_advanced_stats,
    get_player_expected_stats,
    get_player_sabermetrics,
    get_player_stats,
)
from .tjstats import fetch_league_constants, fetch_park_factors  # noqa: F401

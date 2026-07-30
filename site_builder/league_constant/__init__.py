"""Per-(level, year[, league]) league constants — the run-environment numbers
advanced stats are measured against.

Submodules:
    policy    — the shared "may we trust the cache?" decision
    pitching  — MLB Stats API team pitching totals -> FIP constant
    batting   — tjstats.ca park factors + league constants (wRC+ inputs)

This is the only layer that both fetches from an external source and caches
in SQLite.  ``stats/`` stays pure (every constant arrives as an argument) and
``db/`` stays a plain row-access layer; the dependency direction here is
one-way: league_constant -> api / stats / db.schema, never back.

Each submodule exposes a per-run resolver class whose ``for_level(level,
year)`` method memoizes across a whole sync or build run.  The memoization
granularity is deliberately hidden inside the resolver: park factors come
back per (level, year) but league constants come back a whole year at a time,
and a caller that memoized only per (level, year) would re-scrape the
league-constants page once for every level.

Public names are re-exported here so callers can simply
``from site_builder.league_constant import BattingConstants``.
"""

from .batting import (  # noqa: F401
    BattingConstant,
    BattingConstants,
    get_batting_constants,
    publishes_constants,
)
from .pitching import PitchingConstants, get_pitching_constants  # noqa: F401
from .policy import RefreshPolicy, should_use_cache  # noqa: F401

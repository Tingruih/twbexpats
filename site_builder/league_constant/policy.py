"""Cache-refresh policy shared by both league-constant supply chains.

The two chains disagree about the season in progress, and that disagreement
is the entire reason this module exists:

  - FINAL_ONCE_PUBLISHED  — the external source publishes a number and never
    revises it (tjstats.ca park factors / league constants).  Once a slice is
    cached it is reused forever, including for the year in progress.
  - ACCUMULATES_IN_SEASON — the number is a running total that keeps growing
    while the season is played (the MLB team pitching totals behind the FIP
    constant).  The current year's cached row is only a snapshot of the last
    fetch, so it is re-fetched every run.

Before this module the two policies were two differently-worded ``if``
statements in two files, and the only way to see how they differed was to
open both and diff them by hand.
"""

from enum import Enum, auto

from ..constants import SEASON_YEAR


class RefreshPolicy(Enum):
    """How a supply chain's numbers behave over the course of a season."""

    FINAL_ONCE_PUBLISHED = auto()
    ACCUMULATES_IN_SEASON = auto()


def should_use_cache(
    year: int, *, policy: RefreshPolicy, force_refresh: bool
) -> bool:
    """Whether *year*'s cached slice may be trusted instead of re-fetching.

    ``force_refresh`` (the ``--update-constants`` build.py flag) always wins.
    Otherwise only ACCUMULATES_IN_SEASON cares about the year: a season at or
    after ``constants.SEASON_YEAR`` is still accumulating, so its cached row
    must never be treated as final.
    """
    if force_refresh:
        return False
    if policy is RefreshPolicy.ACCUMULATES_IN_SEASON and year >= SEASON_YEAR:
        return False
    return True

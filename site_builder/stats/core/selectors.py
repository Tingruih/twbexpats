"""Domain selectors over season-stat rows (appearance / highest level)."""

from typing import Optional

from ...levels import level_rank, resolve_tier
from .innings import ip_to_outs


def has_appearance(stat) -> bool:
    if not stat:
        return False
    if (stat.gp or 0) > 0:
        return True
    if (stat.pa or 0) > 0:
        return True
    if (stat.ab or 0) > 0:
        return True
    if (stat.bf or 0) > 0:
        return True
    return ip_to_outs(stat.ip) > 0


def highest_level_row(stats):
    """Return the stat row for the highest level a player ever reached, or None.

    Ranking goes through :func:`level_rank` (see ``site_builder.levels``), which
    collapses every historical spelling onto its tier, so the comparison is
    correct across the 2021 MiLB reorganization.  Rows with real appearances are
    preferred; if none have appearances we fall back to all rows.

    The row carries both ``sport_level`` (raw) and ``year``, so callers can
    render the period-accurate display via :func:`levels.level_display`.
    """
    if not stats:
        return None
    appeared = [s for s in stats if has_appearance(s)]
    pool = appeared or list(stats)
    return min(pool, key=lambda s: level_rank(s.sport_level))


def highest_level(stats) -> Optional[str]:
    """Return the canonical tier key of the highest level reached (or None).

    Hierarchy (highest → lowest): MLB > AAA > AA > A+ > A > A- > ROK.  A pre-2021
    "A(Adv)" peak is reported as its tier key "A+".  For period-accurate display
    use :func:`highest_level_row` + :func:`levels.level_display` instead.
    """
    best = highest_level_row(stats)
    if best is None:
        return None
    tier = resolve_tier(best.sport_level)
    return tier.key if tier else (best.sport_level or None)

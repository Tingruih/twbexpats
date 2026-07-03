"""xWPCT — expected winning percentage from FIP (Pythagenpat, exponent 1.83).

Uses the per-level league RA/9 from ``constants.LEAGUE_RA9`` (annual —
refresh each spring).
"""

from typing import Optional

from ...constants import LEAGUE_RA9_DEFAULT, get_league_ra9


def compute_xwpct(fip: Optional[float], sport_level: str,
                  year: Optional[int] = None) -> Optional[float]:
    if fip is None or fip <= 0:
        return None
    lg_ra, _exact = get_league_ra9(sport_level, year)
    if lg_ra is None:
        lg_ra = LEAGUE_RA9_DEFAULT
    try:
        xwpct = 1 / (1 + (fip / lg_ra) ** 1.83)
        return round(xwpct, 3)
    except (ValueError, ZeroDivisionError):
        return None

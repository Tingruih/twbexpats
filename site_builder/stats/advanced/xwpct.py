"""xWPCT — expected winning percentage from FIP, fixed-exponent (1.83)
Pythagorean-style formula. (Not Pythagenpat: Pythagenpat derives its exponent
from the run environment; this project fixes it at 1.83.)

FIP is calibrated to league ERA, not to runs allowed — the constant is solved
so that a league-average pitcher's FIP equals lgERA (see
``compute_league_fip_constant`` in stats.advanced.fip). So the denominator
here is ``lg_era``, the same-scale number computed alongside the FIP constant
from the same team pitching totals. Dividing by a runs-allowed figure instead
would mix in unearned runs that FIP was never scaled against, biasing every
xWPCT upward.

compute_xwpct does no I/O or lookup of its own: the caller resolves lg_era
via ``league_constant.pitching`` and passes it in, the same pattern
``compute_fip()`` uses for ``c_fip``.
"""

from typing import Optional


def compute_xwpct(
    fip: Optional[float], lg_era: Optional[float]
) -> Optional[float]:
    """Expected winning percentage, rounded to three decimals.

    Returns None when either input is missing or non-positive — an
    unresolvable run environment makes the stat unavailable rather than
    defaulting to an assumed one.
    """
    if fip is None or fip <= 0 or lg_era is None or lg_era <= 0:
        return None
    try:
        xwpct = 1 / (1 + (fip / lg_era) ** 1.83)
        return round(xwpct, 3)
    except (ValueError, ZeroDivisionError):
        return None

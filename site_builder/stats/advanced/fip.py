"""FIP — fielding independent pitching (MiLB path; MLB FIP comes from the API).

FIP = (13·HR + 3·(BB+HBP) − 2·K) / IP + C, where C is the per-level/per-year
constant from ``constants.FIP_CONSTANTS`` (annual — refresh each spring).
"""

from typing import Optional

from ...constants import FIP_DEFAULT_CONSTANT, get_fip_constant
from ..core.innings import ip_to_outs


def compute_fip(hr, bb, hbp, k, ip, sport_level: str, year: int,
                c_fip: Optional[float] = None) -> Optional[float]:
    """MiLB FIP using known or supplied constant.

    ``ip`` is in baseball notation (7.2 = 7⅔ innings); converted via
    ip_to_outs to the true fractional innings, matching the aggregation path.
    """
    ip_actual = ip_to_outs(ip) / 3.0
    if ip_actual <= 0:
        return None
    if c_fip is None:
        # Exact (level, year) hit, else latest year at the level, else default.
        c_fip, _exact = get_fip_constant(sport_level, year)
    if c_fip is None:
        c_fip = FIP_DEFAULT_CONSTANT

    hr = hr or 0
    bb = bb or 0
    hbp = hbp or 0
    k = k or 0
    try:
        fip = (13 * hr + 3 * (bb + hbp) - 2 * k) / ip_actual + c_fip
        return round(fip, 2)
    except (TypeError, ZeroDivisionError):
        return None

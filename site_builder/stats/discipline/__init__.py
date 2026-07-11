"""Plate-discipline rates from pitch-level data — one stat per file.

Every module takes the dict produced by ``stats.core.pitches.aggregate_pitches``
(referred to as *agg*) so the underlying single pass is never repeated.
"""

from .csw_pct import compute_csw_pct
from .o_swing_pct import compute_o_swing_pct
from .swing_pct import compute_swing_pct
from .swstr_pct import compute_swstr_pct
from .whiff_pct import compute_whiff_pct
from .z_contact_pct import compute_z_contact_pct
from .z_swing_pct import compute_z_swing_pct
from .zone_pct import compute_zone_pct


def discipline_metrics(agg: dict) -> dict:
    """Build the plate-discipline metrics dict from aggregate_pitches output.

    Includes each rate's own denominator count (``*_den``) alongside the
    percentage — ``combine.py`` needs the true denominator to weight a
    cross-level average correctly; ``total_pitches`` is only the right
    weight for the rates whose denominator actually is total pitches.
    """
    return {
        "swing_pct": compute_swing_pct(agg),
        "whiff_pct": compute_whiff_pct(agg),
        "whiff_pct_den": len(agg["swings"]),
        "swstr_pct": compute_swstr_pct(agg),
        "csw_pct": compute_csw_pct(agg),
        "z_swing_pct": compute_z_swing_pct(agg),
        "z_swing_pct_den": len(agg["in_zone"]),
        "o_swing_pct": compute_o_swing_pct(agg),
        "o_swing_pct_den": len(agg["out_zone"]),
        "z_contact_pct": compute_z_contact_pct(agg),
        "z_contact_pct_den": len(agg["in_zone_swings"]),
        "zone_pct": compute_zone_pct(agg),
    }

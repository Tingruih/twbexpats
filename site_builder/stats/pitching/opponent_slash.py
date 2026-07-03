"""Opponent slash line — p_avg / p_obp / p_slg / p_ops (what batters hit
against this pitcher), baseball-formatted strings.

Kept as one module because the four values share intermediate floats
(OPS needs the unrounded OBP and SLG).
"""

from ...util.numbers import safe_float
from ..batting.avg import compute_avg
from ..batting.obp import compute_obp
from ..batting.ops import compute_ops
from ..batting.slg import compute_slg
from ..core.formatting import fmt_avg


def annotate_opponent_slash(s) -> None:
    """Fill p_avg/p_obp/p_slg/p_ops on a stat row, only where currently None."""
    p_ab = s.get("p_ab")
    if not p_ab or p_ab <= 0:
        return
    p_hits = s.get("p_hits")
    p_tb   = s.get("p_tb")
    bb     = s.get("bb")
    p_hbp  = s.get("p_hbp")
    p_sf   = s.get("p_sac_flies") or 0

    if s.get("p_avg") is None and p_hits is not None:
        s["p_avg"] = fmt_avg(compute_avg(p_hits, p_ab))

    # Only compute OBP when hits/bb/hbp are all known — unlike compute_obp's
    # default of treating missing components as 0, a silently-incomplete
    # opponent OBP would understate the true value.
    p_obp_f = None
    if p_hits is not None and bb is not None and p_hbp is not None:
        p_obp_f = compute_obp(p_hits, bb, p_hbp, p_ab, p_sf)
    if s.get("p_obp") is None and p_obp_f is not None:
        s["p_obp"] = fmt_avg(p_obp_f)

    p_slg_f = None
    if p_tb is not None:
        p_slg_f = compute_slg(p_tb, p_ab)
    if s.get("p_slg") is None and p_slg_f is not None:
        s["p_slg"] = fmt_avg(p_slg_f)

    if s.get("p_ops") is None:
        # Use already-computed floats if available, else parse strings
        obp_f = p_obp_f if p_obp_f is not None else safe_float(s.get("p_obp"))
        slg_f = p_slg_f if p_slg_f is not None else safe_float(s.get("p_slg"))
        if obp_f is not None and slg_f is not None:
            s["p_ops"] = fmt_avg(compute_ops(obp_f, slg_f))

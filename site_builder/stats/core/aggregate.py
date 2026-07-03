"""Counting-stat summation and rate recomputation over season rows."""

from ...constants import COUNTING_FIELDS
from ...util.obj import Obj
from ..batting.avg import compute_avg
from ..batting.obp import compute_obp
from ..batting.ops import compute_ops
from ..batting.slg import compute_slg
from ..pitching.era import compute_era
from ..pitching.whip import compute_whip
from .innings import ip_to_outs, outs_to_ip


def sum_counting(stats, result):
    for field in COUNTING_FIELDS:
        values = [getattr(s, field) for s in stats]
        if all(v is None for v in values):
            result[field] = None
        else:
            result[field] = sum(v or 0 for v in values)


def compute_rate_stats(agg):
    """Compute batting / pitching rate stats on an aggregated Obj."""
    if agg.get("ab") and agg["ab"] > 0:
        agg["avg"] = compute_avg(agg.get("hits"), agg["ab"])
        agg["obp"] = compute_obp(
            agg.get("hits"),
            agg.get("hit_bb"),
            agg.get("hbp"),
            agg["ab"],
            agg.get("sac_flies"),
        )
        agg["slg"] = compute_slg(agg.get("tb"), agg["ab"])
        agg["ops"] = compute_ops(agg.get("obp"), agg.get("slg"))
    else:
        agg["avg"] = agg["obp"] = agg["slg"] = agg["ops"] = None

    # agg["ip"] is baseball decimal notation (e.g. 7.2 = 7⅔ innings = 7.333... real innings).
    # Must convert via ip_to_outs → divide by 3 to get true fractional innings before
    # computing rate stats, otherwise ERA/WHIP will be slightly wrong.
    _ip_outs = ip_to_outs(agg.get("ip"))
    _ip_actual = _ip_outs / 3.0  # real innings pitched as a fraction
    if _ip_actual > 0:
        agg["era"] = compute_era(agg.get("earned_runs"), _ip_actual)
        agg["whip"] = compute_whip(agg.get("p_hits"), agg.get("bb"), _ip_actual)
    else:
        agg["era"] = agg["whip"] = None


def aggregate_stats(stats):
    """Sum counting stats, compute IP, and derive rate stats for a list of rows.

    Shared core of career and season-combined aggregation.
    Returns a new :class:`Obj`.
    """
    agg = Obj()
    sum_counting(stats, agg)
    total_outs = sum(ip_to_outs(s.ip) for s in stats)
    agg["ip"] = outs_to_ip(total_outs)
    compute_rate_stats(agg)
    return agg

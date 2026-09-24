"""Counting-stat summation and rate recomputation over season rows."""

from ...constants import COUNTING_FIELD_GROUPS
from ...util.obj import Obj
from ..batting.avg import compute_avg
from ..batting.obp import compute_obp
from ..batting.ops import compute_ops
from ..batting.slg import compute_slg
from ..pitching.era import compute_era
from ..pitching.whip import compute_whip
from .innings import ip_to_outs, outs_to_ip


def sum_counting(stats, result):
    """依 ``COUNTING_FIELD_GROUPS`` 加總計數欄位，寫入 *result*。

    某列整組都沒有值（例如野手列沒有投球數據）時該列貢獻 0；某列有這組數據
    卻缺某一欄時，該欄總和視為未知（None）。若把後者當 0 加總，分母（p_ab、
    outs）照常累加、分子卻少算，曹錦輝 2003 年度合計的被打 SLG 會算成 .150
    （MLB 單列為 .515）。
    """
    for group in COUNTING_FIELD_GROUPS:
        present = [s for s in stats if any(s.get(f) is not None for f in group)]
        for field in group:
            values = [s.get(field) for s in present]
            # 沒有任何列帶這組數據，或有列帶了這組卻缺這一欄：總和未知
            if not values or any(v is None for v in values):
                result[field] = None
            else:
                result[field] = sum(values)


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
        # 刻意用上面已捨入的 OBP、SLG 相加：MLB API 的 OPS 慣例（見 batting/ops.py）
        agg["ops"] = compute_ops(agg.get("obp"), agg.get("slg"))
    else:
        agg["avg"] = agg["obp"] = agg["slg"] = agg["ops"] = None

    # agg["ip"] 是棒球局數記法（7.2 = 7⅔ 局），先轉 outs 再算率（見 core/innings.py）
    outs = ip_to_outs(agg.get("ip"))
    if outs > 0:
        agg["era"] = compute_era(agg.get("earned_runs"), outs)
        agg["whip"] = compute_whip(agg.get("p_hits"), agg.get("bb"), outs)
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

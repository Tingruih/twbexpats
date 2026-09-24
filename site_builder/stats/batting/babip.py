"""BABIP — batting average on balls in play: (H − HR) / (AB − SO − HR + SF).

Shared by batters and pitchers (pitcher version feeds p_* fields). The
denominator is AB-based: AB already excludes BB/HBP/SH by the official rule,
so only SF needs adding back. (A BF-based denominator would systematically
deflate BABIP — it under-subtracts HBP and SH.)
"""

from ...util.numbers import ratio


def compute_babip(hits, hr, ab, so, sac_flies=0):
    # 任一必要計數缺值
    if any(v is None for v in [hits, hr, ab, so]):
        return None
    denom = ab - so - hr + (sac_flies or 0)
    # 沒有場內球
    if denom <= 0:
        return None
    return ratio(hits - hr, denom)

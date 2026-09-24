"""AVG — batting average: H / AB."""

from ...util.numbers import ratio


def compute_avg(hits, ab):
    # 沒有打數
    if not ab or ab <= 0:
        return None
    return ratio(hits or 0, ab)

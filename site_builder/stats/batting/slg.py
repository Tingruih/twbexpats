"""SLG — slugging percentage: TB / AB."""

from ...util.numbers import ratio


def compute_slg(tb, ab):
    # 沒有打數，或壘打數缺值
    if not ab or ab <= 0 or tb is None:
        return None
    return ratio(tb, ab)

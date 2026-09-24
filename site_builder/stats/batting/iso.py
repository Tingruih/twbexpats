"""ISO — isolated power: (TB − H) / AB.

FanGraphs 定義 ISO = SLG − AVG，等價於 (TB − H) / AB。這裡直接用計數算，不拿
已捨入到三位的 SLG、AVG 相減：兩個捨入值相減在約兩成的列會差 .001
（例：1 H、6 TB、11 AB → .545 − .091 = .454，精確值 .4545 → .455）。
"""

from ...util.numbers import ratio


def compute_iso(tb, hits, ab):
    # 壘打數或安打數缺值；AB 為零時 ratio 回 None
    if tb is None or hits is None:
        return None
    return ratio(tb - hits, ab)

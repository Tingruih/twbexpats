"""OBP — on-base percentage: (H + BB + HBP) / (AB + BB + HBP + SF)."""

from ...util.numbers import ratio


def compute_obp(hits, bb, hbp, ab, sac_flies):
    h = hits or 0
    b = bb or 0
    hp = hbp or 0
    a = ab or 0
    sf = sac_flies or 0
    # 分母為零時 ratio 回 None
    return ratio(h + b + hp, a + b + hp + sf)

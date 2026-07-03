"""OBP — on-base percentage: (H + BB + HBP) / (AB + BB + HBP + SF)."""


def compute_obp(hits, bb, hbp, ab, sac_flies):
    h = hits or 0
    b = bb or 0
    hp = hbp or 0
    a = ab or 0
    sf = sac_flies or 0
    denom = a + b + hp + sf
    if denom == 0:
        return None
    return round((h + b + hp) / denom, 3)

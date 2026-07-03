"""OPS — on-base plus slugging: OBP + SLG."""


def compute_ops(obp, slg):
    if obp is None or slg is None:
        return None
    return round(obp + slg, 3)

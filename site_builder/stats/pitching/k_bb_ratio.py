"""K/BB — strikeout-to-walk ratio."""


def compute_k_bb_ratio(so, bb):
    if so is None or bb is None or bb <= 0:
        return None
    return round(so / bb, 2)

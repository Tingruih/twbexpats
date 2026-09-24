"""K/BB — strikeout-to-walk ratio."""

from ...util.numbers import ratio


def compute_k_bb_ratio(so, bb):
    # 三振數缺值，或沒有保送（比值無定義）
    if so is None or bb is None or bb <= 0:
        return None
    return ratio(so, bb, 2)

"""WHIP — walks + hits per inning pitched: (H + BB) × 3 / outs."""

from ...util.numbers import ratio


def compute_whip(hits_allowed, bb, outs):
    # 沒有投球局數，或被安打數未知
    if not outs or outs <= 0 or hits_allowed is None:
        return None
    return ratio(3 * (hits_allowed + (bb or 0)), outs, 2)

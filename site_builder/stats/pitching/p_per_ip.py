"""P/IP — pitches per inning: pitches × 3 / outs."""

from ...util.numbers import ratio


def compute_p_per_ip(pitches, outs):
    # 投球數缺值或沒有投球局數
    if pitches is None or not outs or outs <= 0:
        return None
    # 兩位小數對應 API pitchesPerInning
    return ratio(3 * pitches, outs, 2)

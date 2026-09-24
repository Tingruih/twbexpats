"""Strike% — strikes / total pitches，三位小數 float（顯示格式由 render 的 floatformat 決定）。"""

from ...util.numbers import ratio


def compute_strike_pct(strikes, pitches):
    # 好球數缺值，或沒有投球數
    if strikes is None or not pitches or pitches <= 0:
        return None
    return ratio(strikes, pitches)

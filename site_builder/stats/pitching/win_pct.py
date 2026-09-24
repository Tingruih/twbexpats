"""Win% — W / (W + L)，三位小數 float（顯示格式由 render 的 floatformat 決定）。"""

from ...util.numbers import ratio


def compute_win_pct(wins, losses):
    # 勝敗數缺值
    if wins is None or losses is None:
        return None
    # 沒有勝敗紀錄，分母為零時 ratio 回 None
    return ratio(wins, wins + losses)

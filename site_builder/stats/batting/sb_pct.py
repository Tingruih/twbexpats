"""SB% — stolen-base success rate: SB / (SB + CS)，三位小數 float（顯示格式由 render 的 floatformat 決定）。"""

from ...util.numbers import ratio


def compute_sb_pct(sb, cs):
    # 盜壘或盜壘刺數缺值
    if sb is None or cs is None:
        return None
    # 沒有盜壘嘗試，分母為零時 ratio 回 None
    return ratio(sb, sb + cs)

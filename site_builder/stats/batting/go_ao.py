"""GO/AO — ground-out to air-out ratio (shared by batter and pitcher fields)."""

from ...util.numbers import ratio


def compute_go_ao(ground_outs, air_outs):
    # 滾地/飛球出局數缺值，或沒有飛球出局（比值無定義）
    if ground_outs is None or air_outs is None or air_outs <= 0:
        return None
    return ratio(ground_outs, air_outs, 2)

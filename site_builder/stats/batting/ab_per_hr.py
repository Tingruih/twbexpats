"""AB/HR — at-bats per home run."""

from ...util.numbers import ratio


def compute_ab_per_hr(ab, hr):
    # 打數缺值，或沒有全壘打（比值無定義）
    if ab is None or not hr or hr <= 0:
        return None
    # 兩位小數對應 API atBatsPerHomeRun
    return ratio(ab, hr, 2)

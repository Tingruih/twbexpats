"""BB% — walk rate: BB / PA (batters) or BB / BF (pitchers)."""

from ...util.numbers import ratio


def compute_bb_pct(bb, plate_appearances):
    # 保送數缺值，或沒有打席
    if bb is None or not plate_appearances or plate_appearances <= 0:
        return None
    return ratio(bb, plate_appearances)

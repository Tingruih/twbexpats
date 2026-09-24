"""K% — strikeout rate: SO / PA (batters) or SO / BF (pitchers)."""

from ...util.numbers import ratio


def compute_k_pct(so, plate_appearances):
    # 三振數缺值，或沒有打席
    if so is None or not plate_appearances or plate_appearances <= 0:
        return None
    return ratio(so, plate_appearances)

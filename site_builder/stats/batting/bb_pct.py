"""BB% — walk rate: BB / PA (batters) or BB / BF (pitchers)."""


def compute_bb_pct(bb, plate_appearances):
    if bb is None or not plate_appearances or plate_appearances <= 0:
        return None
    return round(bb / plate_appearances, 3)

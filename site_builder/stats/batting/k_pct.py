"""K% — strikeout rate: SO / PA (batters) or SO / BF (pitchers)."""


def compute_k_pct(so, plate_appearances):
    if so is None or not plate_appearances or plate_appearances <= 0:
        return None
    return round(so / plate_appearances, 3)

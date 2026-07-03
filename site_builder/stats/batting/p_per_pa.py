"""P/PA — pitches per plate appearance (batters: pitches seen / PA;
pitchers: pitches thrown / BF)."""


def compute_p_per_pa(pitches, plate_appearances):
    if pitches is None or not plate_appearances or plate_appearances <= 0:
        return None
    return round(pitches / plate_appearances, 2)

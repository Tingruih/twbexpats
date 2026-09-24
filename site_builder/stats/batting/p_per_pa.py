"""P/PA — pitches per plate appearance (batters: pitches seen / PA;
pitchers: pitches thrown / BF)."""

from ...util.numbers import ratio


def compute_p_per_pa(pitches, plate_appearances):
    # 投球數缺值，或沒有打席
    if pitches is None or not plate_appearances or plate_appearances <= 0:
        return None
    # 三位小數對應 API pitchesPerPlateAppearance
    return ratio(pitches, plate_appearances, 3)

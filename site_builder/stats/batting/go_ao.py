"""GO/AO — ground-out to air-out ratio (shared by batter and pitcher fields)."""


def compute_go_ao(ground_outs, air_outs):
    if ground_outs is None or air_outs is None or air_outs <= 0:
        return None
    return round(ground_outs / air_outs, 2)

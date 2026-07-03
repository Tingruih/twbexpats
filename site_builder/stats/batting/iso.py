"""ISO — isolated power: SLG − AVG."""


def compute_iso(slg, avg):
    if slg is None or avg is None:
        return None
    return round(slg - avg, 3)

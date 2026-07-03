"""SLG — slugging percentage: TB / AB."""


def compute_slg(tb, ab):
    if not ab or ab <= 0:
        return None
    if tb is None:
        return None
    return round(tb / ab, 3)

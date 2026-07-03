"""AVG — batting average: H / AB."""


def compute_avg(hits, ab):
    if not ab or ab <= 0:
        return None
    return round((hits or 0) / ab, 3)

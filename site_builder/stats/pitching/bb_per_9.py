"""BB/9 — walks per nine innings."""


def compute_bb_per_9(bb, ip_actual):
    if bb is None or not ip_actual or ip_actual <= 0:
        return None
    return round(bb * 9 / ip_actual, 1)

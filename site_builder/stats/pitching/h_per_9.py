"""H/9 — hits allowed per nine innings."""


def compute_h_per_9(hits_allowed, ip_actual):
    if hits_allowed is None or not ip_actual or ip_actual <= 0:
        return None
    return round(hits_allowed * 9 / ip_actual, 1)

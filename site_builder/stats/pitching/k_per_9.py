"""K/9 — strikeouts per nine innings."""


def compute_k_per_9(so, ip_actual):
    if so is None or not ip_actual or ip_actual <= 0:
        return None
    return round(so * 9 / ip_actual, 1)

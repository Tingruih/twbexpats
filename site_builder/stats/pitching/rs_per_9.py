"""RS/9 — run support per nine innings."""


def compute_rs_per_9(run_support, ip_actual):
    if run_support is None or not ip_actual or ip_actual <= 0:
        return None
    return round(run_support * 9 / ip_actual, 2)

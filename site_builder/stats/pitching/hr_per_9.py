"""HR/9 — home runs allowed per nine innings."""


def compute_hr_per_9(hr_allowed, ip_actual):
    if hr_allowed is None or not ip_actual or ip_actual <= 0:
        return None
    return round(hr_allowed * 9 / ip_actual, 2)

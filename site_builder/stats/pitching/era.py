"""ERA — earned run average: ER × 9 / IP (real fractional innings)."""


def compute_era(earned_runs, ip_actual):
    if earned_runs is None or not ip_actual or ip_actual <= 0:
        return None
    return round(earned_runs / ip_actual * 9, 2)

"""P/IP — pitches per inning (real fractional innings)."""


def compute_p_per_ip(pitches, ip_actual):
    if pitches is None or not ip_actual or ip_actual <= 0:
        return None
    return round(pitches / ip_actual, 1)

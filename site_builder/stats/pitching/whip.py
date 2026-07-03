"""WHIP — walks + hits per inning pitched (real fractional innings)."""


def compute_whip(hits_allowed, bb, ip_actual):
    if not ip_actual or ip_actual <= 0:
        return None
    if hits_allowed is None:
        return None
    return round(((hits_allowed or 0) + (bb or 0)) / ip_actual, 2)

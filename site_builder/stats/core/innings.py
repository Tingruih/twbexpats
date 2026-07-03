"""Innings-pitched notation conversions.

Baseball decimal notation (7.2 = 7⅔ innings) must be converted to outs before
any rate math, otherwise ERA/WHIP/per-9 stats come out slightly wrong.
"""


def ip_to_outs(ip_value) -> int:
    if ip_value is None:
        return 0
    whole = int(ip_value)
    thirds = round((ip_value - whole) * 10)
    return whole * 3 + thirds


def outs_to_ip(outs: int):
    if outs == 0:
        return None
    whole = outs // 3
    remainder = outs % 3
    return round(whole + remainder / 10, 1)

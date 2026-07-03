"""XBH — extra-base hits: 2B + 3B + HR (fallback when the API omits it)."""


def compute_xbh(doubles, triples, hr):
    d = doubles or 0
    t = triples or 0
    h = hr or 0
    if d or t or h:
        return d + t + h
    return None

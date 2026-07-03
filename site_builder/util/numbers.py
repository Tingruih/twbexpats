"""Safe numeric conversions and small math helpers."""

import math
from typing import Any, Optional


def safe_float(value: Any, default=None):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default=None):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def ratio(num, den, digits=3):
    """Safe division returning a rounded decimal or None when denominator is 0."""
    if not den:
        return None
    return round(num / den, digits)


def mean(values):
    """Mean of non-None values, or None if empty."""
    vs = [v for v in values if v is not None]
    if not vs:
        return None
    return sum(vs) / len(vs)


def mean_round(values, digits=1):
    """Mean of non-None values, rounded. Returns None if no valid values."""
    v = mean(values)
    return round(v, digits) if v is not None else None


def float_or_none(value) -> Optional[float]:
    """Like safe_float, but also rejects NaN/inf."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None

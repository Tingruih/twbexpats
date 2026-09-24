"""Display unit conversions (imperial → metric)."""

import re

from .numbers import round_half_up

_HEIGHT_RE = re.compile(r"(\d+)['′]\s*(\d+)[\"“”″]?")


def height_to_cm(height_str):
    if not height_str:
        return None
    m = _HEIGHT_RE.match(str(height_str))
    if m:
        feet, inches = int(m.group(1)), int(m.group(2))
        return round_half_up((feet * 12 + inches) * 2.54, 1)
    return None


def lbs_to_kg(weight_lbs):
    if weight_lbs is None:
        return None
    return round_half_up(weight_lbs * 0.453592, 1)

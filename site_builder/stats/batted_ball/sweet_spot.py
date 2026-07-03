"""Sweet spot — launch angle between 8° and 32° (inclusive)."""

from typing import Optional

from ...util.numbers import ratio


def is_sweet_spot(la: Optional[float]) -> bool:
    if la is None:
        return False
    return 8 <= la <= 32


def compute_sweet_spot_pct(la_values: list):
    sweet_spots = sum(1 for la in la_values if is_sweet_spot(la))
    return ratio(sweet_spots, len(la_values))

"""Sweet spot — launch angle between 8° and 32° (inclusive)."""

from typing import Optional


def is_sweet_spot(la: Optional[float]) -> bool:
    if la is None:
        return False
    return 8 <= la <= 32

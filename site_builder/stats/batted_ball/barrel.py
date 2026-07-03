"""Barrel — the Statcast barrel definition."""

from typing import Optional

from ...util.numbers import ratio


def compute_barrel_pct(agg: dict):
    return ratio(agg["barrels"], len(agg["in_play"]))


def is_barrel(ev: Optional[float], la: Optional[float]) -> bool:
    """Statcast barrel definition.

    Minimum EV is 98 mph.  At exactly 98 mph the launch-angle window is
    26°–30°.  For every additional mph above 98:
      - lower bound drops 1°/mph  (floor 8°)
      - upper bound rises 1.5°/mph (ceiling 50°)

    Anchor points:
      98 mph → [26, 30]
     100 mph → [24, 33]
     116 mph → [8,  50]  (both bounds saturated)
    """
    if ev is None or la is None:
        return False
    if ev < 98:
        return False
    delta = ev - 98.0
    la_min = max(8.0,  26.0 - delta)
    la_max = min(50.0, 30.0 + delta * 1.5)
    return la_min <= la <= la_max

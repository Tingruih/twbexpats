"""Hard-hit — the Statcast hard-hit definition (EV ≥ 95 mph)."""

from ...util.numbers import ratio

HARD_HIT_EV_THRESHOLD = 95.0


def compute_hard_hit_pct(agg: dict):
    return ratio(agg["hard_hits"], len(agg["bbe_ev"]))


def is_hard_hit(ev) -> bool:
    return ev is not None and ev >= HARD_HIT_EV_THRESHOLD

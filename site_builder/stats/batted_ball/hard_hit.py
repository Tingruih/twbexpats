"""Hard-hit — the Statcast hard-hit definition (EV ≥ 95 mph)."""

HARD_HIT_EV_THRESHOLD = 95.0


def is_hard_hit(ev) -> bool:
    return ev is not None and ev >= HARD_HIT_EV_THRESHOLD

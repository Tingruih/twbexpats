"""wOBA — weighted on-base average (TJStats fixed linear weights).

Two entry points for the two data sources:
  - :func:`compute_pitch_woba` from cached pitch-level PA outcomes
  - :func:`compute_season_woba` from a season_stats row's counting stats
Both share the weights in ``constants.WOBA_WEIGHTS`` and exclude intentional
walks / sacrifice bunts from the denominator.
"""

from typing import Optional

from ...constants import WOBA_WEIGHTS
from ..core.pa_outcomes import compute_pa_outcome_totals


def compute_pitch_woba(pa_final: list[dict]) -> tuple[float, int]:
    """Compute wOBA numerator and denominator from PA-final pitches.

    Excludes intentional walks, sacrifice bunts, and non-PA baserunning
    events (caught stealing, pickoffs) from the denominator.
    """
    totals = compute_pa_outcome_totals(pa_final)
    return totals["woba_num"], totals["woba_den"]


def compute_season_woba(stat: dict) -> Optional[float]:
    """Compute wOBA from a season_stats row's counting stats.

    Mirrors the pitch-level PA-based wOBA convention: intentional walks are
    excluded from both numerator and denominator (only the unintentional
    portion of walks counts, matching TJStats' own wOBA definition).
    Returns None when there are no usable plate appearances.
    """
    ab = stat.get("ab") or 0
    hits = stat.get("hits") or 0
    doubles = stat.get("doubles") or 0
    triples = stat.get("triples") or 0
    hr = stat.get("hr") or 0
    bb = stat.get("hit_bb") or 0
    ibb = stat.get("ibb") or 0
    hbp = stat.get("hbp") or 0
    sac_flies = stat.get("sac_flies") or 0

    singles = hits - doubles - triples - hr
    unintentional_bb = bb - ibb

    den = ab + unintentional_bb + sac_flies + hbp
    if den <= 0:
        return None

    num = (
        WOBA_WEIGHTS["walk"] * unintentional_bb
        + WOBA_WEIGHTS["hbp"] * hbp
        + WOBA_WEIGHTS["single"] * singles
        + WOBA_WEIGHTS["double"] * doubles
        + WOBA_WEIGHTS["triple"] * triples
        + WOBA_WEIGHTS["home_run"] * hr
    )
    return num / den

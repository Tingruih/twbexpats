"""FIP — fielding independent pitching (MiLB path; MLB FIP comes from the API).

FIP = (13·HR + 3·(BB+HBP) − 2·K) / IP + C, where C is a per-level/per-league
constant. The constant is computed from real league-wide pitching totals
(see ``compute_league_fip_constant`` below) rather than hand-copied from an
external source; the caller resolves it via ``league_constant.pitching`` and
passes it in as ``c_fip`` (``compute_fip`` itself does no I/O — it falls back
to ``FIP_DEFAULT_CONSTANT`` only if the caller couldn't resolve one at all).
"""

from typing import NamedTuple, Optional

from ..core.innings import ip_to_outs

# Last-resort constant when the caller couldn't resolve one at all (fetch
# failure, unrecognized level, season hasn't started yet).  Lives here rather
# than in league_constant/ because that package imports this module — putting
# it there would make the dependency circular.
FIP_DEFAULT_CONSTANT = 3.2


def compute_fip(hr, bb, hbp, k, ip, c_fip: Optional[float] = None) -> Optional[float]:
    """Per-pitcher FIP using a known or supplied constant.

    ``ip`` is in baseball notation (7.2 = 7⅔ innings); converted via
    ip_to_outs to the true fractional innings, matching the aggregation path.
    The resolved constant must come in via ``c_fip`` (the caller looks it up
    from ``league_constant.pitching``), else this falls back to
    ``FIP_DEFAULT_CONSTANT``.

    Returned at full precision (unrounded): the caller rounds for display but
    feeds the raw value into downstream stats (e.g. xwpct), so rounding here
    would leak avoidable error into everything derived from FIP.
    """
    ip_actual = ip_to_outs(ip) / 3.0
    if ip_actual <= 0:
        return None
    if c_fip is None:
        c_fip = FIP_DEFAULT_CONSTANT

    hr = hr or 0
    bb = bb or 0
    hbp = hbp or 0
    k = k or 0
    try:
        return (13 * hr + 3 * (bb + hbp) - 2 * k) / ip_actual + c_fip
    except (TypeError, ZeroDivisionError):
        return None


class LeagueFipConstant(NamedTuple):
    """One (level, year[, league])'s run environment.

    Both fields come out of the same pass over the same team pitching totals:
    the per-pitcher FIP constant, and the league ERA that constant was solved
    against. They are two views of one calculation, which is exactly why
    xWPCT may compare a FIP against ``lg_era`` — see stats.advanced.xwpct.
    """

    fip_constant: float
    lg_era: float


def compute_league_fip_constant(totals: dict) -> Optional[LeagueFipConstant]:
    """Solve for a league's FIP constant and league ERA from its totals.

    Reverses the per-pitcher formula above: C = lgERA − (13·HR + 3·(BB+HBP)
    − 2·K) / lgIP. ``totals`` must have summed-across-every-team counting
    stats: ``hr``, ``bb``, ``hbp``, ``k``, ``earned_runs``, ``outs`` — the
    same shape returned by ``api.league_stats.fetch_team_pitching_totals``
    after grouping/summing by league.

    Both fields are returned at full precision (no rounding): they are stored
    in REAL columns and only the final per-pitcher FIP/xWPCT is rounded for
    display, so truncating here would leak avoidable error into everything
    derived from them.
    """
    outs = totals.get("outs") or 0
    ip = outs / 3.0
    if ip <= 0:
        return None
    lg_era = 9 * (totals.get("earned_runs") or 0) / ip
    hr = totals.get("hr") or 0
    bb = totals.get("bb") or 0
    hbp = totals.get("hbp") or 0
    k = totals.get("k") or 0
    c_fip = lg_era - (13 * hr + 3 * (bb + hbp) - 2 * k) / ip
    return LeagueFipConstant(fip_constant=c_fip, lg_era=lg_era)

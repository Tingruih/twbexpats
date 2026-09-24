"""FIP — fielding independent pitching (MiLB path; MLB FIP comes from the API).

FIP = (13·HR + 3·(BB+HBP) − 2·K) / IP + C, where C is a per-level/per-league
constant. The constant is computed from real league-wide pitching totals
(see ``compute_league_fip_constant`` below) rather than hand-copied from an
external source; the caller resolves it via ``league_constant.pitching`` and
passes it in as ``c_fip`` (``compute_fip`` itself does no I/O).

沒有常數就沒有 FIP：不套用假設的預設常數。2005 年以前的 MiLB 球隊合計沒有
自責分（見 ``compute_league_fip_constant``），常數無從解出，這些季度的 FIP
一律留空；FanGraphs 的 MiLB 數據同樣從 2006 年才開始。
"""

from typing import NamedTuple, Optional

from ..core.innings import ip_to_outs, per_nine


def _fip_raw(hr, bb, hbp, k, outs: int) -> float:
    """(13·HR + 3·(BB+HBP) − 2·K) / IP，尚未加常數；缺值的計數視為 0。

    投手 FIP（加上常數）與聯盟常數（lgERA 減去它）共用這一份公式。
    以 outs 當分母（IP = outs / 3），呼叫端須先確認 outs > 0。
    """
    numerator = 13 * (hr or 0) + 3 * ((bb or 0) + (hbp or 0)) - 2 * (k or 0)
    return numerator * 3 / outs


def compute_fip(hr, bb, hbp, k, ip, c_fip: Optional[float] = None) -> Optional[float]:
    """Per-pitcher FIP using a known or supplied constant.

    ``ip`` is in baseball notation (7.2 = 7⅔ innings); converted via
    ip_to_outs to the true fractional innings, matching the aggregation path.
    The resolved constant must come in via ``c_fip`` (the caller looks it up
    from ``league_constant.pitching``).

    Returned at full precision (unrounded): the caller rounds for display but
    feeds the raw value into downstream stats (e.g. xwpct), so rounding here
    would leak avoidable error into everything derived from FIP.
    """
    # 常數無法解出（見模組 docstring）：不猜預設值，回 None
    if c_fip is None:
        return None
    outs = ip_to_outs(ip)
    # 沒有投球局數，分母為零
    if outs <= 0:
        return None
    try:
        return _fip_raw(hr, bb, hbp, k, outs) + c_fip
    except TypeError:
        # 計數或常數不是數字（stat_json 內容異常）
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
    − 2·K) / lgIP（FanGraphs 定義，見 library.fangraphs.com/pitching/fip/）。 ``totals`` must have summed-across-every-team counting
    stats: ``hr``, ``bb``, ``hbp``, ``k``, ``earned_runs``, ``outs`` — the
    same shape returned by ``api.league_stats.fetch_team_pitching_totals``
    after grouping/summing by league.

    Both fields are returned at full precision (no rounding): they are stored
    in REAL columns and only the final per-pitcher FIP/xWPCT is rounded for
    display, so truncating here would leak avoidable error into everything
    derived from them.

    ``earned_runs`` 為 0 時回 None：MLB Stats API
    ``/teams/stats?stats=season&group=pitching`` 對 2005 年以前的 MiLB 不給
    ``earnedRuns``（``era`` 也是 null），整個聯盟加總出 0 自責分不可能是真實值。
    若照算，lgERA = 0 會解出約 -1 的常數，FIP 會比實際低約 4 分。
    """
    # API 沒給自責分（2005 年以前的 MiLB），常數無從解出
    if not totals.get("earned_runs"):
        return None
    outs = totals.get("outs") or 0
    # 聯盟沒有投球局數，分母為零
    if outs <= 0:
        return None
    # 不捨入：lgERA 是常數的輸入，也原樣存進 league_fip_constants.lg_era
    lg_era = per_nine(totals["earned_runs"], outs, digits=None)
    c_fip = lg_era - _fip_raw(
        totals.get("hr"), totals.get("bb"), totals.get("hbp"), totals.get("k"), outs
    )
    return LeagueFipConstant(fip_constant=c_fip, lg_era=lg_era)

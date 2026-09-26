"""Fill derived advanced stats onto season-stat rows.

Formulas live in the per-stat modules under ``stats/batting`` and
``stats/pitching``; this module only decides *when* a value is filled.  A
field is only ever set when its current value is None, so API-supplied values
are never overwritten.
"""

from ...positions import BATTER
from ..batting.ab_per_hr import compute_ab_per_hr
from ..batting.babip import compute_babip
from ..batting.bb_pct import compute_bb_pct
from ..batting.go_ao import compute_go_ao
from ..batting.iso import compute_iso
from ..batting.k_pct import compute_k_pct
from ..batting.p_per_pa import compute_p_per_pa
from ..batting.sb_pct import compute_sb_pct
from ..batting.xbh import compute_xbh
from ..pitching.bb_per_9 import compute_bb_per_9
from ..pitching.h_per_9 import compute_h_per_9
from ..pitching.hr_per_9 import compute_hr_per_9
from ..pitching.k_bb_ratio import compute_k_bb_ratio
from ..pitching.k_per_9 import compute_k_per_9
from ..pitching.opponent_slash import annotate_opponent_slash
from ..pitching.p_per_ip import compute_p_per_ip
from ..pitching.rs_per_9 import compute_rs_per_9
from ..pitching.strike_pct import compute_strike_pct
from ..pitching.win_pct import compute_win_pct
from .innings import ip_to_outs


def _fill(s, field, value):
    """Set *field* only when the computed value is real (never writes None)."""
    if value is not None:
        s[field] = value


def annotate_row(s, role: str):
    """Fill in ``role``'s derived advanced stats on an Obj (or any dict-like).

    ``s`` 必須已投影到 ``role``（``positions.project_role``）：打擊與投球共用的
    概念名（``so`` / ``hits`` / ``k_pct`` 等）此時就是這個角色的值，所以兩個角色
    讀寫同一組 key，只有分母不同（打者 PA、投手 BF）。
    Only sets a field when its current value is None so that API-supplied
    values are never overwritten.  Works for both per-row and summary rows.
    """
    if role == BATTER:
        _annotate_batter(s)
    else:
        _annotate_pitcher(s)


def _annotate_batter(s):
    # 打者 P/PA = 看球數 / PA；API 值（seasonAdvanced hitting 的
    # pitchesPerPlateAppearance）缺值時才補算
    if s.get("pitches_per_pa") is None:
        _fill(s, "pitches_per_pa", compute_p_per_pa(s.get("pitches"), s.get("pa")))

    # XBH fallback from components
    if s.get("xbh") is None:
        _fill(s, "xbh", compute_xbh(s.get("doubles"), s.get("triples"), s.get("hr")))

    if s.get("iso") is None:
        _fill(s, "iso", compute_iso(s.get("tb"), s.get("hits"), s.get("ab")))

    if s.get("babip") is None:
        _fill(s, "babip", compute_babip(
            s.get("hits"), s.get("hr"), s.get("ab"), s.get("so"),
            s.get("sac_flies") or 0,
        ))

    if s.get("ab_per_hr") is None:
        _fill(s, "ab_per_hr", compute_ab_per_hr(s.get("ab"), s.get("hr")))

    if s.get("go_ao") is None:
        _fill(s, "go_ao", compute_go_ao(s.get("ground_outs"), s.get("air_outs")))

    if s.get("sb_pct") is None:
        _fill(s, "sb_pct", compute_sb_pct(s.get("sb"), s.get("cs")))

    # Batter K% / BB% use PA as denominator
    if s.get("k_pct") is None:
        _fill(s, "k_pct", compute_k_pct(s.get("so"), s.get("pa")))

    if s.get("bb_pct") is None:
        _fill(s, "bb_pct", compute_bb_pct(s.get("bb"), s.get("pa")))


def _annotate_pitcher(s):
    # ── outs 是所有投手率的分母（見 core/innings.py 為何不用浮點局數） ──
    outs = ip_to_outs(s["ip"]) if s.get("ip") is not None else s.get("outs")

    # 投手 P/PA = 用球數 / BF（面對打者數）
    if s.get("pitches_per_pa") is None:
        _fill(s, "pitches_per_pa", compute_p_per_pa(s.get("pitches"), s.get("bf")))

    # /9 rate stats require IP
    if outs and outs > 0:
        if s.get("k_per_9") is None:
            _fill(s, "k_per_9", compute_k_per_9(s.get("so"), outs))
        if s.get("bb_per_9") is None:
            _fill(s, "bb_per_9", compute_bb_per_9(s.get("bb"), outs))
        if s.get("h_per_9") is None:
            _fill(s, "h_per_9", compute_h_per_9(s.get("hits"), outs))
        if s.get("hr_per_9") is None:
            _fill(s, "hr_per_9", compute_hr_per_9(s.get("hr"), outs))
        if s.get("p_per_ip") is None:
            _fill(s, "p_per_ip", compute_p_per_ip(s.get("pitches"), outs))
        if s.get("rs_per_9") is None:
            _fill(s, "rs_per_9", compute_rs_per_9(s.get("run_support"), outs))

    if s.get("k_bb_ratio") is None:
        _fill(s, "k_bb_ratio", compute_k_bb_ratio(s.get("so"), s.get("bb")))

    # Pitcher K% / BB% use BF as denominator (FanGraphs: SO / TBF, BB / TBF)
    if s.get("k_pct") is None:
        _fill(s, "k_pct", compute_k_pct(s.get("so"), s.get("bf")))

    if s.get("bb_pct") is None:
        _fill(s, "bb_pct", compute_bb_pct(s.get("bb"), s.get("bf")))

    if s.get("strike_pct") is None:
        _fill(s, "strike_pct", compute_strike_pct(s.get("strikes"), s.get("pitches")))

    # Pitcher BABIP = (H - HR) / (AB - SO - HR + SF),與打者版公式相同。
    # 用 ab(對方打數)而不是 bf(面對打者數)當分母基準:
    # AB 依官方規則定義本來就已經排除 BB/HBP/SH,只需再加回 SF;
    # 用 BF(≈PA)當基準卻只扣掉 BB 會漏扣 HBP 和 SH(犧牲短打),
    # 導致分母灌水、BABIP 被系統性低估。
    if s.get("babip") is None:
        _fill(s, "babip", compute_babip(
            s.get("hits"), s.get("hr"), s.get("ab"), s.get("so"),
            s.get("sac_flies") or 0,
        ))

    if s.get("go_ao") is None:
        _fill(s, "go_ao", compute_go_ao(s.get("ground_outs"), s.get("air_outs")))

    if s.get("win_pct") is None:
        _fill(s, "win_pct", compute_win_pct(s.get("wins"), s.get("losses")))

    # Pitcher batting line (opponents): avg / obp / slg / ops
    annotate_opponent_slash(s)


def annotate_computed_stats(all_stats, role: str):
    """Add ``role``'s derived fields to each stat row (np alias + all advanced stats)."""
    for stat in all_stats:
        stat.np = stat.pitches
        annotate_row(stat, role)
    return all_stats

"""Fill derived advanced stats onto season-stat rows.

Formulas live in the per-stat modules under ``stats/batting`` and
``stats/pitching``; this module only decides *when* a value is filled.  A
field is only ever set when its current value is None, so API-supplied values
are never overwritten.
"""

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


def annotate_row(s):
    """Fill in derived advanced stats on an Obj (or any dict-like).

    Only sets a field when its current value is None so that API-supplied
    values are never overwritten.  Works for both per-row and summary rows,
    and for both batters and pitchers (all fields guarded by None-checks).
    """
    # ── IP as real fractional innings (needed for pitcher /9 rates) ──
    ip_actual = None
    if s.get("ip") is not None:
        ip_actual = ip_to_outs(s["ip"]) / 3.0
    elif s.get("outs"):
        ip_actual = s["outs"] / 3.0

    # ─────────────────────────── BATTER fields ───────────────────────────

    # P/PA: prefer pitches_per_pa alias, then compute from pitches_seen / PA
    if s.get("p_per_pa") is None and s.get("pitches_per_pa") is not None:
        s["p_per_pa"] = s.get("pitches_per_pa")
    if s.get("p_per_pa") is None:
        _fill(s, "p_per_pa", compute_p_per_pa(s.get("pitches_seen"), s.get("pa")))

    # XBH fallback from components
    if s.get("xbh") is None:
        _fill(s, "xbh", compute_xbh(s.get("doubles"), s.get("triples"), s.get("hr")))

    if s.get("iso") is None:
        _fill(s, "iso", compute_iso(s.get("slg"), s.get("avg")))

    if s.get("babip") is None:
        _fill(s, "babip", compute_babip(
            s.get("hits"), s.get("hr"), s.get("ab"), s.get("h_so"),
            s.get("sac_flies") or 0,
        ))

    if s.get("ab_per_hr") is None:
        _fill(s, "ab_per_hr", compute_ab_per_hr(s.get("ab"), s.get("hr")))

    # Batter GO/AO
    if s.get("go_ao") is None:
        _fill(s, "go_ao", compute_go_ao(s.get("h_ground_outs"), s.get("h_air_outs")))

    if s.get("sb_pct") is None:
        _fill(s, "sb_pct", compute_sb_pct(s.get("sb"), s.get("cs")))

    # Batter K% / BB% use PA as denominator
    if s.get("k_pct") is None:
        _fill(s, "k_pct", compute_k_pct(s.get("h_so"), s.get("pa")))

    if s.get("bb_pct") is None:
        _fill(s, "bb_pct", compute_bb_pct(s.get("hit_bb"), s.get("pa")))

    # ─────────────────────────── PITCHER fields ──────────────────────────

    # Pitcher P/PA alias: pitches_per_pa = pitches / BF
    if s.get("pitches_per_pa") is None:
        _fill(s, "pitches_per_pa", compute_p_per_pa(s.get("pitches"), s.get("bf")))

    # /9 rate stats require IP
    if ip_actual and ip_actual > 0:
        if s.get("k_per_9") is None:
            _fill(s, "k_per_9", compute_k_per_9(s.get("so"), ip_actual))
        if s.get("bb_per_9") is None:
            _fill(s, "bb_per_9", compute_bb_per_9(s.get("bb"), ip_actual))
        if s.get("h_per_9") is None:
            _fill(s, "h_per_9", compute_h_per_9(s.get("p_hits"), ip_actual))
        if s.get("hr_per_9") is None:
            _fill(s, "hr_per_9", compute_hr_per_9(s.get("p_hr"), ip_actual))
        if s.get("p_per_ip") is None:
            _fill(s, "p_per_ip", compute_p_per_ip(s.get("pitches"), ip_actual))
        if s.get("rs_per_9") is None:
            _fill(s, "rs_per_9", compute_rs_per_9(s.get("run_support"), ip_actual))

    if s.get("k_bb_ratio") is None:
        _fill(s, "k_bb_ratio", compute_k_bb_ratio(s.get("so"), s.get("bb")))

    # Pitcher K% / BB% use BF as denominator
    if s.get("k_pct") is None:
        _fill(s, "k_pct", compute_k_pct(s.get("so"), s.get("bf")))

    if s.get("bb_pct") is None:
        _fill(s, "bb_pct", compute_bb_pct(s.get("bb"), s.get("bf")))

    if s.get("strike_pct") is None:
        _fill(s, "strike_pct", compute_strike_pct(s.get("strikes"), s.get("pitches")))

    # Pitcher BABIP = (H - HR) / (AB - SO - HR + SF),與打者版公式對稱。
    # 這裡用 p_ab(對方打數)而不是 bf(面對打者數)當分母基準:
    # AB 依官方規則定義本來就已經排除 BB/HBP/SH,只需再加回 SF;
    # 舊版用 BF(≈PA)當基準卻只扣掉 BB,漏扣 HBP 和 SH(犧牲短打),
    # 導致分母灌水、BABIP 被系統性低估。
    if s.get("p_babip") is None:
        _fill(s, "p_babip", compute_babip(
            s.get("p_hits"), s.get("p_hr"), s.get("p_ab"), s.get("so"),
            s.get("p_sac_flies") or 0,
        ))

    # Pitcher GO/AO
    if s.get("p_go_ao") is None:
        _fill(s, "p_go_ao", compute_go_ao(s.get("p_ground_outs"), s.get("p_air_outs")))

    if s.get("win_pct") is None:
        _fill(s, "win_pct", compute_win_pct(s.get("wins"), s.get("losses")))

    # Pitcher batting line (opponents): p_avg, p_obp, p_slg, p_ops
    annotate_opponent_slash(s)


def annotate_computed_stats(all_stats):
    """Add derived fields to each stat row (np alias + all advanced stats)."""
    for stat in all_stats:
        stat.np = stat.pitches
        annotate_row(stat)
    return all_stats

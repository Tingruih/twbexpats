"""Opponent slash line — avg / obp / slg / ops on a pitcher-projected row (what
batters hit against this pitcher)，三位小數 float（顯示格式由 render 的 floatformat 決定）。

列必須已投影到投手（``positions.project_role``）：此時 ``ab`` / ``hits`` / ``bb`` 等
概念名是被打數、被安打、投球保送，公式與打者相同。

Kept as one module because the four values share intermediates: OPS is the
sum of the *rounded* OBP and SLG computed here (MLB API convention, see
``batting/ops.py``), so it must reuse exactly the values written to obp / slg.
"""

from ...util.numbers import safe_float
from ..batting.avg import compute_avg
from ..batting.obp import compute_obp
from ..batting.ops import compute_ops
from ..batting.slg import compute_slg


def _set_if_real(s, field, value):
    # 計算結果為 None（分母為零）時不寫入，保持欄位缺值
    if value is not None:
        s[field] = value


def annotate_opponent_slash(s) -> None:
    """Fill avg/obp/slg/ops on a pitcher-projected stat row, only where currently None."""
    ab = s.get("ab")
    # 沒有被打數（沒投球或舊資料缺欄），四項都無從計算
    if not ab or ab <= 0:
        return
    hits = s.get("hits")
    tb   = s.get("tb")
    bb   = s.get("bb")
    hbp  = s.get("hbp")
    sf   = s.get("sac_flies") or 0

    if s.get("avg") is None and hits is not None:
        _set_if_real(s, "avg", compute_avg(hits, ab))

    # Only compute OBP when hits/bb/hbp are all known — unlike compute_obp's
    # default of treating missing components as 0, a silently-incomplete
    # opponent OBP would understate the true value.
    obp_f = None
    if hits is not None and bb is not None and hbp is not None:
        obp_f = compute_obp(hits, bb, hbp, ab, sf)
    if s.get("obp") is None and obp_f is not None:
        s["obp"] = obp_f

    slg_f = None
    if tb is not None:
        slg_f = compute_slg(tb, ab)
    if s.get("slg") is None and slg_f is not None:
        s["slg"] = slg_f

    if s.get("ops") is None:
        # 優先用本次算出的捨入值，否則用既有值（API 給的也是捨入值；
        # 舊 DB 列可能仍是字串，safe_float 兩者皆可解析）
        obp_v = obp_f if obp_f is not None else safe_float(s.get("obp"))
        slg_v = slg_f if slg_f is not None else safe_float(s.get("slg"))
        if obp_v is not None and slg_v is not None:
            _set_if_real(s, "ops", compute_ops(obp_v, slg_v))

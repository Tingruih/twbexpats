"""Statcast by role — 依角色派送逐球 Statcast 聚合: compute_statcast(role, pitches).

sync（單一層級列，寫進 DB）與 render（跨層級合計列，build 時現算）共用這個入口，
兩邊才保證用同一個聚合函式、同一套欄位口徑。
"""

from ..positions import BATTER, PITCHER
from .batter_statcast import compute_batter_statcast
from .pitcher_statcast import compute_pitcher_statcast

_BY_ROLE = {BATTER: compute_batter_statcast, PITCHER: compute_pitcher_statcast}


def compute_statcast(role: str, pitches: list) -> dict:
    """``role``（``positions.BATTER`` / ``PITCHER``）的 Statcast 聚合；未知角色直接 KeyError。"""
    return _BY_ROLE[role](pitches)

"""
Single source of truth for position → role mapping.

`position` 為 /api/v1/people 的 `primaryPosition.abbreviation`（存於
`players.position`）。比照 ``site_builder.levels`` / ``site_builder.roster``：
其他模組不得自行比對 position 字串（如 ``position == "P"``），一律 import 本模組。
"""

from typing import Optional

# 角色值；同時是 sync/extract.py::extract_pitch_logs() 的 role 參數
PITCHER = "pitcher"
BATTER = "batter"

# primaryPosition.abbreviation 中代表投手的值
PITCHER_POSITIONS = frozenset({"P"})


def primary_role(position: Optional[str]) -> str:
    """球員的主要角色：``PITCHER`` 或 ``BATTER``。"""
    # 空字串（players 表還沒有該球員）或其他守位一律視為打者
    return PITCHER if position in PITCHER_POSITIONS else BATTER


def is_pitcher_position(position: Optional[str]) -> bool:
    """``position`` 的主要角色是否為投手。"""
    return primary_role(position) == PITCHER

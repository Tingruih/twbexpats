"""
Single source of truth for position → role mapping and role-split field names.

`position` 為 /api/v1/people 的 `primaryPosition.abbreviation`（存於
`players.position`）。比照 ``site_builder.levels`` / ``site_builder.roster``：
其他模組不得自行比對 position 字串（如 ``position == "P"``）、stat group 名稱
（``"hitting"`` / ``"pitching"``）或自行拼 ``p_`` 前綴，一律 import 本模組。
"""

from typing import Optional

# 角色值；同時是 game_logs.role 的值與 sync/extract.py::extract_pitch_logs() 的 role 參數
PITCHER = "pitcher"
BATTER = "batter"

# primaryPosition.abbreviation 中代表投手的值
PITCHER_POSITIONS = frozenset({"P"})

# 兩個角色；逐角色處理（逐球聚合、sabermetrics group）時的固定順序
ROLES = (BATTER, PITCHER)

# /people/{id}/stats 回傳的 stats[].group.displayName → 角色
_STAT_GROUP_ROLES = {"hitting": BATTER, "pitching": PITCHER}

# season_stats.stat_json 中打擊與投球共用名稱、必須依角色拆開的 key。
# 慣例沿用既有 p_hr / p_babip：打擊不加前綴，投球加 p_（見 role_field）。
ROLE_SPLIT_FIELDS = ("gp", "statcast", "expected", "saber", "war")


def primary_role(position: Optional[str]) -> str:
    """球員的主要角色：``PITCHER`` 或 ``BATTER``。"""
    # 空字串（players 表還沒有該球員）或其他守位一律視為打者
    return PITCHER if position in PITCHER_POSITIONS else BATTER


def is_pitcher_position(position: Optional[str]) -> bool:
    """``position`` 的主要角色是否為投手。"""
    return primary_role(position) == PITCHER


def role_for_stat_group(group_name: Optional[str]) -> Optional[str]:
    """stat group 名稱（``stats[].group.displayName``，不分大小寫）對應的角色。"""
    # fielding 等不屬於打擊/投球的 group
    return _STAT_GROUP_ROLES.get((group_name or "").lower())


def stat_group_for_role(role: str) -> str:
    """``role_for_stat_group`` 的反向：API ``group=`` 參數要帶的 stat group 名稱。"""
    return next(group for group, r in _STAT_GROUP_ROLES.items() if r == role)


def role_field(role: str, name: str) -> str:
    """``ROLE_SPLIT_FIELDS`` 在 ``stat_json`` 中的實際 key：打擊為 ``name``，投球為 ``p_<name>``。"""
    return "p_" + name if role == PITCHER else name


def project_role(row, role: str) -> None:
    """把 ``role`` 的拆分欄位投影到不帶前綴的 key 上（就地修改 ``row``）。

    只給 render 層用：樣板、合併、生涯加總都讀不帶前綴的 ``gp`` / ``war`` 等。
    投手檢視時必須無條件覆寫（``p_<name>`` 缺值就寫 None），否則只打擊、
    沒投球的列會把打擊的 ``gp`` 帶進投手頁的出賽數。
    """
    if role != PITCHER:
        return
    for name in ROLE_SPLIT_FIELDS:
        row[name] = row.get(role_field(PITCHER, name))

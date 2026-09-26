"""
Single source of truth for position → role mapping and role-split field names.

`position` 為 /api/v1/people 的 `primaryPosition.abbreviation`（存於
`players.position`）。比照 ``site_builder.levels`` / ``site_builder.roster``：
其他模組不得自行比對 position 字串（如 ``position == "P"``）、stat group 名稱
（``"hitting"`` / ``"pitching"`` / ``"fielding"``）或自行拼 ``p_`` 前綴，一律 import 本模組。
"""

from typing import Iterable, Optional

# 角色值；同時是 game_logs.role 的值與 sync/extract.py::extract_pitch_logs() 的 role 參數
PITCHER = "pitcher"
BATTER = "batter"

# primaryPosition.abbreviation 中代表投手的值
PITCHER_POSITIONS = frozenset({"P"})

# 兩個角色；逐角色處理（逐球聚合、sabermetrics group）時的固定順序
ROLES = (BATTER, PITCHER)

# /people/{id}/stats 回傳的 stats[].group.displayName → 角色
_STAT_GROUP_ROLES = {"hitting": BATTER, "pitching": PITCHER}
# stats[].group.displayName 中不屬於任何角色的守備 group
FIELDING_GROUP = "fielding"

# 打擊與投球都有的概念，在 season_stats.stat_json 依角色拆開存：打擊存概念名，
# 投球存 p_<概念名>（role_field）。render 投影（project_role）後樣板、合併、
# 生涯加總在兩個角色的檢視都只讀概念名。只屬於一個角色的欄位（投球 era / ip /
# bf、打擊 pa / rbi / lob）不在這裡，也不得經過 role_field。
ROLE_SPLIT_FIELDS = (
    # 出賽數與外部整包資料
    "gp", "statcast", "expected", "saber", "war",
    # yearByYear 計數（打擊為本人成績，投球為被打成績）
    "ab", "hits", "doubles", "triples", "hr", "tb", "runs", "bb", "ibb", "so",
    "hbp", "sb", "cs", "gdp", "sac_bunts", "sac_flies", "ground_outs",
    "air_outs", "pitches",
    # yearByYear 比率（投球為被打率）
    "avg", "obp", "slg", "ops", "babip", "go_ao", "sb_pct",
    # seasonAdvanced
    "gidpo", "pitches_per_pa",
    # render 階段自算（stats/core/annotate.py），分母依角色為 PA 或 BF
    "k_pct", "bb_pct",
)
_ROLE_SPLIT_SET = frozenset(ROLE_SPLIT_FIELDS)


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


def _stats_entry_group(entry: Optional[dict]) -> str:
    """``stats[]`` 其中一筆的 ``group.displayName``（小寫）。"""
    # 缺 group 欄位時為空字串，role_of_stats_entry / is_fielding_entry 都判為不符
    return ((entry or {}).get("group") or {}).get("displayName", "").lower()


def role_of_stats_entry(entry: Optional[dict]) -> Optional[str]:
    """``/people/{id}/stats`` 回應 ``stats[]`` 其中一筆的角色（讀 ``group.displayName``）。"""
    # fielding 或缺 group 的項目不屬於任何角色
    return role_for_stat_group(_stats_entry_group(entry))


def is_fielding_entry(entry: Optional[dict]) -> bool:
    """``stats[]`` 其中一筆是否為守備 group。"""
    return _stats_entry_group(entry) == FIELDING_GROUP


def stat_groups_param(roles: Iterable[str] = ROLES, *, fielding: bool = False) -> str:
    """API ``group=`` 參數值，依 ``roles`` 的順序，例如 ``"hitting,pitching"``。"""
    groups = [stat_group_for_role(role) for role in roles]
    if fielding:
        groups.append(FIELDING_GROUP)
    return ",".join(groups)


def role_field(role: str, name: str) -> str:
    """``ROLE_SPLIT_FIELDS`` 在 ``stat_json`` 中的實際 key：打擊為 ``name``，投球為 ``p_<name>``。

    ``name`` 必須已登記在 ``ROLE_SPLIT_FIELDS``：未登記的名字不會被 ``project_role``
    投影，默默拼出前綴只會產生一個樣板讀不到的 key。
    """
    if name not in _ROLE_SPLIT_SET:
        raise ValueError(f"{name!r} is not in ROLE_SPLIT_FIELDS")
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

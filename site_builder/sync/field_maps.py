"""MLB Stats API stat-field → local column-name mappings.

兩個 stat group 同名的 API 欄位只登記一次（``_YEARBYYEAR_SHARED`` /
``_ADVANCED_SHARED``），寫入時由 ``positions.role_field`` 決定 key：打擊存概念名、
投球存 ``p_<概念名>``。只屬於一個角色的欄位各自一張表，key 不加前綴。

比率欄位一律存 float：API 以字串給值，分母為零時給 ".---" / "-.--"、
舊 MiLB 資料可能整欄缺，safe_float 全部收斂成 None，annotate_row 的 is None
檢查才能補算；顯示格式由 render 的 floatformat 決定。
"""

from ..positions import BATTER, PITCHER, role_field
from ..util.numbers import safe_float, safe_int

# (API 欄位, 概念名, 轉型)；概念名必須登記在 positions.ROLE_SPLIT_FIELDS
_YEARBYYEAR_SHARED = (
    ("atBats", "ab", safe_int),
    ("hits", "hits", safe_int),
    ("doubles", "doubles", safe_int),
    ("triples", "triples", safe_int),
    ("homeRuns", "hr", safe_int),
    ("totalBases", "tb", safe_int),
    ("runs", "runs", safe_int),
    ("baseOnBalls", "bb", safe_int),
    ("intentionalWalks", "ibb", safe_int),
    ("strikeOuts", "so", safe_int),
    ("hitByPitch", "hbp", safe_int),
    ("stolenBases", "sb", safe_int),
    ("caughtStealing", "cs", safe_int),
    ("groundIntoDoublePlay", "gdp", safe_int),
    ("sacBunts", "sac_bunts", safe_int),
    ("sacFlies", "sac_flies", safe_int),
    ("groundOuts", "ground_outs", safe_int),
    ("airOuts", "air_outs", safe_int),
    ("numberOfPitches", "pitches", safe_int),
    ("avg", "avg", safe_float),
    ("obp", "obp", safe_float),
    ("slg", "slg", safe_float),
    ("ops", "ops", safe_float),
    ("babip", "babip", safe_float),
    ("groundOutsToAirouts", "go_ao", safe_float),
    ("stolenBasePercentage", "sb_pct", safe_float),
)

_YEARBYYEAR_ONLY = {
    BATTER: (
        ("plateAppearances", "pa", safe_int),
        ("rbi", "rbi", safe_int),
        ("leftOnBase", "lob", safe_int),
        ("catchersInterference", "ci", safe_int),
        ("caughtStealingPercentage", "cs_pct", safe_float),
        ("atBatsPerHomeRun", "ab_per_hr", safe_float),
    ),
    PITCHER: (
        ("era", "era", safe_float),
        ("whip", "whip", safe_float),
        ("inningsPitched", "ip", safe_float),
        ("wins", "wins", safe_int),
        ("losses", "losses", safe_int),
        ("saves", "sv", safe_int),
        ("holds", "hld", safe_int),
        ("gamesStarted", "gs", safe_int),
        ("earnedRuns", "earned_runs", safe_int),
        ("battersFaced", "bf", safe_int),
        ("strikeoutsPer9Inn", "k_per_9", safe_float),
        ("walksPer9Inn", "bb_per_9", safe_float),
        ("hitsPer9Inn", "h_per_9", safe_float),
        ("strikeoutWalkRatio", "k_bb_ratio", safe_float),
        ("homeRunsPer9", "hr_per_9", safe_float),
        ("pitchesPerInning", "p_per_ip", safe_float),
        ("winPercentage", "win_pct", safe_float),
        ("strikePercentage", "strike_pct", safe_float),
        ("saveOpportunities", "svo", safe_int),
        ("outs", "outs", safe_int),
        ("completeGames", "cg", safe_int),
        ("shutouts", "sho", safe_int),
        ("strikes", "strikes", safe_int),
        ("balks", "balks", safe_int),
        ("wildPitches", "wp", safe_int),
        ("pickoffs", "pickoffs", safe_int),
        ("gamesFinished", "gf", safe_int),
        ("inheritedRunners", "ir", safe_int),
        ("inheritedRunnersScored", "irs", safe_int),
        ("qualityStarts", "qs", safe_int),
    ),
}

# pitchesPerPlateAppearance 兩個 group 同名：打擊是看球數 / PA，投球是用球數 / BF，
# 與 k_pct 等一樣依角色分存，投影後同一個概念名在各自檢視代表各自的分母
_ADVANCED_SHARED = (
    ("gidpOpp", "gidpo", safe_int),
    ("babip", "babip", safe_float),
    ("pitchesPerPlateAppearance", "pitches_per_pa", safe_float),
)

_ADVANCED_ONLY = {
    BATTER: (
        ("reachedOnError", "roe", safe_int),
        ("walkOffs", "wo", safe_int),
        ("extraBaseHits", "xbh", safe_int),
    ),
    PITCHER: (
        ("qualityStarts", "qs", safe_int),
        ("bequeathedRunners", "bqr", safe_int),
        ("bequeathedRunnersScored", "bqr_s", safe_int),
        ("runSupport", "run_support", safe_int),
        ("runsScoredPer9", "rs_per_9", safe_float),
    ),
}


def apply_yearbyyear_fields(stat_doc: dict, role: str, stat: dict):
    """yearByYear 一個角色的 ``stat`` 寫入 ``stat_doc``；缺值也寫 None（整組覆寫）。"""
    for api_key, name, cast in _YEARBYYEAR_SHARED:
        stat_doc[role_field(role, name)] = cast(stat.get(api_key))
    for api_key, key, cast in _YEARBYYEAR_ONLY[role]:
        stat_doc[key] = cast(stat.get(api_key))


def apply_advanced_fields(stat_doc: dict, role: str, stat: dict):
    """seasonAdvanced 一個角色的 ``stat`` 補進 ``stat_doc``；缺值不寫，保留 yearByYear 的值。"""
    fields = [(api_key, role_field(role, name), cast)
              for api_key, name, cast in _ADVANCED_SHARED]
    fields += _ADVANCED_ONLY[role]
    for api_key, key, cast in fields:
        val = cast(stat.get(api_key))
        if val is not None:
            stat_doc[key] = val

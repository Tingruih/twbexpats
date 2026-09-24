"""Season trend chart (player-detail「圖表」分頁) payload builders.

與 movement.py / plinko.py 同樣的檔案定位——一個圖表一個檔案。跟兩者不同的是
這裡的資料是「逐場」而非「球季+層級」彙整，且直接在 build time 從已快取的
game_logs 現算（pitches_json 已經在 sync 階段抓好，逐場再彙整一次的成本很低），
所以不走 compute_*（sync 時算好存進 season_stats）那條路，是單一 build-time 入口。

每一點都是「季初至該場」的累積值，組成方式分三層：

  - 每場的原料 ``_Totals.of_game``：box score 計數、該場的 ``aggregate_pitches``
    與打席小計。每場只彙整自己的球，單一層級序列與 All Levels 序列共用。
  - 總帳 ``_Totals.add``：逐場合併原料，數字相加、清單串接。
  - 公式表 ``TrendMetric``：每個指標直接呼叫 stats/ 的 compute_*，拿總帳當輸入。

這裡刻意不寫任何數據公式。逐球分類與其他球無關，所以「每場各自彙整再合併」
與「整季的球一次彙整」得到同一份資料，交給同一個 compute_* 就會得到與球季值
相同的結果；stats/ 改了定義，走勢圖自動跟著改。

MLB Stats API gameLog 的 AVG/ERA 等是逐層級累積值，球員升降層級時會歸零；
這裡自己從計數累積，All Levels 序列跨層級才會連續。
"""

from dataclasses import dataclass
from typing import Callable, Optional

from ..levels import ALL_LEVELS, level_display, level_label, level_rank
from ..stats.advanced.woba import compute_pitch_woba
from ..stats.batted_ball.barrel import compute_barrel_pct
from ..stats.batted_ball.exit_velocity import compute_avg_ev
from ..stats.batted_ball.hard_hit import compute_hard_hit_pct
from ..stats.batted_ball.launch_angle import collect_la_values
from ..stats.batted_ball.sweet_spot import compute_sweet_spot_pct
from ..stats.batting.avg import compute_avg
from ..stats.batting.bb_pct import compute_bb_pct
from ..stats.batting.k_pct import compute_k_pct
from ..stats.core.pa_outcomes import compute_pa_outcome_totals
from ..stats.core.pitches import aggregate_pitches
from ..stats.discipline.csw_pct import compute_csw_pct
from ..stats.discipline.o_swing_pct import compute_o_swing_pct
from ..stats.discipline.swstr_pct import compute_swstr_pct
from ..stats.discipline.whiff_pct import compute_whiff_pct
from ..stats.discipline.z_contact_pct import compute_z_contact_pct
from ..stats.pitching.era import compute_era

# gameLog 端點每場的 stat 物件（存於 game_logs.stats_json）中逐場相加的計數欄位。
# 投手列才有 battersFaced/earnedRuns/outs、打者列才有 plateAppearances，缺的欄位記 0
_BOX_FIELDS = (
    "hits",
    "atBats",
    "strikeOuts",
    "baseOnBalls",
    "battersFaced",
    "plateAppearances",
    "earnedRuns",
    "outs",
)


def _merge(acc: dict, part: dict) -> None:
    """把 *part* 併進 *acc*：數字相加、清單串接到 *acc* 自己的清單後面。

    其他型別無法判斷該怎麼跨場合併，直接丟錯：aggregate_pitches 日後若新增
    dict 之類的欄位，要在這裡明確決定合併方式，而不是被默默算錯。
    """
    for key, value in part.items():
        if isinstance(value, list):
            acc[key].extend(value)
        elif isinstance(value, (int, float)):
            acc[key] += value
        else:
            raise TypeError(f"不知道如何逐場合併 {key!r}（{type(value).__name__}）")


@dataclass
class _Totals:
    """一場或季初至今多場的累積總帳。

    三本帳分開放：``box`` 的 "hits" 是 box score 安打，``pa`` 的 "hits" 是由
    逐球打席結果推得的安打，同名但來源不同，放在同一個 dict 會互相覆蓋。
    """

    box: dict  # _BOX_FIELDS 的計數
    agg: dict  # aggregate_pitches 的輸出
    pa: dict   # compute_pa_outcome_totals 的輸出（wOBA 分子分母）

    @classmethod
    def empty(cls) -> "_Totals":
        return cls(
            box=dict.fromkeys(_BOX_FIELDS, 0),
            agg=aggregate_pitches([]),
            pa=compute_pa_outcome_totals([]),
        )

    @classmethod
    def of_game(cls, log) -> "_Totals":
        s = log.stats_json or {}
        agg = aggregate_pitches(log.pitches_json or [])
        return cls(
            box={f: s.get(f) or 0 for f in _BOX_FIELDS},
            agg=agg,
            # 打席小計逐場算好再相加：若每場都對季初至今的全部打席重跑，成本會隨
            # 場數平方成長。代價是 woba_num 的浮點相加順序與球季值一次算完不同，
            # 最後一位可能不同，顯示只取到小數第三位
            pa=compute_pa_outcome_totals(agg["pa_final"]),
        )

    def add(self, other: "_Totals") -> None:
        # 只會併進 empty() 建出的總帳；各場 of_game 的清單不會被改動，可重複使用
        _merge(self.box, other.box)
        _merge(self.agg, other.agg)
        _merge(self.pa, other.pa)


@dataclass(frozen=True)
class TrendMetric:
    """走勢圖的一個指標：前端選單的 key/label，以及如何從總帳算出數值。

    ``compute`` 只負責把總帳的哪一部分交給 stats/ 的哪個 compute_*，不在這裡
    寫公式。需要看每一筆的指標（如平均初速）從串接後的清單整份重算，與球季值
    走同一個函式；每季最多幾百顆擊球，每場重算的成本很小。
    """

    key: str
    label: str
    compute: Callable[[_Totals], Optional[float]]


_AVG = TrendMetric("avg", "AVG", lambda t: compute_avg(t.box["hits"], t.box["atBats"]))
_WHIFF = TrendMetric("whiff_pct", "Whiff%", lambda t: compute_whiff_pct(t.agg))
_SWSTR = TrendMetric("swstr_pct", "SwStr%", lambda t: compute_swstr_pct(t.agg))
_CHASE = TrendMetric("chase_pct", "Chase%", lambda t: compute_o_swing_pct(t.agg))
_Z_CONTACT = TrendMetric("z_contact_pct", "Z-Contact%", lambda t: compute_z_contact_pct(t.agg))
_HARD_HIT = TrendMetric("hard_hit_pct", "HardHit%", lambda t: compute_hard_hit_pct(t.agg))
_BARREL = TrendMetric("barrel_pct", "Barrel%", lambda t: compute_barrel_pct(t.agg))
_EXIT_VELOCITY = TrendMetric(
    "exit_velocity", "Exit Velocity", lambda t: compute_avg_ev(t.agg["bbe_ev"])
)

# 順序即前端選單順序
PITCHER_TREND_METRICS = (
    TrendMetric("era", "ERA", lambda t: compute_era(t.box["earnedRuns"], t.box["outs"])),
    _AVG,
    TrendMetric(
        "k_pct", "K%", lambda t: compute_k_pct(t.box["strikeOuts"], t.box["battersFaced"])
    ),
    TrendMetric(
        "bb_pct", "BB%", lambda t: compute_bb_pct(t.box["baseOnBalls"], t.box["battersFaced"])
    ),
    _WHIFF,
    TrendMetric("csw_pct", "CSW%", lambda t: compute_csw_pct(t.agg)),
    _SWSTR,
    _CHASE,
    _Z_CONTACT,
    _HARD_HIT,
    _BARREL,
    _EXIT_VELOCITY,
)

BATTER_TREND_METRICS = (
    _AVG,
    TrendMetric(
        "k_pct", "K%", lambda t: compute_k_pct(t.box["strikeOuts"], t.box["plateAppearances"])
    ),
    TrendMetric(
        "bb_pct", "BB%",
        lambda t: compute_bb_pct(t.box["baseOnBalls"], t.box["plateAppearances"]),
    ),
    TrendMetric("woba", "wOBA", lambda t: compute_pitch_woba(t.pa)),
    _EXIT_VELOCITY,
    _HARD_HIT,
    _BARREL,
    TrendMetric(
        "sweet_spot_pct", "SweetSpot%",
        lambda t: compute_sweet_spot_pct(collect_la_values(t.agg["in_play"])),
    ),
    _WHIFF,
    _CHASE,
    _Z_CONTACT,
    _SWSTR,
)

PITCHER_TREND_STAT_OPTIONS = [(m.key, m.label) for m in PITCHER_TREND_METRICS]
BATTER_TREND_STAT_OPTIONS = [(m.key, m.label) for m in BATTER_TREND_METRICS]


def _cumulative_points(games: list, metrics, badge_year: Optional[int] = None) -> list:
    """依序把每場併進總帳，每場結束時對總帳算一次全部指標。

    *games* 是依日期排序的 ``(log, _Totals)``。*badge_year* 有值時（All Levels
    序列）每點附上該場的層級，讓前端標示這一點屬於哪個層級。
    """
    running = _Totals.empty()
    points = []
    for log, totals in games:
        running.add(totals)
        point = {"date": log.date.strftime("%m/%d"), "date_key": log.date.isoformat()}
        if badge_year is not None:
            point["level_label"] = level_display(log.sport_level, badge_year)
        point.update({m.key: m.compute(running) for m in metrics})
        points.append(point)
    return points


def _build_year_entry(year_logs: list, year: int, metrics) -> dict:
    """一個球季：每個層級一條序列，打過多個層級時再加一條跨層級的 All Levels 序列。

    All Levels 是把全部比賽依日期合併後用同一本總帳累積，而不是把各層級序列
    接起來（那樣每次升降層級都會歸零）。
    """
    # 先排序再分組：穩定排序下，分組後各層級內的順序與各自排序相同
    games = sorted(
        ((log, _Totals.of_game(log)) for log in year_logs), key=lambda g: g[0].date
    )

    # 以 tier key 分組；同一年每個 tier key 對應唯一的 level_display 字串，
    # 所以下面用顯示字串當 dict 鍵不會互相覆蓋
    by_level: dict = {}
    for game in games:
        by_level.setdefault(game[0].sport_level, []).append(game)

    year_entry = {}
    for tier_key in sorted(by_level, key=level_rank):
        level_key = level_display(tier_key, year)
        year_entry[level_key] = {
            "level_label": level_key,
            "games": _cumulative_points(by_level[tier_key], metrics),
        }
    if len(year_entry) > 1:
        year_entry[ALL_LEVELS] = {
            "level_label": level_label(ALL_LEVELS, year),
            "games": _cumulative_points(games, metrics, badge_year=year),
        }
    return year_entry


def _build_trend_by_year(logs_by_year: dict, metrics) -> dict:
    """year -> level_display 字串（或 ALL_LEVELS）-> {"level_label", "games": [...]}。

    只採計有日期的例行賽 game log；整季沒有可用比賽的年份不輸出。
    """
    result = {}
    for year in sorted(logs_by_year, reverse=True):
        year_logs = [
            log for log in logs_by_year[year]
            if log.date and not log.is_postseason
        ]
        if not year_logs:
            continue
        result[year] = _build_year_entry(year_logs, year, metrics)
    return result


def build_pitcher_trend_by_year(logs_by_year: dict) -> dict:
    """投手走勢圖 payload，指標見 ``PITCHER_TREND_METRICS``。"""
    return _build_trend_by_year(logs_by_year, PITCHER_TREND_METRICS)


def build_batter_trend_by_year(logs_by_year: dict) -> dict:
    """打者走勢圖 payload，指標見 ``BATTER_TREND_METRICS``。"""
    return _build_trend_by_year(logs_by_year, BATTER_TREND_METRICS)

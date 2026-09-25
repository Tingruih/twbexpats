"""season_fetches：過去球季「已成功抓過」的登記表。

規則（sabermetrics / expectedStatistics / 投手 FIP 常數共用）：
  - 當季（``constants.is_season_in_progress``）每次都重抓，也不登記：換季後
    上一季不在表裡，會以「過去球季」再抓一次，拿到季後修正過的最終值。
  - 過去球季只要成功抓過一次就登記，之後不再抓。API 成功回應但沒有資料
    （例如 2015 年以前沒有 expected stats、2005 年以前 MiLB 沒有自責分）
    也算抓過，否則會每次執行都白抓一次。
  - 抓取失敗（``FetchError``）不登記，下次執行自動重試。
  - ``force=True``（build.py 的 ``--full-history`` / ``--update-constants``）
    忽略登記，全部重抓。

``subject`` 是球員 mlb_id（轉成字串）或層級 tier key，依 ``source`` 而定。
"""

import datetime
from typing import Iterable, Optional

from ..constants import is_season_in_progress

# source 值：登記表內每種資料來源的名稱
SABERMETRICS = "sabermetrics"
# expectedStatistics 依角色分開登記：打擊（group=hitting）與投球（group=pitching）
# 是兩個請求，一個成功不代表另一個也抓過
EXPECTED_STATS = "expected"
P_EXPECTED_STATS = "p_expected"
FIP_CONSTANTS = "fip_constants"

# {(subject, year)}，由 load_fetched 產生
FetchedSet = set[tuple[str, int]]


def load_fetched(cur, source: str) -> FetchedSet:
    """``source`` 已登記的 ``{(subject, year)}``；整次執行讀一次即可。"""
    cur.execute("SELECT subject, year FROM season_fetches WHERE source = ?", (source,))
    return {(subject, year) for subject, year in cur.fetchall()}


def needs_fetch(fetched: FetchedSet, subject, year: int, *, force: bool) -> bool:
    """這個 (subject, year) 這次要不要抓（規則見模組 docstring）。"""
    return force or is_season_in_progress(year) or (str(subject), year) not in fetched


def mark_fetched(
    cur, source: str, subject, years: Iterable[int], now_iso: Optional[str] = None
) -> None:
    """登記成功抓過的年份；當季不登記（見模組 docstring）。呼叫端負責 commit。"""
    now_iso = now_iso or datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur.executemany(
        "INSERT OR REPLACE INTO season_fetches (source, subject, year, fetched_at) "
        "VALUES (?, ?, ?, ?)",
        [
            (source, str(subject), year, now_iso)
            for year in years
            if not is_season_in_progress(year)
        ],
    )

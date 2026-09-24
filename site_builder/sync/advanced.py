"""
Pipeline C：以球員-年為單位，把進階數據寫入 season_stats。

負責的欄位（``stat_json``）：
  - MLB 列：``saber``（sabermetrics 整包）、``fip`` / ``xfip`` / ``war``
    （投手）、``war`` / ``wrc_plus``（打者）、``lg_era`` / ``xwpct``（投手）
  - MiLB 投手列：``fip`` / ``lg_era`` / ``xwpct``，由計數數據加聯盟常數自算

這些值只依賴 season_stats 的計數數據、MLB sabermetrics 與聯盟常數，
和逐球資料無關，所以掃過每一列，不看該年有沒有 playByPlay。
逐球資料衍生的 ``statcast`` / ``expected`` 由 ``sync/statcast.py`` 負責。

sabermetrics 依 ``db/season_fetches.py`` 的規則抓取：當季每次重抓，過去球季
成功抓過一次後不再抓（``full_history=True`` 強制全部重抓）。沒抓的年份改用
上次存下的 ``saber`` 整包重算欄位，所以公式或 lgERA 變動仍會套用到舊球季。

sabermetrics 是整季合計（見 ``_season_total_saber``），轉隊球員同一年的
每一隊 MLB 列都寫入同一份值；``render/pages.py`` 的 ``_merge_level_rows``
以 ``_first_not_none`` 取 WAR/wRC+、以 IP 加權合併相同的 FIP，結果仍是整季值。
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from ..api import FetchError, get_player_sabermetrics
from ..constants import GAME_FETCH_WORKERS
from ..db.season_fetches import SABERMETRICS, load_fetched, mark_fetched, needs_fetch
from ..db.season_stats import save_season_row
from ..league_constant.pitching import PitchingConstants
from ..levels import MLB_KEY, is_mlb
from ..positions import is_pitcher_position
from ..stats.advanced.fip import LeagueFipConstant, compute_fip
from ..stats.advanced.xwpct import compute_xwpct
from ..util.json import loads_json_dict, loads_json_list
from ..util.log import describe_exc
from ..util.numbers import round_half_up, safe_float, safe_int

logger = logging.getLogger(__name__)

# MiLB 投手列由本模組自算的欄位；算不出來時整組移除，避免留下舊值
_MILB_FIP_FIELDS = ("fip", "lg_era", "xwpct")


def _season_total_saber(saber_groups: list, target_group: str) -> dict[int, dict]:
    """``{year: stat}``，每年只取 sabermetrics 的整季合計 split。

    ``stats[].splits[]`` 對同一年轉隊球員的回傳順序是：整季合計一筆（沒有
    ``team``、帶 ``numTeams``），接著依隊名字母順序各隊一筆（帶 ``team``）。
    若逐筆覆寫，最後留下的是字母排最後那一隊的單隊值（例：Yu Chang 2022
    存成 Rays 的 WAR 0.43 / wRC+ 99，整季實為 0.30 / 77），所以一律略過帶
    ``team`` 的 split。只待一隊的年份也只回一筆沒有 ``team`` 的整季 split；
    同年只有一筆時仍直接採用，避免 API 哪天單隊也附上 ``team`` 就整年遺失。
    """
    splits_by_year: dict[int, list[dict]] = {}
    for grp in saber_groups:
        if grp.get("group", {}).get("displayName", "").lower() != target_group:
            continue
        for sp in grp.get("splits", []):
            yr = safe_int(sp.get("season"))
            if yr:
                splits_by_year.setdefault(yr, []).append(sp)

    result: dict[int, dict] = {}
    for yr, splits in splits_by_year.items():
        if len(splits) == 1:
            result[yr] = splits[0].get("stat", {})
            continue
        totals = [sp for sp in splits if "team" not in sp]
        # 多筆卻找不到整季列：寧可不寫，也不要把單隊值當整季值存進去
        if totals:
            result[yr] = totals[0].get("stat", {})
    return result


def _fetch_season_saber(mlb_id: int, year: int, is_pitcher: bool) -> dict:
    """平行 worker：抓一年的 ``/people/{id}/stats?stats=sabermetrics&season={year}``。

    回該年整季 stat；API 成功回應但該年沒有資料時回 ``{}``。
    一次一年而不用 ``seasons=a,b``：多年查詢對轉隊年份不回整季合計 split
    （Yu Chang 2022 實測只回各隊 split），``_season_total_saber`` 會整年略過。
    """
    target_group = "pitching" if is_pitcher else "hitting"
    return _season_total_saber(
        get_player_sabermetrics(mlb_id, years=[year]), target_group
    ).get(year, {})


def _level_wide_lg_era(constants: dict[str, LeagueFipConstant]) -> Optional[float]:
    """xWPCT 一律以整層 lgERA 為分母（對比的是整個層級的平均，不是其中一個聯盟）。"""
    level_wide = constants.get("")
    # 該層級沒有可用常數（例如 2005 年以前的 MiLB）
    return level_wide.lg_era if level_wide else None


def _mlb_advanced_fields(
    saber: dict, is_pitcher: bool, lg_era: Optional[float]
) -> dict:
    """由整季 sabermetrics 取出要寫進 MLB 列的欄位。

    投手 FIP 直接用 API 的值，但 xWPCT 的分母仍是我們自算的整層 lgERA；
    FIP 缺值時整組不寫，保留既有值（與 API 呼叫失敗時的處理一致）。
    """
    fields: dict = {"saber": saber}
    if is_pitcher:
        fip = safe_float(saber.get("fip"))
        if fip is not None:
            fields.update(
                # 存 API 原值（五位小數），顯示時才捨入；同層級轉隊合併要用未捨入值加權
                fip=fip,
                xfip=safe_float(saber.get("xfip")),
                war=safe_float(saber.get("war")),
                lg_era=lg_era,
                xwpct=compute_xwpct(fip, lg_era),
            )
    else:
        fields["war"] = safe_float(saber.get("war"))
        # API 回傳小數（76.727），FanGraphs 顯示四捨五入的整數（77）；
        # 直接轉 int 會無條件捨去成 76，內建 round() 遇 .5 又會取偶數
        wrc_plus = safe_float(saber.get("wRcPlus"))
        if wrc_plus is not None:
            fields["wrc_plus"] = int(round_half_up(wrc_plus, 0))
    return fields


def _milb_fip_fields(
    stat_doc: dict, league_name: str, constants: dict[str, LeagueFipConstant]
) -> Optional[dict]:
    """MiLB 投手列的 FIP / lgERA / xWPCT；算不出來時回 None。

    FIP 常數優先用球員所屬聯盟，沒有才退整層；xWPCT 一律用整層 lgERA。
    """
    level_wide = constants.get("")
    own_league = constants.get(league_name) or level_wide
    fip = compute_fip(
        hr=stat_doc.get("p_hr"),
        bb=stat_doc.get("bb"),
        hbp=stat_doc.get("p_hbp"),
        k=stat_doc.get("so"),
        ip=safe_float(stat_doc.get("ip")),
        c_fip=own_league.fip_constant if own_league else None,
    )
    # 沒有投球局數，或該層級/年份沒有可用常數
    if fip is None:
        return None
    lg_era = _level_wide_lg_era(constants)
    # 存未捨入值（模板以 floatformat(2) 顯示）：xWPCT 與同層級轉隊的 IP 加權合併
    # （render/pages.py _merge_level_rows）都要用未捨入的 FIP，避免誤差傳下去
    return {"fip": fip, "lg_era": lg_era, "xwpct": compute_xwpct(fip, lg_era)}


def _load_rows(cur, roster_ids: list[int]) -> list[tuple]:
    """名冊球員的所有 season_stats 列：``(mlb_id, year, team, league, level, stat_json, fielding_json)``。"""
    placeholders = ",".join("?" * len(roster_ids))
    cur.execute(
        "SELECT player_mlb_id, year, team_name, league_name, sport_level, "
        "stat_json, fielding_json FROM season_stats "
        f"WHERE player_mlb_id IN ({placeholders})",
        roster_ids,
    )
    return cur.fetchall()


def _fetch_all_saber(
    tasks: list[tuple[int, int]], positions: dict[int, str]
) -> dict[tuple[int, int], dict]:
    """平行抓每個 (球員, 年) 的整季 sabermetrics，回 ``{(mlb_id, year): stat}``。

    以「球員-年」為平行單位：這個端點一次約 1 秒，偶爾逾時 15 秒，
    以球員為單位時，MLB 年份多的球員會一年接一年排隊，拖長整段時間。
    抓取失敗的 (球員, 年) 不會出現在結果中。
    """
    saber: dict[tuple[int, int], dict] = {}
    with ThreadPoolExecutor(max_workers=GAME_FETCH_WORKERS) as executor:
        future_to_task = {
            executor.submit(
                _fetch_season_saber, mlb_id, year, is_pitcher_position(positions.get(mlb_id))
            ): (mlb_id, year)
            for mlb_id, year in tasks
        }
        for future in as_completed(future_to_task):
            mlb_id, year = future_to_task[future]
            # 抓不到就不寫也不登記，MLB 列改用上次存下的 saber，下次執行重試
            try:
                saber[(mlb_id, year)] = future.result()
            except FetchError as e:
                logger.warning(
                    "sabermetrics fetch failed for %s year=%s: %s",
                    mlb_id, year, describe_exc(e),
                )
            except Exception:
                logger.exception("sabermetrics parse failed for %s year=%s", mlb_id, year)
    return saber


def sync_season_advanced(
    conn,
    roster_ids: list[int],
    positions: dict[int, str],
    constants: PitchingConstants,
    *,
    full_history: bool = False,
) -> None:
    """對名冊球員的每一列 season_stats 寫入進階數據（欄位見模組 docstring）。

    ``constants`` 整次執行共用記憶體快取，需要的 (level, year) 會先一次平行抓完。
    MLB 列在 sabermetrics 沒抓（已登記的過去球季）或抓不到時，以既有的
    ``saber`` 重算；連 ``saber`` 都沒有就保留既有值。MiLB 投手列則是由計數
    數據決定的結果，算不出來就移除舊值（例如先前用錯誤常數算出的 FIP）。
    """
    if not roster_ids:
        return
    cur = conn.cursor()
    rows = _load_rows(cur, roster_ids)

    fetched = load_fetched(cur, SABERMETRICS)
    tasks = sorted({
        (mlb_id, year)
        for mlb_id, year, _, _, level, _, _ in rows
        if is_mlb(level) and needs_fetch(fetched, mlb_id, year, force=full_history)
    })
    logger.info("Advanced: fetching sabermetrics for %d MLB player-season(s) ...", len(tasks))
    fresh_saber = _fetch_all_saber(tasks, positions)
    for mlb_id, year in fresh_saber:
        mark_fetched(cur, SABERMETRICS, mlb_id, [year])

    constants.prefetch({
        (MLB_KEY if is_mlb(level) else level, year)
        for mlb_id, year, _, _, level, _, _ in rows
        if level and is_pitcher_position(positions.get(mlb_id))
    })

    updated = 0
    for mlb_id, year, team_name, league_name, level, stat_json, fielding_json in rows:
        is_pitcher = is_pitcher_position(positions.get(mlb_id))
        stat_doc = loads_json_dict(stat_json)
        if is_mlb(level):
            saber = fresh_saber.get((mlb_id, year)) or stat_doc.get("saber")
            # 從未抓到過 sabermetrics（API 失敗或無資料）：保留既有值
            if not saber:
                continue
            lg_era = _level_wide_lg_era(constants.for_level(MLB_KEY, year)) if is_pitcher else None
            stat_doc.update(_mlb_advanced_fields(saber, is_pitcher, lg_era))
        elif is_pitcher and level:
            fields = _milb_fip_fields(
                stat_doc, league_name, constants.for_level(level, year)
            )
            if fields:
                stat_doc.update(fields)
            else:
                for key in _MILB_FIP_FIELDS:
                    stat_doc.pop(key, None)
        else:
            continue
        save_season_row(
            cur, mlb_id, year, team_name, league_name, level,
            stat_doc, loads_json_list(fielding_json),
        )
        updated += 1
    conn.commit()
    logger.info("  wrote advanced stats to %d season row(s)", updated)

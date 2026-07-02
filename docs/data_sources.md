# 資料來源總覽：投手 / 打者所有數據欄位

本文件整理 Taiwan MLB Tracker 目前呈現的**每一個數據欄位**，並標明：

- 🔵 **API**：直接取自 MLB Stats API，程式只做欄位改名／型別轉換，沒有數學運算
- 🟢 **計算**：由程式用公式計算或彙總出來的衍生欄位
- 來源端點 / 定義位置（檔案:行號）

> 對應程式碼：`site_builder/api.py`（API 呼叫）、`site_builder/sync.py`（欄位對應寫入 DB）、
> `site_builder/helpers.py`（單場/彙總計算）、`site_builder/statcast.py`（逐球 Statcast 計算）、
> `site_builder/wrc_plus.py`（wOBA / wRC+）。

---

## 目錄

1. [球員基本資料](#一球員基本資料)
2. [投手數據](#二投手數據)
3. [打者數據](#三打者數據)
4. [守備數據（打者／投手共用）](#四守備數據打者投手共用)
5. [逐場紀錄（Game Log）](#五逐場紀錄game-log)
6. [生涯／賽季彙總邏輯](#六生涯賽季彙總邏輯)
7. [跨層級 Statcast 合併邏輯](#七跨層級-statcast-合併邏輯)
8. [總結：API vs 計算 比例](#八總結api-vs-計算-比例)

---

## 一、球員基本資料

**端點**：`GET /people/{mlb_id}?hydrate=transactions,rosterEntries,currentTeam`（`api.py get_player_profile()` 第20–121行）

| 欄位 | 分類 | 說明 |
|---|---|---|
| `mlb_id`, `full_name`, `position`, `height`, `weight`, `birth_date`, `birth_city`, `birth_country`, `is_active`, `bat_side`, `pitch_hand` | 🔵 API | 原封取自 `people[0]` |
| `latest_transaction`, `transactions_json` | 🔵 API | 取 `transactions` 陣列，僅按日期排序、抽欄位 |
| `roster_status`, `roster_status_code`, `roster_is_active` | 🔵 API | 取 `rosterEntries[0].status` |
| `team_id`, `current_team_name` | 🔵 API | 取 `currentTeam` |
| `current_team_level` | 🟢 計算（對照表） | 另呼叫 `/teams/{team_id}` 取得 `sportId`，用 `levels.py` 的固定對照表轉成 `MLB/AAA/AA/A+/A` 等代碼；純查表，非數學運算 |
| `status_category`（active/injured/restricted/inactive/other） | 🟢 計算 | `helpers.py categorize_roster_status()`（64行），依 `roster_status_code` 對照固定代碼集合分類 |
| `height_cm` | 🟢 計算 | `helpers.py height_to_cm()`（190行）：`(呎×12+吋) × 2.54` |
| `weight_kg` | 🟢 計算 | `helpers.py lbs_to_kg()`（200行）：`磅 × 0.453592` |

下一場比賽：**端點** `GET /schedule?teamId=...`（`api.py get_next_game()` 第232–290行）
`date`, `opponent`, `is_home`, `venue`, `status` 為 🔵 API 原始欄位；`game_time` 為 🟢 計算（UTC → UTC+8 時區格式化，非統計運算）。

---

## 二、投手數據

### 2.1 基礎數據（🔵 API）

**端點**：`GET /people/{mlb_id}/stats?stats=yearByYear&group=pitching`（MLB）／加 `leagueListId=milb_all`（MiLB）
對應：`api.py get_player_stats()` → `sync.py _apply_yearbyyear_fields()`（255–316行）

| 欄位 | API 原始欄位 | 中文 |
|---|---|---|
| `era` | `era` | 自責分率 |
| `whip` | `whip` | 每局被上壘率 |
| `ip` | `inningsPitched` | 投球局數（棒球記法，如7.2＝7⅓局）|
| `so` | `strikeOuts` | 三振 |
| `wins` / `losses` | `wins` / `losses` | 勝／敗 |
| `bb` | `baseOnBalls` | 保送 |
| `sv` / `hld` | `saves` / `holds` | 救援成功／中繼成功 |
| `gs` | `gamesStarted` | 先發場次 |
| `earned_runs` | `earnedRuns` | 自責分 |
| `pitches` | `numberOfPitches` | 投球總數 |
| `bf` | `battersFaced` | 面對打者數 |
| `k_per_9` / `bb_per_9` / `h_per_9` / `hr_per_9` | `strikeoutsPer9Inn` / `walksPer9Inn` / `hitsPer9Inn` / `homeRunsPer9` | 每9局三振／保送／被安打／被全壘打（API 已算好）|
| `k_bb_ratio` | `strikeoutWalkRatio` | 三振保送比（API 已算好）|
| `p_per_ip` | `pitchesPerInning` | 每局用球數（API 已算好）|
| `win_pct` | `winPercentage` | 勝率（API 已算好，字串）|
| `strike_pct` | `strikePercentage` | 好球率（API 已算好，字串）|
| `p_ground_outs` / `p_air_outs` | `groundOuts` / `airOuts` | 滾地／飛球出局 |
| `runs_allowed` | `runs` | 被得分 |
| `p_hits` / `p_hr` / `p_hbp` / `p_ibb` | `hits` / `homeRuns` / `hitByPitch` / `intentionalWalks` | 被安打／被全壘打／觸身球／故意四壞 |
| `p_sb` / `p_cs` | `stolenBases` / `caughtStealing` | 被盜壘／阻殺 |
| `p_gdp` | `groundIntoDoublePlay` | 製造雙殺 |
| `p_doubles` / `p_triples` / `p_tb` / `p_ab` | `doubles` / `triples` / `totalBases` / `atBats` | 被二壘安打／三壘安打／壘打數／面對打數 |
| `svo` | `saveOpportunities` | 救援機會 |
| `outs` | `outs` | 總出局數 |
| `cg` / `sho` | `completeGames` / `shutouts` | 完投／完封 |
| `strikes` / `balks` / `wp` / `pickoffs` | `strikes` / `balks` / `wildPitches` / `pickoffs` | 好球數／犯規／暴投／牽制出局 |
| `gf` | `gamesFinished` | 終結比賽數 |
| `ir` / `irs` | `inheritedRunners` / `inheritedRunnersScored` | 繼承跑者／繼承跑者得分 |
| `p_sac_bunts` / `p_sac_flies` | `sacBunts` / `sacFlies` | 對手犧牲觸擊／犧牲高飛 |
| `p_avg` / `p_obp` / `p_slg` / `p_ops` | `avg` / `obp` / `slg` / `ops` | 被打擊三圍（API 已算好，字串）|
| `p_sb_pct` | `stolenBasePercentage` | 被盜壘成功率（API 已算好，字串）|
| `p_babip` | `babip` | 場內打擊率（API 已算好；若缺值程式會補算，見 2.3）|
| `p_go_ao` | `groundOutsToAirouts` | 滾飛比（API 已算好）|
| `qs` | `qualityStarts` | 優質先發 |

### 2.2 進階數據（🔵 API）

**端點**：`GET /people/{mlb_id}/stats?stats=seasonAdvanced&group=pitching&season={year}`
對應：`api.py get_player_advanced_stats()` → `sync.py _apply_advanced_fields()`（356–392行）

| 欄位 | API 原始欄位 |
|---|---|
| `qs` | `qualityStarts` |
| `bqr` | `bequeathedRunners`（遺留跑者）|
| `bqr_s` | `bequeathedRunnersScored`（遺留跑者得分）|
| `p_gidpo` | `gidpOpp`（雙殺機會）|
| `run_support` | `runSupport`（打線支援得分）|
| `rs_per_9` | `runsScoredPer9` |
| `p_babip` | `babip` |
| `pitches_per_pa` | `pitchesPerPlateAppearance` |

### 2.3 缺值補算（🟢 計算，僅在 API 未提供該值時才補上）

定義於 `helpers.py _compute_advanced_stats()`（第507–637行），只有目標欄位為 `None` 時才會寫入，絕不覆蓋 API 給的值。

| 欄位 | 公式 |
|---|---|
| `pitches_per_pa` | `pitches / bf` |
| `k_per_9` | `so × 9 / IP實際局數` |
| `bb_per_9` | `bb × 9 / IP實際局數` |
| `h_per_9` | `p_hits × 9 / IP實際局數` |
| `hr_per_9` | `p_hr × 9 / IP實際局數` |
| `p_per_ip` | `pitches / IP實際局數` |
| `rs_per_9` | `run_support × 9 / IP實際局數` |
| `k_bb_ratio` | `so / bb` |
| `k_pct` | `so / bf` |
| `bb_pct` | `bb / bf` |
| `strike_pct` | `strikes / pitches` |
| `p_babip` | `(p_hits − p_hr) / (p_ab − so − p_hr + p_sac_flies)`。註：改用 `p_ab`（對方打數）而非 `bf` 當分母，因為 `bf`≈PA 只扣掉 BB 卻漏扣 HBP／犧牲觸擊，會系統性低估 BABIP |
| `p_go_ao` | `p_ground_outs / p_air_outs` |
| `win_pct` | `wins / (wins + losses)` |
| `p_avg` | `p_hits / p_ab` |
| `p_obp` | `(p_hits + bb + p_hbp) / (p_ab + bb + p_hbp + p_sac_flies)` |
| `p_slg` | `p_tb / p_ab` |
| `p_ops` | `p_obp + p_slg` |
| `np`（別名） | `= pitches`（模板用別名，非新計算）|

以上是 `ip_to_outs()` / `outs_to_ip()`（`helpers.py` 171–184行）把「7.2 局」的棒球記法換算成真實出局數／分數局，供所有 /9 類公式使用。

### 2.4 MLB 進階指標：FIP / xFIP / WAR（🔵 API，僅 MLB）

**端點**：`GET /people/{mlb_id}/stats?stats=sabermetrics&group=pitching&season={year}`
對應：`api.py get_player_sabermetrics()`（352–371行）→ `sync.py _merge_statcast_into_season()` 第1095–1101行

| 欄位 | 來源 |
|---|---|
| `fip` | API `sabermetrics.fip`，四捨五入至小數點後2位 |
| `xfip` | API `sabermetrics.xfip` |
| `war` | API `sabermetrics.war` |

> 這三個指標常被誤以為是自製算法，但 **MLB 層級是 API 直接算好回傳的**，程式沒有重算。只有 MiLB（API 無此端點）才會走 2.5 的自製公式。

### 2.5 MiLB 版 FIP / xWPCT（🟢 計算，僅 MiLB）

`statcast.py compute_fip()`（1339–1368行）、`compute_xwpct()`（1371–1380行），因 MLB API 沒有 MiLB 的 sabermetrics 端點，程式自行計算：

```
FIP = (13×HR + 3×(BB+HBP) − 2×K) / IP實際局數 + cFIP
```
- 輸入 HR/BB/HBP/K/IP 皆為 🔵 API 原始計數欄位
- `cFIP`（聯盟修正常數）來自 `FIP_CONSTANTS` 表（2024年各層級人工預先算好的常數，MLB 3.247／AAA 3.896／AA 3.613／A+ 3.586／A 3.733），查不到年份時退回同層級的 2024 值，最終退回 3.2

```
xWPCT（Pythagenpat 1.83）= 1 / (1 + (FIP / 聯盟RA9)^1.83)
```
- 聯盟 RA9 來自 `LEAGUE_RA9` 常數表（MLB 4.40／AAA 5.10／AA 4.80／A+ 4.60／A 4.70，皆為程式內建近似值）

### 2.6 Expected Stats：對方期望打擊三圍（🔵 API，僅 MLB）

**端點**：`GET /people/{mlb_id}/stats?stats=expectedStatistics&group=pitching&season={year}`
對應：`api.py get_player_expected_stats()`（374–407行）

| 欄位 | API 原始欄位 | 說明 |
|---|---|---|
| `xba` | `avg` | 對方期望打擊率（Statcast 端算好的期望值，程式只改名）|
| `xslg` | `slg` | 對方期望長打率 |
| `xwoba` | `woba` | 對方期望 wOBA |
| `xwobacon` | `wobaCon` | 對方期望「有擊中球」wOBA |

> MiLB 呼叫此端點一律回傳 0.0（API 本身限制），因此只對 MLB 賽季有效，程式不會為 MiLB 另外計算 x 系列指標。

### 2.7 Statcast 逐球指標（🟢 全部計算，`statcast.py compute_pitcher_statcast()` 969–1003行）

原始輸入：`GET /game/{game_pk}/feed/live`（play-by-play）逐球資料，經 `extract_pitch_logs()`（206–326行）萃取成逐球 dict，快取在 `game_logs.pitches_json`。這些逐球欄位（球速 `start_speed`/`end_speed`、位移 `pfx_x/z`／`ivb`/`hb`、轉速 `spin_rate`、出球速度角度 `ev`/`la`、進壘位置 `zone` 等）本身是 🔵 API 算好的物理量，程式只是萃取存下來；下列才是程式在其上「聚合、分類、二次計算」出來的指標：

**選球紀律**（`_discipline_metrics()` 917–929行）
| 欄位 | 公式 |
|---|---|
| `swing_pct` | 揮棒數 / 總球數 |
| `whiff_pct` | 揮空數 / 揮棒數 |
| `swstr_pct` | 揮空數 / 總球數 |
| `csw_pct` | (被判好球數 + 揮空數) / 總球數 |
| `z_swing_pct` | 好球帶內揮棒數 / 好球帶內球數 |
| `o_swing_pct`（Chase%） | 好球帶外揮棒數 / 好球帶外球數 |
| `z_contact_pct` | 好球帶內有觸擊揮棒數 / 好球帶內揮棒數 |
| `zone_pct` | 好球帶內球數 / (好球帶內+外球數) |

判定邏輯：`zone` 1–9 視為好球帶內；11–14 視為好球帶外。揮棒/揮空判定依 API `details.code`（如 S/W/F/T 等）對照固定代碼集合（20–26行）。

**打擊品質（被打）**（`_batted_ball_metrics()` 932–961行）
| 欄位 | 公式 |
|---|---|
| `gb_pct` / `ld_pct` / `fb_pct` / `pu_pct` | 對應軌跡球數 / 總在場內擊球數（BBE）|
| `air_pct` | (fb + ld) / BBE |
| `barrel_pct` | Barrel 判定數 / BBE |
| `hard_hit_pct` | 出球速度≥95mph 的球數 / 有出球速度紀錄的 BBE 數 |
| `avg_ev` | 有出球速度紀錄之 BBE 的平均值 |
| `pull_pct` / `straight_pct` / `oppo_pct` / `pull_air_pct` | 依落點座標算出的拉打方向分類 / BBE |

Barrel 判定公式（`_is_barrel()` 395–415行，仿 Statcast 官方定義自行重建）：出球速度 <98mph 一律不算；≥98mph 時每加1mph，仰角下限−1°（下限 8°）、上限+1.5°（上限 50°），起始錨點 98mph→[26°,30°]。

拉打方向公式（`_spray_direction_from_coordinates()` 711–774行）：用 Gameday 座標算噴射角
```
angle = atan2(hc_x − 125.42, 198.27 − hc_y) × 0.75
```
（0.75 為透視修正係數，來源見程式內註解 The Hardball Times 2017），角度 < −15° 判為左外野、> +15° 判為右外野，再依打者慣用手轉換為 Pull/Straight/Oppo；座標缺失時退回用 `hitData.location` 概略分區（`_spray_direction_from_location()` 693–708行）。

**wOBA against**（`_compute_woba()` 898–914行）
```
woba_against = Σ(每個打席結果的固定權重) / 有效打席數
```
權重為 TJStats 固定值（`WOBA_WEIGHTS`：保送0.689／觸身0.720／一安0.881／二安1.254／三安1.589／全壘打2.048），故意四壞與犧牲觸擊排除在分母外。

**其他單一指標**
| 欄位 | 公式 |
|---|---|
| `hr_fb_pct` | 被全壘打數 / 飛球數 |
| `avg_extension` | 所有球的 `extension`（出手延伸）平均值 |
| `pa_count` | 上述 wOBA 計算所用的有效打席數 |

**球種細節（`pitch_arsenal`/`pitch_outcomes`/`pitch_usage_by_count`/`pitch_plinko`/`pitch_movement`）**
- `_compute_pitch_arsenal_pitcher()`（1006–1054行）：每球種的球速/位移/轉速/釋放點平均、Zone%/Chase%/Whiff%/Put-Away%（兩好球後三振數/兩好球球數）/wOBA
- `_compute_pitch_outcomes_pitcher()`（1057–1122行）：每球種對應的被打擊率、wOBA、CSW%、Barrel%、Hard-Hit% 等結果面指標
- `_compute_pitch_usage_by_count_pitcher()`（1125–1175行）：依球數狀態（領先/落後/兩好球前後等）分桶統計球種使用率
- `_compute_pitch_plinko()`（517–626行）：球數轉移路徑圖（0-0→0-1→…）逐節點球種分佈
- `compute_pitch_movement_chart()`（629–685行）：逐球位移點陣（HB/IVB 散佈圖用），僅做取樣（超過700球則等距抽樣，非統計計算）
- 以上皆依打者左右打分 all/L/R 三組（`_compute_pitcher_bat_side_splits()` 1178–1194行）

---

## 三、打者數據

### 3.1 基礎數據（🔵 API）

**端點**：`GET /people/{mlb_id}/stats?stats=yearByYear&group=hitting`
對應：`sync.py _apply_yearbyyear_fields()`（317–353行）

| 欄位 | API 原始欄位 |
|---|---|
| `avg` / `obp` / `slg` / `ops` | `avg` / `obp` / `slg` / `ops`（API 已算好）|
| `hr` / `rbi` | `homeRuns` / `rbi` |
| `sb` / `cs` | `stolenBases` / `caughtStealing` |
| `ab` / `hits` | `atBats` / `hits` |
| `hit_bb` | `baseOnBalls` |
| `pa` | `plateAppearances` |
| `doubles` / `triples` / `tb` | `doubles` / `triples` / `totalBases` |
| `hbp` | `hitByPitch` |
| `gdp` | `groundIntoDoublePlay` |
| `runs` | `runs` |
| `h_so` | `strikeOuts` |
| `ibb` | `intentionalWalks` |
| `h_ground_outs` / `h_air_outs` | `groundOuts` / `airOuts` |
| `pitches_seen` | `numberOfPitches` |
| `lob` | `leftOnBase` |
| `sac_bunts` / `sac_flies` | `sacBunts` / `sacFlies` |
| `ci` | `catchersInterference` |
| `babip` | `babip`（API 已算好；缺值時見 3.3）|
| `go_ao` | `groundOutsToAirouts`（API 已算好）|
| `sb_pct` / `cs_pct` | `stolenBasePercentage` / `caughtStealingPercentage`（字串）|
| `ab_per_hr` | `atBatsPerHomeRun`（API 已算好）|

### 3.2 進階數據（🔵 API）

**端點**：`GET /people/{mlb_id}/stats?stats=seasonAdvanced&group=hitting&season={year}`
對應：`sync.py _apply_advanced_fields()`（357–373行）

| 欄位 | API 原始欄位 |
|---|---|
| `roe` | `reachedOnError` |
| `wo` | `walkOffs` |
| `gidpo` | `gidpOpp` |
| `xbh` | `extraBaseHits`（API 已算好；缺值時見 3.3）|
| `babip` | `babip` |
| `pitches_per_pa` | `pitchesPerPlateAppearance` |

### 3.3 缺值補算（🟢 計算，僅在 API 未提供時補上）

定義於 `helpers.py _compute_advanced_stats()`（432–505行）

| 欄位 | 公式 |
|---|---|
| `p_per_pa` | 優先取 `pitches_per_pa`，否則 `pitches_seen / pa` |
| `xbh` | `doubles + triples + hr` |
| `iso` | `slg − avg` |
| `babip` | `(hits − hr) / (ab − h_so − hr + sac_flies)` |
| `ab_per_hr` | `ab / hr` |
| `go_ao` | `h_ground_outs / h_air_outs` |
| `sb_pct` | `sb / (sb + cs)` |
| `k_pct` | `h_so / pa` |
| `bb_pct` | `hit_bb / pa` |

### 3.4 Expected Stats：期望打擊三圍（🔵 API，僅 MLB）

**端點**：`GET /people/{mlb_id}/stats?stats=expectedStatistics&group=hitting&season={year}`
對應：`api.py get_player_expected_stats()`

| 欄位 | API 原始欄位 |
|---|---|
| `xba` | `avg` |
| `xslg` | `slg` |
| `xwoba` | `woba` |
| `xwobacon` | `wobaCon` |

同投手一樣，MiLB 呼叫恆回傳 0.0，因此只有 MLB 賽季顯示這組數據。

### 3.5 MLB 進階指標：WAR（🔵 API）與 wRC+（🔵 API｜🟢 計算 雙軌）

**端點**：`GET /people/{mlb_id}/stats?stats=sabermetrics&group=hitting&season={year}`
對應：`sync.py _merge_statcast_into_season()` 第1102–1112行

- `war`：🔵 直接取 API `sabermetrics.war`
- `wrc_plus`：🔵 直接取 API `sabermetrics.wRcPlus`（MLB 賽季合計值，換隊球員只寫入該年度第一筆記錄，避免重複顯示）

同時程式會**額外自行計算一份 wRC+ 存成 `wrc_plus_calc`**（不覆蓋 API 值），用於跟 API 版本對照 / 給 MiLB 使用：

### 3.6 wOBA / wRC+（TJBat+，🟢 計算，MiLB 為主要顯示欄位，MLB 為對照欄位）

定義於 `wrc_plus.py`，公式仿照 [TJStats Glossary](https://tjstats.ca/glossary/)：

**wOBA**（`compute_woba()` 44–77行，依賽季累計計數計算，不是逐球計算）
```
singles = hits − doubles − triples − hr
unintentional_bb = hit_bb − ibb
wOBA = (0.689×BB非故意 + 0.720×HBP + 0.881×一安 + 1.254×二安 + 1.589×三安 + 2.048×全壘打)
       / (AB + BB非故意 + SF + HBP)
```
輸入的 AB/H/2B/3B/HR/BB/IBB/HBP/SF 皆為 🔵 API 賽季計數欄位；權重為固定常數（與 2.7 節投手 wOBA 用同一組 `WOBA_WEIGHTS`）。

**wRC+**（`compute_wrc_plus()` 80–90行）
```
wRC/PA = (wOBA − 聯盟wOBA) / 1.24 + 聯盟R/PA
PFm    = 1 + (球場因子 − 1) × 0.5
wRC+   = round(100 × (wRC/PA / PFm) / 聯盟R/PA)
```
- `聯盟wOBA`、`聯盟R/PA`：🌐 從外部網站 **tjstats.ca** 即時爬取（`fetch_league_constants()` 131–163行），並非 MLB Stats API
- `球場因子`：🌐 同樣爬自 tjstats.ca（`fetch_park_factors()` 93–128行），依球員該年在該層級 PA 最多的球隊決定用哪支球隊的球場因子
- 每次 build 都重新抓取／計算，不寫回資料庫持久化（`annotate_wrc_plus()` 166–229行）

### 3.7 Statcast 逐球指標（🟢 全部計算，`statcast.py compute_batter_statcast()` 1202–1249行）

原始輸入同 2.7 節（逐球 play-by-play 資料）。除了與投手共用的選球紀律、打擊品質、拉打方向邏輯外，打者版額外有：

| 欄位 | 公式 / 說明 |
|---|---|
| `woba` | 同 3.6 節公式，但改用**逐球資料**現場計算（非賽季計數彙總），僅計入 PA 完結球 |
| `max_ev` | 該球員在場數據中最大出球速度 |
| `ev90` | 出球速度第90百分位數：所有 BBE 出球速度由小到大排序，取第 `int(N×0.9)` 位（註解說明：樣本數<10時與 tjstats 官方數字可能有落差）|
| `avg_la` | 所有在場內擊球的平均出球仰角 |
| `swsp_pct`（Sweet-Spot%） | 仰角落在 8°–32° 的擊球數 / 有仰角紀錄的擊球數 |
| `vs_pitch_types` | `_compute_vs_pitch_types_batter()`（1252–1331行）：對各球種的打擊率、wOBA、CSW%、Barrel%、Hard-Hit%、Put-Away% 等，排除 EP/FA 這類極少見的位置球員投球類型 |
| `pitch_plinko` | 依投手左右投手分 vs LHP / vs RHP 兩組球數轉移圖 |

---

## 四、守備數據（打者／投手共用）

**端點**：`GET /people/{mlb_id}/stats?stats=yearByYear&group=fielding`
對應：`sync.py`（589–611行）

| 欄位 | 分類 | API 原始欄位 / 公式 |
|---|---|---|
| `position`, `gp`, `gs` | 🔵 API | 守備位置、出賽場數、先發場數 |
| `innings` | 🔵 API | `innings` |
| `assists` | 🔵 API | `assists` |
| `putouts` | 🔵 API | `putOuts` |
| `errors` | 🔵 API | `errors` |
| `chances` | 🔵 API | `chances` |
| `fielding_pct` | 🔵 API | `fielding`（字串，API 已算好 (PO+A)/(PO+A+E)）|
| `dp` / `tp` | 🔵 API | `doublePlays` / `triplePlays` |
| `throwing_errors` | 🔵 API | `throwingErrors` |
| `range_factor_game` | 🔵 API | `rangeFactorPerGame`（API 已算好）|
| `range_factor_9` | 🔵 API | `rangeFactorPer9Inn`（API 已算好）|

守備數據**目前沒有任何自製計算欄位**，全部是 API 原值。

---

## 五、逐場紀錄（Game Log）

**端點**：`GET /people/{mlb_id}/stats?stats=gameLog&season={year}&group=hitting,pitching`
對應：`api.py get_game_logs()`，直接把該場的 `stats` dict 原封存成 `game_logs.stats_json`（🔵 API，欄位與第二、三節的 yearByYear 欄位同名）。

逐場的**逐球**資料（`pitches_json`）來自 `GET /game/{game_pk}/feed/live`，經 `extract_pitch_logs()` 萃取，欄位詳見第 2.7 節「原始輸入」說明，展開頁面用 `summarize_pitch_for_display()`（1388–1406行）做顯示用投影，未做二次計算。

---

## 六、生涯／賽季彙總邏輯

當同一年跨隊、跨層級，或要顯示生涯總計時，`helpers.py` 會把多筆 `season_stats` 列彙總後**重新計算比率型欄位**（而非直接加總比率）：

- `_sum_counting()`（300–306行）：把所有計數型欄位（PA/AB/HR/…／W/L/SV/SO/…）逐筆加總
- `_compute_rate_stats()`（309–346行）：用加總後的計數重算
  - `avg = Σhits / Σab`
  - `obp = calc_obp(Σhits, Σhit_bb, Σhbp, Σab, Σsac_flies)`
  - `slg = Σtb / Σab`；`ops = obp + slg`
  - `era = Σearned_runs / IP實際局數 × 9`
  - `whip = (Σp_hits + Σbb) / IP實際局數`
- 供 `compute_career()`（363–386行）、`compute_season_combined()`（389–401行）、`compute_year_groups()`（647–691行）三個函式使用
- 彙總完成後仍會呼叫 `_compute_advanced_stats()` 補上 ISO/BABIP/K%/BB%/FIP 相關欄位等衍生指標

---

## 七、跨層級 Statcast 合併邏輯

球員同年在多個層級（如 MLB＋AAA）都有出賽時，年度總覽列要顯示一個合併的 Statcast 摘要。
`builder.py _combine_statcast_dicts()`（479–558行）依不同性質的欄位選用不同權重做加權平均（🟢 計算，非簡單平均）：

| 欄位類型 | 加權基準 |
|---|---|
| 選球紀律（swing%/swstr%/csw%/zone%/z_swing%/o_swing%/z_contact%/strike%/extension）| 依各層級 `total_pitches` 加權 |
| 打擊品質（barrel%/hard_hit%/avg_ev/avg_la/sweet-spot%/GB-LD-FB-PU%/拉打方向%/HR-FB%/EV90）| 依各層級 `bbe`（在場內擊球數）加權 |
| wOBA / wOBA against | 依各層級 `pa_count` 加權 |
| `max_ev` | 取各層級最大值（非加權平均）|
| 球種細節（arsenal/outcomes/usage/plinko/movement）| 各自依球種出現次數加權合併 |

---

## 八、總結：API vs 計算 比例

- **量的角度**：資料庫欄位數七成以上直接來自 API（yearByYear／seasonAdvanced／gameLog／fielding 端點），包含基礎三圍、計數型數據、守備數據，甚至 MLB 層級的 FIP／xFIP／WAR／wRC+／xwOBA／xBA／xSLG 都是 API 直接給的，程式只做欄位改名。
- **質的角度**：真正由程式「自製算法」計算、且技術複雜度最高的三塊：
  1. **MiLB 版 FIP / xWPCT**：API 無 MiLB sabermetrics 端點，程式手算並套用人工預估的聯盟常數
  2. **wOBA / wRC+（TJBat+）**：全等級自算，還需結合外部網站 tjstats.ca 的球場因子與聯盟常數（唯一會呼叫 MLB 官方 API 以外資料來源的部分）
  3. **整套 Statcast 逐球分析**（選球紀律、打擊品質、Barrel%、拉打方向、球種細節、Pitch Plinko、球路移動圖，以及跨層級加權合併）：完全從原始逐球 JSON 現場推導，`statcast.py` 一支檔案就有1400多行邏輯
- 此外還有大量「缺值補算」（`helpers.py _compute_advanced_stats()`）—— 這些欄位**優先使用 API 給的值**，只在 API 未提供時才用公式補算，因此同一欄位在不同層級/年份可能一部分是 API 值、一部分是程式算的，屬於「混合來源」欄位。

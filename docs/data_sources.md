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
9. [逐球進階物理量與跑壘／守備歸屬](#九逐球進階物理量與跑壘守備歸屬2026-07-新增擷取)
10. [球員每場比賽詳細分析報告 — 設計構想](#十球員每場比賽詳細分析報告--設計構想)
11. [withMetrics 端點新增欄位（2026-07 遷移）](#十一withmetrics-端點新增欄位2026-07-遷移)

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

原始輸入：`GET /game/{game_pk}/withMetrics`（play-by-play）逐球資料，經 `extract_pitch_logs()`（206–326行）萃取成逐球 dict，快取在 `game_logs.pitches_json`。這些逐球欄位（球速 `start_speed`/`end_speed`、位移 `pfx_x/z`／`ivb`/`hb`、轉速 `spin_rate`、出球速度角度 `ev`/`la`、進壘位置 `zone` 等）本身是 🔵 API 算好的物理量，程式只是萃取存下來；下列才是程式在其上「聚合、分類、二次計算」出來的指標：

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

逐場的**逐球**資料（`pitches_json`）來自 `GET /game/{game_pk}/withMetrics`，經 `extract_pitch_logs()` 萃取，欄位詳見第 2.7 節「原始輸入」說明，展開頁面用 `summarize_pitch_for_display()`（1388–1406行）做顯示用投影，未做二次計算。

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

---

## 九、逐球進階物理量與跑壘／守備歸屬（2026-07 新增擷取）

`extract_pitch_logs()`（`site_builder/sync/extract.py`）原本只萃取球速、pfx 位移、轉速/轉向、出球初速/角度/距離等「Statcast 核心欄位」。以下欄位是**新增擷取**的，全部來自同一份 `GET /game/{game_pk}/withMetrics` 回應，不需要新的 API 端點，只是走訪原本就有的 JSON 節點：

### 9.1 新增的逐球物理量（每一球都有）

| 新欄位 | API 原始路徑 | 分類 | 說明 |
|---|---|---|---|
| `plate_time` | `pitchData.plateTime` | 🔵 API | 從出手到進壘的飛行時間（秒），數字越小代表打者反應時間越少 |
| `strike_zone_top` / `strike_zone_bottom` | `pitchData.strikeZoneTop` / `strikeZoneBottom` | 🔵 API | **這一球當下、這位打者站姿實際的好球帶上下界**（呎），逐球都可能因打者不同而變動，比固定的 `zone` 1–14 代碼精確 |
| `type_confidence` | `pitchData.typeConfidence` | 🔵 API | 球種自動分類的信心值（0–1），可用來過濾誤判球種 |
| `vx0` / `vy0` / `vz0` | `pitchData.coordinates.vX0/vY0/vZ0` | 🔵 API | 出手瞬間三軸初速度（呎/秒） |
| `ax` / `ay` / `az` | `pitchData.coordinates.aX/aY/aZ` | 🔵 API | 三軸加速度（含重力與 Magnus 力，呎/秒²） |
| `break_angle` / `break_length` / `break_y` | `pitchData.breaks.breakAngle/breakLength/breakY` | 🔵 API | 舊版 PITCHf/x 系統的位移量測（非 Statcast 的 pfx 系統），可當作 `ivb`/`hb` 的交叉驗證，本身分析價值不高 |

### 9.2 新增的打席結果節點（僅該打席最後一球，`is_pa_final=True` 時才有值）

| 新欄位 | API 原始路徑 | 說明 |
|---|---|---|
| `runners` | `play.runners[]`（經 `_extract_runners()` 精簡） | 該打席**每一位壘上跑者**的移動結果與守備功勞，見下表 |

`runners` 內每筆物件：

| 子欄位 | 說明 |
|---|---|
| `runner_id` | 跑者 MLB ID |
| `origin_base` / `start_base` / `end_base` | 出發前所在壘包 / 這個打席開始時壘包 / 打席結束後壘包（`null` 代表得分回本壘或出局） |
| `out_base` / `is_out` / `out_number` | 若在哪個壘包被封殺、是否出局、這是本局第幾個出局數 |
| `event` / `event_type` | 這名跑者的移動事件（如 `Single`／`Caught Stealing`／`Fielders Choice`） |
| `movement_reason` | 移動原因代碼（如 `r_force_out`、`r_stolen_base_2b`） |
| `is_scoring_event` | 是否為得分 |
| `rbi` | 這名跑者得分是否算打點（歸給打擊者） |
| `earned` | 這分是否為自責分 |
| `responsible_pitcher_id` | 該分責任歸屬的投手（換投後跑者得分歸前一位投手時用得到） |
| `credits[]` | 守備功勞列表：`{player_id, position, credit}`，`credit` 如 `f_assist`／`f_putout`／`f_error` |

> 已用真實比賽資料驗證（`Kai-Wei Teng` 2024-03-31 出賽），格式與欄位命名皆已確認正確可用。

### 9.3 這些新欄位能算出什麼——投手視角

**進場角度 VAA / HAA（Vertical / Horizontal Approach Angle）**
目前業界（Baseball Savant／各球團分析部門）最主流的「球路立體感」指標，需要 `vy0`/`vz0`/`az`/`ax`/`vx0` 才能算，過去完全沒存就無法回頭補算：
```
t = (vy_f − vy0) / ay        # vy_f 為進壘瞬間的 y 方向速度，由能量守恆解出
VAA = -atan(vz0 + az×t, vy_f) 轉角度
HAA = -atan(vx0 + ax×t, vy_f) 轉角度
```
VAA 數值越「平」（越接近 0°，即負得越少）代表球路進壘軌跡越平，對上打者的仰角更難產生高質量接觸，是評估「四縫線是否適合衝高」的核心指標之一，目前网站完全没有這個能力。

**精確 Zone%／Edge%**
現有 `zone_pct`/`o_swing_pct` 靠固定 `zone` 1–14 代碼判斷好壞球，同一顆球對不同身高/站姿的打者其實好球帶不同。有了逐球的 `strike_zone_top/bottom` 搭配既有的 `px`/`pz`，可以：
- 重算「真實好球帶內外」而非用代碼概估
- 新增 `edge_pct`（好球帶邊緣 ±2 吋內的球數比例）—— 抓「投手是否敢挑戰邊緣」

**球種分類品質過濾**
`type_confidence` 可以在算 `pitch_arsenal`／`vs_pitch_types` 前先過濾低信心球種（如 <0.5 直接併入「未分類」），避免罕見球路因誤判混進主要球種統計，讓球種佔比更準。

**節奏／知覺球速**
`plate_time` 搭配既有的 `extension`，可算「知覺球速」（Perceived Velocity，出手點離本壘板越近，同樣球速對打者來說反應時間越短，等同球更快）：
```
perceived_velo ≈ start_speed × (聯盟平均 extension / 該投手 extension)
```
`plate_time` 本身也可以直接當「打者反應時間」欄位呈現，比反推的知覺球速更直觀。

**責任分攤（繼承跑者失分）**
`runners[].responsible_pitcher_id` + `earned` 讓「這場比賽/這局失分該算在哪個投手頭上」可以逐球precisely重建，而不是只看 `ir`/`irs`（繼承跑者/繼承跑者得分）這種賽季彙總數字。

### 9.4 這些新欄位能算出什麼——打者視角

**打點／得分的逐球歸戶**
`runners[].rbi`／`is_scoring_event` 讓「這一球打點是誰打的、哪個跑者回本壘」可以逐球重建，能拿來做打席敘事文字（例如「二壘安打，讓二壘跑者回本壘得分」），而不是只顯示賽季 RBI 總數。

**跑壘價值（Baserunning Value）**
`origin_base`→`end_base` 的差距可以算「超前進壘」（Extra Bases Taken，如一壘安打時跑者從二壘直接衝回本壘），以及盜壘/阻殺的逐球細節（`movement_reason` 判斷 stolen_base/caught_stealing 種類）。這是目前完全沒有、也無法從賽季彙總數字回推的資訊。

**真實好球帶熱區圖**
同 9.3，`strike_zone_top/bottom` 讓打者的 swing/take 熱區圖可以用「這位打者當下實際好球帶」正規化，而不是套用聯盟固定尺寸的好球帶框。

**守備歸戶（連動 spray/BABIP 分析）**
`credits[]` 可以做到「這球被誰接殺／誰失誤」，未來若想做「運氣調整版 BABIP」（例如扣掉守備失誤造成的上壘），或是單純在打席敘事秀出「游擊手美技接殺」這類文字，都有資料基礎了。

---

## 十、球員每場比賽詳細分析報告 — 設計構想

以下是根據上述新欄位，針對「每場比賽詳細分析報告」這個未來功能的資料面規劃，分投手/打者兩個視角：

### 10.1 投手單場報告

- **逐打席敘事列表**：依打席分組（用 `is_pa_final` 分段），每組列出對戰打者、逐球球種/球速/位置/結果、最終打席結果（`pa_event_desc`）
- **好球帶疊圖**：用 `px`/`pz` 對照 `strike_zone_top/bottom` 畫出該場所有球的落點（現有 `pitch_movement` 只畫 IVB/HB 散佈圖，沒有畫好球帶落點圖）
- **VAA/HAA 依球種拆分**：驗證投手當天是否維持一致的進場角度（同球種角度飄動可能代表放球點跑掉、體能下滑）
- **單場版選球紀律指標**：`csw_pct`/`whiff_pct`/`o_swing_pct` 現有公式直接套用在單場的 pitches 子集合即可，不需要新邏輯
- **責任失分拆解**：用 `runners[].responsible_pitcher_id`/`earned` 重建「這場比賽的失分，哪些是自己造成、哪些是繼承來的」

### 10.2 打者單場報告

- **逐打席敘事列表**：面對的投手、逐球球種/好壞球/揮空與否/進球方式、最終打席結果，可做成類似「第3打席：對左投，4球（96mph速球外角/滑球揮空/…）→ 二壘安打，打點1分」的敘事文字
- **好球帶熱區圖（單場版）**：同 9.4，用該打者當天實際好球帶正規化
- **單場版 Chase%/Whiff%/Zone%**：套用現有 `_discipline_metrics()` 在單場 pitches 子集合
- **打點/得分敘事**：用 `runners[].rbi`/`is_scoring_event` 標出每個打點的來源打席

**⚠️ 打者跑壘資料的架構限制（需要額外處理）**：
`extract_pitch_logs(game_data, player_id, role="batter")` 目前只會抓「這位球員站在打擊區時」發生的球與 `runners`。但一個打者的**跑壘貢獻**（例如他自己上壘後被別人打回本壘、或自己盜壘）發生在**別的打席**——那個打席的打者是別人，`runners[]` 陣列裡才會出現這位球員的 `runner_id`。

換句話說，要完整重建「打者本場的跑壘表現」，現有的 `role="pitcher"/"batter"` 兩種掃描邏輯**都涵蓋不到**，需要新增第三種走訪方式：不看 `matchup.pitcher/batter`，而是走訪該場**所有** play 的 `runners[]`，篩出 `runner_id == player_id` 的紀錄。這塊目前完全沒有實作，是把「打者單場報告」做完整之前必須補上的一塊，建議放在 `site_builder/sync/extract.py` 新增一個 `extract_baserunning_events(game_data, player_id)` 函式，走訪 `liveData.plays.allPlays[].runners[]`（不受目前逐球迴圈的 batter/pitcher 過濾限制）。

### 10.3 回填既有比賽資料的注意事項

`sync_statcast()` 的判斷邏輯是「`pitches_json` 非空就跳過重抓」（`site_builder/sync/statcast.py` 第410行 `needs_fetch = pitches_json in (None, "[]")`），所以**已經抓過的歷史比賽不會自動補上這批新欄位**——新欄位只會出現在下次爬到的「新比賽」裡。如果要讓歷史比賽也補齊，需要先把對應的 `game_logs.pitches_json` 清空（例如 `UPDATE game_logs SET pitches_json='[]', hit_coord_checked=0`）再重跑 `python build.py statcast`，這樣會強迫重新呼叫 playByPlay 端點重新萃取。目前沒有現成指令做這件事，如果需要我可以加一個 `--reextract` 選項。

---

## 十一、withMetrics 端點新增欄位（2026-07 遷移）

`site_builder/api/games.py::get_game_play_by_play()` 這次改打 `GET /game/{game_pk}/withMetrics`
取代舊的 `GET /game/{game_pk}/feed/live`——`withMetrics` 是 `feed/live` 的**嚴格超集**，同一份
`liveData.plays` 結構下多了一批逐球/逐打席進階欄位。`extract_pitch_logs()`
（`site_builder/sync/extract.py`）擴充擷取這些欄位，且新增回傳值：現在是
`(pitches, nonpitch_events)` 2-tuple，`nonpitch_events` 對應新的 `game_logs.events_json`
欄位。完整的欄位實測結論（含兩處文檔更正：event 層級沒有 WP/LI/drama、`pitchNumber` 是
「每打席」而非「單場累計」）見 `docs/withmetrics_field_reference.md`。

### 11.1 新增的逐球欄位（每一球都有；`contextMetrics`/`hitData` 系列僅 MLB 有值，MiLB 為空）

| 新欄位 | API 原始路徑 | 分類 | 說明 |
|---|---|---|---|
| `play_id` | `playEvents[].playId` | 🔵 API | 這顆球的全域唯一 ID（UUID），可對接 Baseball Savant 逐球資料/影片，也可當穩定去重 key |
| `pitch_number` | `playEvents[].pitchNumber` | 🔵 API | **該打席內**第幾球（含界外），非投手單場累計球數（見上方更正說明） |
| `pre_outs` | `playEvents[].preCount.outs` | 🔵 API | 這顆球**投出之前**的出局數；`pre_balls`/`pre_strikes`（原本就有）現在也優先取 `preCount.balls`/`.strikes`，缺值才 fallback 手動累加 |
| `break_vertical` | `playEvents[].pitchData.breaks.breakVertical` | 🔵 API | 垂直位移（含重力），可做 `ivb`（誘導垂直位移）的交叉驗證 |
| `sz_plate_x`/`sz_plate_y`/`sz_plate_z` | `playEvents[].pitchData.strikeZoneInfo.plateX`/`.plateY`/`.plateZ` | 🔵 API | 新版好球帶模型下，球通過本壘板平面的三維座標 |
| `sz_top`/`sz_bottom` | `playEvents[].pitchData.strikeZoneInfo.strikeZoneTop`/`.strikeZoneBottom` | 🔵 API | 新版模型的好球帶上下緣（與既有 `strike_zone_top/bottom` 用不同建模管線，可能有微小差異） |
| `sz_flat`/`sz_rounded` | `playEvents[].pitchData.strikeZoneInfo.strikeZoneFlat`/`.strikeZoneRounded` | 🔵 API | 好球帶形狀模型是否套用平面版/圓角版邊界 |
| `sz_corner_radius` | `playEvents[].pitchData.strikeZoneInfo.strikeZoneCornerRadiusInches` | 🔵 API | 圓角好球帶模型的轉角半徑 |
| `sz_width_in`/`sz_depth_in` | `playEvents[].pitchData.strikeZoneInfo.widthInches`/`.depthInches` | 🔵 API | 3D 好球帶模型的寬度/景深 |
| `sz_edge_distance` | `playEvents[].pitchData.strikeZoneInfo.edgeDistance` | 🔵 API | 球心到好球帶邊緣的最短距離（可量化「差一點點的好壞球」） |
| `sz_is_strike` | `playEvents[].pitchData.strikeZoneInfo.isStrike` | 🔵 API | 新版模型下這球是否落在好球帶內，可能與裁判實際判決不同 |
| `avg_pitch_speed_player`/`max_pitch_speed_player`/`pitch_speed_pct`/`hr_ballparks` | `playEvents[].contextMetrics.averagePitchSpeedPlayer`/`.maxPitchSpeedPlayer`/`.pitchSpeedPlayerRank`/`.homeRunBallparks` | 🔵 API | 該投手當場同球種的平均/最快球速、這顆球速的球種內百分位排名、（若為全壘打）幾座球場也會出牆 |
| `hit_probability`/`bat_speed`/`is_sword_swing` | `playEvents[].hitData.hitProbability`/`.batSpeed`/`.isSwordSwing` | 🔵 API | 該擊球初速+仰角組合的聯盟平均安打機率、揮棒最大球棒速度（bat-tracking，2024/25 季起才有覆蓋）、是否為「劍擊」防禦性揮棒 |
| `defense` | `playEvents[].defense` | 🔵 API（濃縮巢狀結構） | 投球當下 9 個守備位置球員 id，經 `_condense_defense()` 只留 id（原節點含每個位置的完整 `{id, link}` dict） |
| `offense` | `playEvents[].offense` | 🔵 API（濃縮巢狀結構） | 投球當下打者防守位置＋投球前/後壘上跑者 id，經 `_condense_offense()` 濃縮（含代打/代跑偵測用的 `batter_pos`），不重存 `batter_id` |

### 11.2 新增的打席結果欄位（僅該打席最後一球，`is_pa_final=True` 時才有值，經 `_pa_context()`）

| 新欄位 | API 原始路徑 | 分類 | 說明 |
|---|---|---|---|
| `home_wp` | `play.homeTeamWinProbability` | 🔵 API | 打席結束當下主隊獲勝機率（百分比）；客隊視角未落地存欄位，讀取時用 `100 - home_wp` 反推 |
| `wpa` | `play.homeTeamWinProbabilityAdded` | 🔵 API | 這個打席讓主隊勝率增減多少個百分點（主隊視角，可正可負） |
| `leverage_index` | `play.leverageIndex` | 🔵 API | 局勢緊張度指數（LI），1.0 為聯盟平均 |
| `drama_index` | `play.dramaIndex` | 🔵 API | MLB 官方「精彩程度」綜合指標，混合勝率變化與比賽情境 |
| `pa_xwoba` | `play.contextMetrics.xWoba` | 🔵 API | 這個打席實際結果對應的期望 wOBA 貢獻值 |
| `catch_probability` | `play.contextMetrics.catchProbability` | 🔵 API | 若該打席是飛球，野手接殺這顆球的機率（Statcast Catch Probability） |
| `pa_final_balls`/`pa_final_strikes`/`pa_final_outs` | `play.count.balls`/`.strikes`/`.outs` | 🔵 API | 打席**結束當下**的球數，與逐球用的 `playEvents[].count`（投球後球數）不同 |

> ⚠️ **注意（經 2026-07 實測驗證）**：以上欄位在 **event（逐球）層級**也存在同名節點
> （`playEvents[].homeTeamWinProbability`/`.leverageIndex`/`.dramaIndex`），但實測抽樣
> 4 場（含 2024 世界大賽 G1）發現逐球層級這些欄位全部恆為 0，並非真正逐球更新——
> WP/LI/drama 只做到逐打席精度，因此程式**只在 `is_pa_final` 時**從 play 層級讀取，
> 完全不讀 event 層級的同名欄位。

### 11.3 新增的非投球事件：`events_json`（pickoff／stepoff）

`playEvents[]` 除了 `pitch`（投球）外還有 `action`/`pickoff`/`stepoff`/`no_pitch` 幾種
`type`。這次新增擷取其中的 `pickoff`（牽制）與 `stepoff`（投手板脫離）兩種，寫入
`game_logs.events_json`（`ALTER TABLE` 新增欄位，`TEXT NOT NULL DEFAULT '[]'`），經
`_condense_nonpitch_event()` 濃縮；`action`/`no_pitch` 這兩類事件本身仍完全略過。

| 新欄位（`events_json` 內每筆物件） | API 原始路徑 | 分類 | 說明 |
|---|---|---|---|
| `type` | `playEvents[].type` | 🔵 API | `pickoff` 或 `stepoff` |
| `index` | `playEvents[].index` | 🔵 API | 事件在 `playEvents[]` 中的序號 |
| `play_id` | `playEvents[].playId` | 🔵 API | 事件的全域唯一 ID |
| `inning` | `play.about.inning` | 🔵 API | 第幾局 |
| `pre_balls`/`pre_strikes`/`pre_outs` | `playEvents[].preCount.balls`/`.strikes`/`.outs` | 🔵 API | 事件發生前的球數 |
| `balls`/`strikes`/`outs` | `playEvents[].count.balls`/`.strikes`/`.outs` | 🔵 API | 事件發生後的球數 |
| `result_code`/`result_desc` | `playEvents[].details.code`/`.description` | 🔵 API | 結果代碼與播報文字 |
| `disengagement_num` | `playEvents[].details.disengagementNum` | 🔵 API | 該打席第幾次「脫離投手板」（2023 起限制牽制次數規則的計數） |
| `from_catcher` | `playEvents[].details.fromCatcher` | 🔵 API | 牽制是否由捕手發動 |
| `runner_going` | `playEvents[].details.runnerGoing` | 🔵 API | 跑者是否正在起跑（盜壘中）；僅部分事件有值 |
| `is_out` | `playEvents[].details.isOut` | 🔵 API | 是否造成出局 |
| `pitcher_id`/`batter_id` | `play.matchup.pitcher.id`/`.batter.id` | 🔵 API | 該打席的投打對戰雙方（events_json 本身不受 `role="pitcher"/"batter"` 過濾，附加這兩個欄位方便下游識別） |
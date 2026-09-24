# 數據欄位總表（前端視角，桌機版）

以頁面上看得到的欄位為主軸，往回追到模板變數與資料來源。手機版（`mobile/`）顯示同一批資料，不另列。

## 0. 讀法

每個欄位：**顯示名稱 → 模板變數 → 來源**。來源只有三種：

- `API: <路徑>`：MLB Stats API 原值，只做改名（對照見 `sync/field_maps.py`）
- `calc`：本地計算，一律附公式；`API→calc` 表示 API 有值用 API，沒值才本地算（`stats/core/annotate.py` 的規則：永不覆寫 API 值）
- `cache: <表>`：從 SQLite 快取表讀出的外部常數

公式符號：IP 一律是真實局數（`outs / 3`，不是 7.2 這種記法）；`/` 表示除法，分母 ≤ 0 時顯示 `-`。程式裡投手率一律以整數 `outs` 當分母精確計算（`ER × 9 / IP` 實作為 `ER × 27 / outs`，見 `stats/core/innings.py::per_nine`），不先除成浮點局數。

**數值精度與捨入**（`util/numbers.py`）：
- 全專案只有一個捨入實作 `round_half_up`：四捨五入（平手進位）。計數相除一律用精確分數再捨入，與 MLB Stats API 的做法相同（對照 DB 全部列驗證：AVG/OBP/SLG/OPS/ERA/WHIP/K/9/BB/9/H/9/P/IP/K/BB/BABIP/GO/AO/SB%/W% 單列 0 不符）。內建 `round()` 對二進位平手值取偶數（5/16 → .312，API 為 .313），已不再用於數據。
- 本地算的精度對齊 API：AVG 類三位；ERA、WHIP、K/9、BB/9、H/9、HR/9、P/IP、K/BB、GO/AO、AB/HR 兩位；P/PA 三位。模板再用 `floatformat(n)`（同樣 half-up）決定顯示位數。
- **OPS 採 MLB API 慣例：捨入後 OBP + 捨入後 SLG**，不是精確值相加（API 的 `ops` / `p_ops` 全部等於 `obp + slg`；精確值相加約兩成的列會差 .001）。
- FIP 存未捨入值（MLB 為 API 的五位小數），模板顯示時才捨入到兩位；xWPCT 與同層級轉隊合併都用未捨入值。

**季度彙總列一律重算**：`tab_stats` / `tab_advanced` 的年度彙總列（`grp.summary`）是 `aggregate_stats()` 把計數欄位加總後重算比率，即使該年只有一隊也一樣。API 提供的比率值（AVG、ERA…）只出現在多隊年份展開後的明細列。

---

## 1. 首頁 / 退役頁卡片（`index.j2` / `retired.j2`）

| 顯示 | 模板變數 | 來源 |
|---|---|---|
| 頭像 | `headshot_cdn_urls(mlb_id, player.latest_level_is_mlb)` | calc：最近一個有出賽的季度列是否為 MLB |
| 中文名 / 英文名 | `player.name_tw` / `player.name_en` | `src/data/roster.json` / API: `people[0].fullName` |
| 層級徽章（首頁） | `level_display(player.level, player.level_year)` | API: `currentTeam.id` → `/teams/{id}.sport.id`（`level_year` = 目標球季），僅限現役球員（`roster.is_active_player`）；非現役或無 currentTeam 時對 `season_stats` 最新年度呼叫 `highest_level_row()`，優先有出賽的列（`level_year` = 該季）。個人頁 hero 徽章同此欄位，退役頁卡片則是生涯最高層級（`highest_level_row(整個生涯)`），兩者定義不同。DB 存 tier key，舊制名稱（`A(Adv)` 等）由 `level_display` 依 `level_year` 產生 |
| 層級徽章（退役頁） | `level_display(item.badge_level, item.badge_year)` | calc：生涯有出賽的最高層級（`highest_level_row`），年份取該列的 `year` |
| 守位 | `player.position` | API: `primaryPosition.abbreviation` |
| 生涯年份（退役頁） | `stat.years_range` | calc：`min(year)–max(year)` |
| 投手 ERA / WHIP / K / W-L | `stat.era` `.whip` `.so` `.wins` `.losses` | 見下方「卡片數據列」 |
| 打者 AVG / HR / OPS / SB | `stat.avg` `.hr` `.ops` `.sb` | 同上 |
| 排序：層級 | `data-level-order` | calc：`level_rank(player.level)` |
| 排序：最近出賽 | `item.last_game_date` | `game_logs` 最新一場 `date` |

**卡片數據列**
- 首頁：當年度 `season_stats` 列（API 原值），挑選順序：隊名 = `player.team` → 層級 = `player.level` → 當年最高層級（`render/pages.py::_pick_display_stat`）。
- 退役頁：生涯合計 `compute_career()`，計數加總後重算：
  - `AVG = H / AB`
  - `OPS = OBP + SLG`（兩者先各自捨入到三位，見 §0），`OBP = (H + BB + HBP) / (AB + BB + HBP + SF)`，`SLG = TB / AB`
  - `ERA = ER × 9 / IP`
  - `WHIP = (H + BB) / IP`

---

## 2. 球員頁 Hero（`player_detail.j2`）

| 顯示 | 模板變數 | 來源 |
|---|---|---|
| 層級徽章 | `level_display(player.level, player.level_year)` | 同 §1 |
| 球隊 | `player.team` | API: `currentTeam.name`；缺值時同 §1 退回邏輯 |
| 投打 | `player.pitch_hand` / `player.bat_side` | API: `pitchHand.description` / `batSide.description`（取首字） |
| 數據條 | `latest_team_stat.*` | 當年度單一球隊列，挑選邏輯同首頁；投手另加 `IP`，打者另加 `RBI` |

---

## 3. 球員頁分頁

### 3.1 球員資料（`tab_bio.j2`）

| 顯示 | 模板變數 | 來源 |
|---|---|---|
| 出生日期 | `player.birth_date` | API: `birthDate` |
| 年齡 | `player.age` | calc：`今天年份 − 出生年 − (今天月日 < 生日月日 ? 1 : 0)` |
| 出生地 | `player.birth_city` / `birth_country` | API: `birthCity` / `birthCountry` |
| 身高 | `player.height` / `height_cm` | API: `height`；cm = `(ft × 12 + in) × 2.54` |
| 體重 | `player.weight` / `weight_kg` | API: `weight`；kg = `lbs × 0.453592` |
| 狀態 | `player.status_display` / `status_category` | API: `rosterEntries[0].status`；分類見 `roster.py::categorize_roster_status` |
| 下場比賽 | `next_game.opponent` `.is_home` `.game_time` `.venue` | API: `/schedule`（7 天窗口）；時間轉 UTC+8 |
| 異動紀錄 | `transactions[].date` `.type` `.description` | API: `transactions[]`（`effectiveDate`、`typeDesc`、`description`） |
| 生涯累計 | `total_career.*` | calc：`compute_career()`，公式同 §1 退役頁 |
| 當季合計 | `season_combined.*` | calc：`compute_year_groups()` 當年那一組的 `summary`（與成績表年度列同一物件），當年度所有隊加總重算並經 `annotate_row` |

### 3.2 基礎數據（`tab_stats.j2`）

明細列為 `season_stats.stat_json` 的 API 原值；彙總列規則見 §0。

**打者**

| 顯示 | 變數 | 來源 |
|---|---|---|
| G | `gp` | API: `gamesPlayed` |
| PA / AB / R / RBI / H / 2B / 3B / HR / SB / CS | `pa` `ab` `runs` `rbi` `hits` `doubles` `triples` `hr` `sb` `cs` | API: hitting 同名欄位 |
| BB / SO | `hit_bb` / `h_so` | API: hitting `baseOnBalls` / `strikeOuts` |
| AVG | `avg` | API→calc：`H / AB` |
| OBP | `obp` | API→calc：`(H + BB + HBP) / (AB + BB + HBP + SF)` |
| SLG | `slg` | API→calc：`TB / AB` |
| OPS | `ops` | API→calc：捨入後 `OBP + SLG`（見 §0） |

**投手**

| 顯示 | 變數 | 來源 |
|---|---|---|
| W/L / GS / SV / HLD / BF | `wins` `losses` `gs` `sv` `hld` `bf` | API: pitching 同名欄位 |
| IP | `ip` | API: `inningsPitched`；彙總列 = `Σouts` 轉回記法 |
| H / ER / HR / BB / HBP / SO | `p_hits` `earned_runs` `p_hr` `bb` `p_hbp` `so` | API: pitching `hits` `earnedRuns` `homeRuns` `baseOnBalls` `hitByPitch` `strikeOuts` |
| ERA | `era` | API→calc：`ER × 9 / IP` |

### 3.3 比賽紀錄（`tab_gamelogs.j2`）

全部為 `game_logs.stats_json` 的 API 原值（`/people/{id}/stats?stats=gameLog`），不做本地計算。

| 顯示 | 變數 | 備註 |
|---|---|---|
| 投手 IP/H/R/ER/BB/SO/HR/HB | `s.inningsPitched` … `s.hitByPitch` | |
| 投手 ERA | `s.era` | API 的「該層級季初至今累積值」，升降級會重置 |
| 投手結果 | `s.wins` / `losses` / `saves` / `holds` | W > L > S > H 優先序 |
| 打者 AB…CS | `s.atBats` … `s.caughtStealing` | |
| 打者 AVG / OPS | `s.avg` / `s.ops` | 同 ERA，為 API 累積值 |
| 逐球展開 | `log.pitch_data_url` | 見下表 |

**逐球展開 JSON**（`render/pitch_log.py`，每場一檔 `data/pitchlogs/{id}/{game}.json`）

| 顯示 | 鍵 | 來源（`pitches_json` → API `playEvents[]`） |
|---|---|---|
| 局數 | `inning` | `about.inning` |
| 球種 | `pitch_type` / `pitch_name` | `details.type.code` / `.description` |
| 球速 | `speed` | `pitchData.startSpeed` |
| 進壘區 | `zone` | `pitchData.zone`（1–9 好球帶，11–14 壞球帶） |
| 結果 | `result` | `details.description`（缺則 `details.code`） |
| EV / LA | `ev` / `la` | `hitData.launchSpeed` / `launchAngle` |
| iVB / HB | `ivb` / `hb` | `pitchData.breaks.breakVerticalInduced` / `breakHorizontal` |
| 轉速 / 延伸 | `spin` / `extension` | `breaks.spinRate` / `pitchData.extension` |
| 打席結果 | `pa_event` | `result.event`（僅打席最後一球） |
| 投球前球數 | `pre_balls` / `pre_strikes` | `preCount`；缺則由前一球 `count` 推算 |
| 影片 | `video` | cache: `play_videos`（`/game/{pk}/content`，僅 MLB） |

### 3.4 進階數據（`tab_advanced.j2`）

#### 3.4.1 歷年進階數據（`season_stats` 衍生）

**投手**

| 顯示 | 變數 | 來源 / 公式 |
|---|---|---|
| WHIP | `whip` | API→calc：`(H + BB) / IP` |
| K/9 | `k_per_9` | API→calc：`SO × 9 / IP`（API 與 calc 皆存兩位，模板顯示一位；API 值先捨入過一次，見 §6-11） |
| BB/9 | `bb_per_9` | API→calc：`BB × 9 / IP` |
| H/9 | `h_per_9` | API→calc：`H × 9 / IP` |
| HR/9 | `hr_per_9` | API→calc：`HR × 9 / IP` |
| K/BB | `k_bb_ratio` | API→calc：`SO / BB` |
| K% | `p_k_pct` | calc：`SO / BF`（同 FanGraphs `K / TBF`；與打者 `k_pct` 分開存，避免有打擊紀錄的投手被打者值遮蔽） |
| BB% | `p_bb_pct` | calc：`BB / BF`（同 FanGraphs `BB / TBF`，BB 含 IBB） |
| Strike% | `strike_pct` | API→calc：`Strikes / Pitches`（float `0.64`，顯示為 `0.640`，非百分比格式；API 值實際只精確到兩位並補 0，calc 為三位，見 §6-12） |
| AVG / OBP / SLG / OPS（被打） | `p_avg` `p_obp` `p_slg` `p_ops` | API→calc：`H/AB`、`(H+BB+HBP)/(AB+BB+HBP+SF)`、`TB/AB`、捨入後 `OBP+SLG`（皆用對手打擊欄位 `p_*`） |
| BABIP | `p_babip` | API→calc：`(H − HR) / (AB − SO − HR + SF)` |
| GO/AO | `p_go_ao` | API→calc：`GO / AO` |
| P/PA | `pitches_per_pa` | API: `pitchesPerPlateAppearance`→calc：`Pitches / BF` ⚠️ 見 §6-1 |

**打者**

| 顯示 | 變數 | 來源 / 公式 |
|---|---|---|
| K% | `k_pct` | calc：`SO / PA` |
| BB% | `bb_pct` | calc：`BB / PA` |
| ISO | `iso` | calc：`(TB − H) / AB`（= FanGraphs 的 SLG − AVG，但用計數直接算，不拿兩個已捨入值相減；缺 TB 或 H 時留空） |
| BABIP | `babip` | API→calc：`(H − HR) / (AB − SO − HR + SF)` |
| XBH | `xbh` | API: `extraBaseHits`→calc：`2B + 3B + HR` |
| AB/HR | `ab_per_hr` | API→calc：`AB / HR` |
| GO/AO | `go_ao` | API→calc：`GO / AO` |
| SB% | `sb_pct` | API→calc：`SB / (SB + CS)`（float，顯示 `0.500`） |
| P/PA | `p_per_pa` | API: `pitchesPerPlateAppearance`→calc：`PitchesSeen / PA` |
| IBB / HBP / GIDP / SF / SH / LOB | `ibb` `hbp` `gdp` `sac_flies` `sac_bunts` `lob` | API: hitting 同名欄位 |
| GIDPO / ROE / WO | `gidpo` `roe` `wo` | API（seasonAdvanced）: `gidpOpp` / `reachedOnError` / `walkOffs` |

#### 3.4.2 Statcast 概覽

`sc.*` 來自 `season_stats.stat_json.statcast`（sync 時由逐球資料算好寫入）；「合計」列為當年所有層級逐球資料合併後重算，不是加權平均。以下通用定義：

- **BBE**：`is_in_play = true` 的球數
- **BBE_ev**：BBE 中有 EV 的球數
- **Barrel**：`EV ≥ 98` 且 `LA ∈ [max(8, 26 − (EV−98)), min(50, 30 + 1.5(EV−98))]`
- **Hard-Hit**：`EV ≥ 95`
- **wOBA 權重**（TJStats 固定值）：uBB .689、HBP .720、1B .881、2B 1.254、3B 1.589、HR 2.048

| 顯示 | 變數 | 公式 |
|---|---|---|
| FIP（MLB） | `ss_row.fip` | API: sabermetrics `fip`（存五位小數原值，顯示兩位） |
| FIP（MiLB） | `ss_row.fip` | calc：`(13·HR + 3·(BB + HBP) − 2·SO) / IP + C`；`C = lgERA − (13·lgHR + 3·(lgBB + lgHBP) − 2·lgSO) / lgIP`，兩式共用 `stats/advanced/fip.py::_fip_raw`；lgERA = `ER × 27 / outs` 不捨入（`per_nine(..., digits=None)`，它是 C 的輸入）（cache: `league_fip_constants`，優先用球員所屬聯盟，缺則用全層級）。2005 年以前 MiLB：API 球隊合計沒有 `earnedRuns`，lgERA 與 C 解不出，FIP / xWPCT 留空（不套預設常數；FanGraphs 的 MiLB 也從 2006 年開始）。不需要逐球資料，每一列都算（`sync/advanced.py`） |
| xWPCT | `ss_row.xwpct` | calc：`1 / (1 + (FIP / lgERA)^1.83)`；lgERA 一律用全層級 |
| wOBA（投手 `woba_against` / 打者 `woba`） | `sc.woba*` | calc（逐球）：`Σ權重 / 打席數`，打席數排除 IBB、SH（含 `sac_bunt_double_play`）、捕手妨礙、打席未完成（牽制／盜壘出局、跑者出局、再見暴投、比賽中止）（`stats/core/pa_outcomes.py`）⚠️ 見 §6-3 |
| xwOBA | `ss_row.expected.xwoba` | API: `stats=expectedStatistics` `woba`（MiLB 全為 0，不寫入） |
| wRC+（MLB） | `ss_row.wrc_plus` → 缺則 `wrc_plus_calc` | API: sabermetrics `wRcPlus`（小數，四捨五入成整數，與 FanGraphs 顯示一致），缺則同下 |
| wRC+（MiLB） | `ss_row.wrc_plus` | calc：`100 × ((wOBA − lgwOBA)/1.24 + lgR/PA) / PFm / lgR/PA`，`PFm = 1 + (PF − 1) × 0.5`；此處 wOBA 為**季度計數版**：`(.689·uBB + .720·HBP + .881·1B + 1.254·2B + 1.589·3B + 2.048·HR) / (AB + uBB + SF + HBP)`；PF / lgwOBA / lgR/PA 來自 cache: `tjstats_*` |
| WAR（打者） | `ss_row.war` | API: sabermetrics `war`（僅 MLB） |
| Barrel% | `sc.barrel_pct` | calc：`Barrels / BBE_ev` |
| Hard-Hit% | `sc.hard_hit_pct` | calc：`HardHit / BBE_ev` |
| Avg EV | `sc.avg_ev` | calc：`ΣEV / BBE_ev` |
| Max EV | `sc.max_ev` | calc：`max(EV)` |
| EV90 | `sc.ev90` | calc：EV 升冪排序後取第 `min(⌊0.9n⌋, n−1)` 個 |
| Avg LA | `sc.avg_la` | calc：`ΣLA / (有 LA 的 BBE 數)` |
| SwSp% | `sc.swsp_pct` | calc：`(8° ≤ LA ≤ 32° 的球數) / (有 LA 的 BBE 數)` |
| GB% | `sc.gb_pct` | calc：`GB / (GB + LD + FB + PU)` |
| HR/FB% | `sc.hr_fb_pct` | calc：`HR / FB`，分子為全部 HR（同 FanGraphs），分母只含 `fly_ball` ⚠️ 見 §6-4 |
| Whiff% | `sc.whiff_pct` | calc：同 §3.4.3 |
| Avg Ext | `sc.avg_extension` | calc：`Σextension / (有 extension 的球數)` |
| BBE | `sc.bbe` | calc：BBE ⚠️ 見 §6-5 |

#### 3.4.3 Plate Discipline

逐球定義（`stats/core/pitches.py`、`constants.py`）：
- **Swing**：`result_code ∈ {S, W, F, T, M, L, O, R, Q, X, D, E}`
- **Whiff**：`result_code ∈ {S, W, T, M, O, Q}`
- **Called strike**：`result_code = C`
- **InZone**：`zone ∈ 1–9`；**OutZone**：`zone ∈ 11–14`（無 zone 的球兩邊都不算）

| 顯示 | 變數 | 公式 |
|---|---|---|
| Pitches | `sc.total_pitches` | calc：球數 |
| Strike%（打者） | `sc.strike_pct` | calc：`(is_strike 或 is_in_play) / Pitches` |
| Zone% | `sc.zone_pct` | calc：`InZone / (InZone + OutZone)` |
| Z-Swing% | `sc.z_swing_pct` | calc：`InZoneSwings / InZone` |
| O-Swing% | `sc.o_swing_pct` | calc：`OutZoneSwings / OutZone` |
| Z-Contact% | `sc.z_contact_pct` | calc：`(InZoneSwings − InZoneWhiffs) / InZoneSwings` |
| Swing% | `sc.swing_pct` | calc：`Swings / Pitches` |
| Whiff% | `sc.whiff_pct` | calc：`Whiffs / Swings` |
| CSW% | `sc.csw_pct` | calc：`(CalledStrikes + Whiffs) / Pitches` |
| SwStr% | `sc.swstr_pct` | calc：`Whiffs / Pitches` |

#### 3.4.4 擊球型態

擊球分類（`hitData.trajectory`）：GB = `ground_ball, bunt_grounder`；LD = `line_drive, bunt_line_drive`；FB = `fly_ball`；PU = `popup, bunt_popup`。
方向：Gameday 座標 `angle = atan2(x − 125.42, 198.27 − y) × 0.75`（度），`< −15°` 左、`> 15°` 右、其餘中；無座標則用 `hitData.location` 守位代碼；再依打者左右打換成 Pull / Oppo。

| 顯示 | 變數 | 公式 |
|---|---|---|
| BBE | `sc.bbe` | 同 §3.4.2 |
| GB% / LD% / FB% / PU% | `sc.gb_pct` … | calc：`各類 / (GB + LD + FB + PU)` |
| Air% | `sc.air_pct` | calc：`(LD + FB) / (GB + LD + FB + PU)` |
| Pull% / Straight% / Oppo% | `sc.pull_pct` … | calc：`各方向 / 有方向的擊球數` |
| PullAir%（打者） | `sc.pull_air_pct` | calc：`(Pull 且 LD/FB) / 有方向的擊球數` |

#### 3.4.5 球種分析

先排除 `pitch_type ∈ {UN, IN, PO, AB, AS, NP}` 與未知球種。投手可切換對戰左/右打（`bat_side`），打者可切換對戰左/右投（`pitch_hand`）。打者表另排除觸擊打席與觸擊球（`core/atypical.py`）：觸擊打席 = 以 `constants.SAC_BUNT_EVENTS`（`sac_bunt`、`sac_bunt_double_play`）結束，或擊球軌跡屬 `BUNT_TRAJECTORIES`；沒有 hitData 的比賽只能靠事件判斷。

**投手：球種數據**（`sc.pitch_arsenal[]`）

| 顯示 | 變數 | 公式 |
|---|---|---|
| Pitch% | `pct` | `該球種球數 / 總球數` |
| Velo | `velo` | `mean(startSpeed)` |
| iVB / HB | `ivb` / `hb` | `mean(breakVerticalInduced)` / `mean(breakHorizontal)` |
| Spin | `spin` | `mean(spinRate)` |
| Ext. | `extension` | `mean(extension)` |
| vRel / hRel | `v_rel` / `h_rel` | 求 `y(t) = 60.5 − extension` 的 t（取 \|t\| 較小的根），`z = z0 + vz0·t + ½az·t²`、`x = x0 + vx0·t + ½ax·t²`，再取平均；整組無 extension（2017 前）改求值在 y = 50 平面 |
| Zone% / Chase% / Whiff% | `zone_pct` `chase_pct` `whiff_pct` | 同 §3.4.3 |

**投手：對戰結果**（`sc.pitch_outcomes[]`）

| 顯示 | 變數 | 公式 |
|---|---|---|
| Pitches / Pitch% | `count` / `pct` | 同上 |
| Strike% | `strike_pct` | `(is_strike 或 is_in_play) / Pitches` |
| Z-Whiff% | `z_whiff_pct` | `InZoneWhiffs / InZoneSwings` |
| O-Swing% / SwStr% / CSW% | … | 同 §3.4.3 |
| PutAway% | `put_away_pct` | `兩好球時投出且該打席以三振結束的球數 / 兩好球時的總球數` |
| AVG | `avg` | `H / AB`（逐球：AB = 打席 − BB − HBP − SF − SH − IBB − 捕手妨礙；犧牲雙殺比照犧牲）⚠️ 見 §6-3 |
| wOBA | `woba` | 同 §3.4.2 |
| Barrel% / Hard-Hit% | … | 同 §3.4.2 |

**打者：對戰球種 / 分類**（`sc.vs_pitch_types[]` / `vs_pitch_groups[]`）：欄位與公式同上兩表（Strike%、Zone%、Z-Swing%、O-Swing%、Whiff%、SwStr%、CSW%、PutAway%、AVG、wOBA、Barrel%、Hard-Hit%）。分類 = 速球 / 變化球 / 變速球（`constants.PITCH_TYPE_GROUPS`）。

**各球數配球比例**（`pitch_usage_by_count` / `pitch_group_usage_by_count`）：`某球數區間內該球種球數 / 該區間總球數`，區間定義見 `constants.COUNT_USAGE_BUCKETS`，依投球**前**球數分組。

### 3.5 守備數據（`tab_fielding.j2`）

全部為 API 原值（`season_stats.fielding_json`，來自 yearByYear `fielding` group），無本地計算。

| 顯示 | 變數 | API 欄位 |
|---|---|---|
| POS / GP / GS / INN | `position` `gp` `gs` `innings` | `position.abbreviation` `gamesPlayed` `gamesStarted` `innings` |
| TC / PO / A / E | `chances` `putouts` `assists` `errors` | `chances` `putOuts` `assists` `errors` |
| FLD% | `fielding_pct` | `fielding`（API 已算好：`(PO + A) / (PO + A + E)`） |
| DP / TP / TE | `dp` `tp` `throwing_errors` | `doublePlays` `triplePlays` `throwingErrors` |
| RF/G / RF/9 | `range_factor_game` / `range_factor_9` | `rangeFactorPerGame` / `rangeFactorPer9Inn` |

### 3.6 數據圖表（`tab_plot.j2`）

**賽季走勢圖**（`graph/season_trend.py`，排除季後賽）：每場為「季初至該場」的累積值；「All Levels」跨層級連續累加（不用 API 的逐層級累積值）。每場的逐球彙整與計數併入總帳後，直接呼叫下表的 `stats/` 函式計算，走勢圖本身不寫公式，因此最後一點與同範圍的球季值相同（wOBA 的最後一位例外，見下表）。

| 數據 | 公式 |
|---|---|
| ERA（投） | `ΣER × 27 / Σouts` |
| AVG | `ΣH / ΣAB` |
| K% / BB%（投） | `ΣSO / ΣBF`、`ΣBB / ΣBF` |
| K% / BB%（打） | `ΣSO / ΣPA`、`ΣBB / ΣPA` |
| wOBA（打） | 同 §3.4.2 逐球版；分子分母為逐場 `compute_pa_outcome_totals` 小計相加，浮點相加順序與球季一次計算不同，最後一位可能不同（顯示至小數第三位不受影響） |
| Exit Velocity | `ΣEV / BBE_ev`（對季初至今的 `bbe_ev` 呼叫 `compute_avg_ev`，與球季值同一個函式） |
| HardHit% / Barrel% | `HardHit / BBE_ev`、`Barrels / BBE_ev` |
| SweetSpot%（打） | 同 SwSp% |
| Whiff% / CSW% / SwStr% / Chase% / Z-Contact% | 同 §3.4.3 |

以上計數來自 `game_logs.stats_json`（ER、outs、H、AB、SO、BB、BF、PA）與 `pitches_json`（其餘）。

**球種使用 / 位移圖（投手）**：`sc.pitcher_bat_side_splits`（同 §3.4.5）與 `sc.pitch_movement`（每球 `[type, HB, iVB, velo, spin]`，超過 700 點會抽樣）。
**Pitch Plinko**：`sc.pitch_plinko`，各球數節點的球種比例與球數轉移（`graph/plinko.py`）。

---

## 4. 附錄：DB 表格速查

| 表 | 用途 | 寫入時機 |
|---|---|---|
| `players` | 球員基本資料、現役隊伍、異動、下場比賽 | `sync` / `refresh`（`sync/players.py::_write_player_to_db`） |
| `season_stats` | 每 (球員, 年, 隊) 一列；`stat_json` = §3.2/3.4.1 欄位 + `statcast` / `saber` / `expected` / `fip` / `xwpct` / `lg_era` / `war` / `wrc_plus`；`fielding_json` = §3.5 | 計數：`sync`；Statcast 與進階：`statcast` |
| `game_logs` | 每場一列；`stats_json` = §3.3；`pitches_json` = 逐球資料（結構見 `sync/extract.py::extract_pitch_logs`） | `stats_json`：`sync`；`pitches_json`：`statcast` |
| `play_videos` | play_id → 影片 URL | `statcast` |
| `tjstats_park_factors` / `tjstats_league_constants` | wRC+ 的 PF、lgwOBA、lgR/PA | build 時缺值才抓（`--update-constants` 強制） |
| `league_fip_constants` | 每 (層級, 年, 聯盟) 的 FIP 常數 C 與 lgERA；`league_name = ''` 為全層級 | `statcast` 時：當季每次重算，過去球季缺值才算（`--update-constants` 強制） |
| `season_fetches` | 過去球季的外部逐年資料「已成功抓過」登記（`sabermetrics` / `expected` / `fip_constants`） | `statcast` 時成功抓取過去球季後寫入 |

**外部逐年資料的重抓規則**（`db/season_fetches.py`）：`saber`、`expected`、FIP 常數在當季每次重抓；
過去球季成功抓過一次（含 API 成功但沒有資料）就不再抓，`saber` 衍生的 `fip` / `xfip` / `war` / `wrc_plus` /
`xwpct` 仍每次以存下的 `saber` 重算。`--full-history` 強制重抓 `saber` / `expected`，`--update-constants`
強制重抓 FIP 常數與 tjstats 常數。MLB 每次回傳的歷史 sabermetrics 在小數點後 4–6 位會有微幅浮動
（例：2024 WAR -0.169036 / -0.169076），凍結過去球季不影響顯示值。

**API 端點 → 寫入位置**

| 端點 | 寫入 | 函式 |
|---|---|---|
| `/people/{id}?hydrate=transactions,rosterEntries,currentTeam` | `players` | `api/players.py::get_player_profile` |
| `/teams/{id}` | `players.level`（`sport.id` 經 `sport_to_tier_key()` 轉 tier key）、`players.level_year` | 同上 |
| `/people/{id}/stats?stats=yearByYear&group=hitting,pitching,fielding`（MiLB 加 `leagueListId=milb_all`） | `season_stats.stat_json` 計數 / `fielding_json` | `api/stats.py::get_player_stats` |
| `/people/{id}/stats?stats=seasonAdvanced&group=hitting,pitching` | `stat_json` 的 `roe` `wo` `gidpo` `xbh` `bqr` `run_support` 等 | `get_player_advanced_stats` |
| `/people/{id}/stats?stats=gameLog` | `game_logs.stats_json` | `get_game_logs` |
| `/people/{id}/stats?stats=sabermetrics`（僅 MLB） | `stat_json.saber` / `fip` / `xfip` / `war` / `wrc_plus` | `get_player_sabermetrics` |
| `/people/{id}/stats?stats=expectedStatistics` | `stat_json.expected` | `get_player_expected_stats` |
| `/game/{pk}/withMetrics` | `game_logs.pitches_json` / `events_json` | `api/games.py::get_game_play_by_play` |
| `/game/{pk}/content` | `play_videos` | `api/content.py` |
| `/schedule?teamId=…`（7 天） | `players.next_game_json` | `api/schedule.py::get_next_game` |
| 聯盟球隊投球總數 | `league_fip_constants` | `api/league_stats.py` |
| tjstats.ca（爬蟲） | `tjstats_*` | `api/tjstats.py` |

不影響畫面但影響流程的欄位：`game_logs.pbp_version`（逐球資料抽取版本，落後或比賽未完賽就重抓）、`players.next_game_for_season` / `next_game_updated_at`（下場比賽快照是否過期）。

---

## 5. 已抓取但未被下游使用的資料

以下欄位已存進 DB，但沒有任何模板、render、stats 或 JS 讀取（寫入後僅被加總或原樣保留）。

**`season_stats.stat_json`（API 計數，只參與 `COUNTING_FIELDS` 加總，從未顯示）**

- 投手：`balks` `wp` `pickoffs` `cg` `sho` `gf` `svo` `qs` `ir` `irs` `bqr` `bqr_s` `runs_allowed` `p_ibb` `p_sb` `p_cs` `p_gdp` `p_gidpo` `p_doubles` `p_triples` `p_sac_bunts` `run_support`
- 投手（float）：`win_pct` `p_sb_pct`
- 打者：`ci`（捕手妨礙）、`cs_pct`
- 本地算了但沒顯示：`p_per_ip`（`Pitches / IP`）、`rs_per_9`（`RunSupport × 9 / IP`）、`win_pct`（`W / (W + L)`）

**`season_stats.stat_json` 的進階區塊**

- `saber`：MLB sabermetrics 整包原樣保存，只取出 `fip` / `xfip` / `war` / `wRcPlus`。一律是**整季合計**：API 對轉隊球員會回整季列（沒有 `team`、帶 `numTeams`）加各隊列，`_season_total_saber()` 只取整季列，不取單隊值。投打一致：同一份整季值寫進該年每一隊的 MLB 列（投手 FIP 以 IP 加權合併後仍是整季值，WAR/wRC+ 由 render 取任一非空值）
- `xfip`（投手）、`war`（投手）：已寫入但模板只顯示打者 WAR
- `lg_era`：只作為 xWPCT 輸入，未顯示
- `expected.xba` / `xslg` / `xwobacon`：只顯示 `xwoba`
- `statcast.pa_count`、`*_den`（`whiff_pct_den` 等）、`two_strike_count`：分母計數，未顯示也未使用

**`game_logs.pitches_json`（逐球，來自 `game/{pk}/withMetrics`，路徑相對於 `playEvents[]`）**

`withMetrics` 欄位的實測結論見 `docs/withmetrics_field_reference.md`。

| 欄位 | API 路徑 | 意義 / 限制 |
|---|---|---|
| `end_speed` | `pitchData.endSpeed` | 進壘球速 |
| `plate_time` | `pitchData.plateTime` | 出手到進壘的飛行時間（秒） |
| `type_confidence` | `pitchData.typeConfidence` | 球種自動分類信心值（0–1） |
| `pfx_x` / `pfx_z` | `pitchData.coordinates.pfxX/pfxZ` | PITCHf/x 位移（吋） |
| `px` / `pz` | `pitchData.coordinates.pX/pZ` | 進壘位置（呎，本壘板中心為原點） |
| `spin_dir` | `pitchData.breaks.spinDirection` | 轉軸方向（度） |
| `break_angle` / `break_length` / `break_y` | `pitchData.breaks.*` | 舊版 PITCHf/x 位移量測 |
| `break_vertical` | `pitchData.breaks.breakVertical` | 含重力的垂直位移 |
| `strike_zone_top` / `strike_zone_bottom` | `pitchData.strikeZoneTop/Bottom` | 該打者當下的好球帶上下緣（呎） |
| `sz_plate_x/y/z` | `pitchData.strikeZoneInfo.plateX/Y/Z` | 新版好球帶模型下，球通過本壘板的座標 |
| `sz_top` / `sz_bottom` | `strikeZoneInfo.strikeZoneTop/Bottom` | 新版模型的上下緣（與上一列不同建模管線） |
| `sz_flat` / `sz_rounded` / `sz_corner_radius` | `strikeZoneInfo.*` | 圓角好球帶模型；2020 起才有 |
| `sz_width_in` / `sz_depth_in` | `strikeZoneInfo.widthInches/depthInches` | 3D 好球帶寬度 / 景深 |
| `sz_edge_distance` | `strikeZoneInfo.edgeDistance` | 球心到好球帶邊緣最短距離；2024 起才有 |
| `sz_is_strike` | `strikeZoneInfo.isStrike` | 模型判定是否好球（可能與裁判不同） |
| `hit_distance` | `hitData.totalDistance` | 擊球飛行距離 |
| `hardness` | `hitData.hardness` | 擊球強度分類（soft / medium / hard） |
| `hit_probability` | `hitData.hitProbability` | 該 EV + LA 的聯盟平均安打機率；僅 MLB |
| `hr_ballparks` | `contextMetrics.homeRunBallparks` | 幾座球場會是全壘打；僅 MLB |
| `bat_speed` / `is_sword_swing` | `hitData.batSpeed/isSwordSwing` | 棒速 / 劍擊揮棒；僅 MLB，2024 部分覆蓋、2025 起全面，未揮棒的球本就無值 |
| `pre_outs` / `outs` | `preCount.outs` / `count.outs` | 投球前 / 後出局數 |
| `pitch_number` | `pitchNumber` | **打席內**第幾球，不是單場累計 |
| `batter_id` / `pitcher_id` | `matchup.batter.id` / `defense.pitcher.id` | 對戰雙方（投手取逐球實際投手） |
| `is_ball` | `details.isBall` | 是否判壞球 |
| `defense` | `defense.*.id` | 投球當下 9 個守位的球員 id |
| `offense` | `offense.*` | 壘上跑者 id、打者守位 |
| `runners[]` | `play.runners[]`（僅打席最後一球） | 每位跑者：`origin_base` / `start_base` / `end_base`、`is_out` / `out_base` / `out_number`、`movement_reason`、`is_scoring_event`、`rbi`、`earned`、`responsible_pitcher_id`（失分責任投手）、`credits[]`（守備功勞 `{player_id, position, credit}`） |
| `pa_final_balls/strikes/outs` | `play.count.*` | 打席**結束當下**的球數 |
| `home_wp` | `play.homeTeamWinProbability` | 打席結束時主隊勝率（%），客隊用 `100 − home_wp` |
| `wpa` | `play.homeTeamWinProbabilityAdded` | 此打席主隊勝率增減（百分點） |
| `leverage_index` / `drama_index` | `play.leverageIndex/dramaIndex` | 局勢緊張度 / 官方精彩程度 |
| `pa_xwoba` | `play.contextMetrics.xWoba` | 此打席的期望 wOBA；僅 MLB |

WP / LI / drama 在逐球層級也有同名節點，但實測恆為 0，所以只在打席最後一球從 play 層級讀取。

**`game_logs.events_json`（牽制 / 離板事件，只寫不讀）**

`playEvents[].type ∈ {pickoff, stepoff}` 的事件，每筆：`type`、`index`、`play_id`、`inning`、投前 / 投後球數與出局數、`result_code` / `result_desc`、`disengagement_num`（該打席第幾次脫離投手板）、`from_catcher`（是否捕手牽制）、`runner_going`（跑者是否起跑）、`is_out`、`pitcher_id` / `batter_id`。

**其他**

- `players.next_game_json.date` / `.status`：模板只用 opponent、is_home、game_time、venue
- 傳入模板但桌機版沒用到的 context：`milb_career` `mlb_career` `next_game_updated_at` `all_stats` `game_logs` `years`

---

## 6. 陷阱與已知疑點

1. **`pitches_per_pa` 鍵名衝突**：`field_maps.apply_advanced_fields` 的 hitting 與 pitching 兩組都把 `pitchesPerPlateAppearance` 寫進同一個 `pitches_per_pa`，有打擊紀錄的投手會被後處理的那組覆蓋。
2. **`players.team` / `level` 會在同函式第二段 `UPDATE` 被覆寫**（`sync/players.py::_write_player_to_db()` 的 level/team UPDATE），upsert 的 SET 子句沒列這兩欄是正常的。Hero 的 `player.team`（現役隊伍）與數據條的 `latest_team_stat.team_name`（當季有出賽的隊伍）意義不同，可能不一致。
3. **逐球 wOBA 與季度計數 wOBA 不會完全一致**：逐球版（Statcast 表、球種表、走勢圖）已比照官方規則 9.02(a)(1) 與 FanGraphs 分母 `AB + BB − IBB + SF + HBP` 排除捕手妨礙；`sac_fly_double_play` / `sac_bunt_double_play` 比照 SF / SH（API 只在記錄員已判定犧牲時才給這兩個事件，推進失敗會標成 `fielders_choice_out` / `double_play` 等並計打數；已逐場對 boxscore `atBats` 驗證）。但逐球版只涵蓋有 play-by-play 的比賽（MiLB 常缺），與季度計數版（wRC+ 用）數字仍可能不同。打席中途因跑者出局、再見暴投或比賽中止而結束的打席（`other_out`、`wild_pitch`、空白 `eventType` 等，清單見 `constants.NON_PA_EVENTS`）不計打席與打數，與 boxscore 一致。
4. **HR/FB% 分母只含 `fly_ball`**：FanGraphs 的 FB 含內野高飛（`IFFB% = IFFB / FB`），本站不含 `popup`，數值會比 FanGraphs 偏高。分子用全部 HR（含平飛球全壘打）與 FanGraphs 一致，不是問題。即使對齊，擊球型態分類來源（MLB `hitData.trajectory` vs. FanGraphs 的 SIS）不同，數字也不會完全相同。
5. **BBE 的 tooltip 寫 `GB+LD+FB+PU`，實際是所有 `is_in_play` 的球**，包含沒有 trajectory 的球；GB% 等比率的分母則是有分類的球，兩者不同。
6. **三位小數比率一律存 float、顯示成 `0.250`**：`win_pct`、`strike_pct`、`p_avg`、`p_obp`、`p_slg`、`p_ops`、`p_sb_pct`、`sb_pct`、`cs_pct`、`fielding_pct` 由 `sync/field_maps.py` / `sync/players.py` 以 `safe_float` 寫入，API 分母為零的佔位字（`.---`、`-.--`）與缺值都存 `None`，樣板一律用 `floatformat(3)`（缺值顯示 `-`）。2026-09 以前寫入的列仍是 API 字串（如 `".640"`、`".---"`），`floatformat` 同樣能解析，重跑一次 `python build.py sync` 後 DB 才會全部變成 float。逐場紀錄（`game_logs.stats_json`）是 API 原始字串照存，顯示時同樣經 `floatformat`。同名的逐球 Strike% 是小數，用 `pct_fmt` 顯示成 `64.0%`。
7. **年度彙總列一律重算**（見 §0），捨入方式與 API 相同。加總時某列有該組數據（打擊或投球）卻缺某一欄，該欄合計為未知並顯示 `-`，而不是當 0 加總：例如 2005 年以前的 MiLB 投球列沒有 `p_tb` / `pitches` / `strikes`，若照舊當 0，曹錦輝 2003 年度合計的被打 SLG 會算成 .150（MLB 單列 .515）（`stats/core/aggregate.py::sum_counting`、`constants.COUNTING_FIELD_GROUPS`）。
8. **Statcast 只寫入同層級的季度列**；同層級季中轉隊時，每一列存的是同一份整季 Statcast，render 時以 (年, 層級) 去重。
9. **MLB 的 WAR / wRC+ / FIP 是整季值，轉隊時該年每一隊的 MLB 列都相同**；render 合併成一列顯示，不會重複。沒有任何地方把各列 WAR 相加。
10. **新增逐球擷取欄位要把 `constants.PBP_EXTRACT_VERSION` 加 1**：`statcast` 只抓 `pbp_version` 落後的比賽，加 1 後每場重抓剛好一次（約 1.6 萬場 withMetrics）。
11. **API 的 K/9、BB/9、H/9、P/IP、AB/HR 已是兩位小數，模板顯示一位**：`floatformat` 以 half-up 顯示（API `9.45` → `9.5`），但真實值若為 9.446，API 先捨成 9.45、再顯示成 9.5，仍會比從計數直接算多 0.1。目前刻意沿用 API 值而不從計數重算。
12. **API 的 `strikePercentage` 只精確到兩位**（488/764 = .6387 回傳 `".640"`），本地算的彙總列是三位（`.639`），同一欄精度不同。
13. **API 自身的平手值不一致**：`homeRunsPer9` 在 27·HR/outs 剛好是 x.xx5 時偶爾捨去（1 HR / 40 outs = .675 → `.67`），`atBatsPerHomeRun` 也有一例（39.625 → `39.62`）；本地算一律進位。只影響本地重算的彙總列。
14. **`rs_per_9` 語意不一致**：API 的 `runsScoredPer9` 實為失分率 RA9（`runs_allowed × 27 / outs`，DB 439/444 列相符），本地備援 `compute_rs_per_9` 用的是 `run_support`。模板未顯示此欄位。
15. **`BATTED_BALL_RATE_DIGITS = 6`**：GB%/LD%/FB%/PU%/Air%/Pull% 等存六位小數，但只經 `pct_fmt`（一位百分比 = 三位小數）顯示，理由未記錄；改動需重跑 statcast 才會反映到 DB。

# 打擊／投球角色分離（二刀流資料正確性）設計

日期：2026-09-25
相關 bug：`docs/bugs/UNFIXED_BUGS.md` #4、#50、#51，以及本文件 §1.2 新發現的逐球資料污染、
§1.3 新發現的打席中換人歸屬錯誤

## 1. 背景

### 1.1 根本原因

`site_builder` 假設「一位球員只有一個角色」，角色由 `players.position` 是否為 `"P"` 決定
（`positions.primary_role()`）。但 MLB API 對同一位球員會同時回傳 `hitting` 與 `pitching`
兩組數據（投手上場打擊、野手登板、真正的二刀流）。兩組寫進同一個位置時，後寫者覆蓋先寫者，
結果取決於 API 回傳順序，而不是規則。

### 1.2 受影響的地方（2026-09-25 本機 DB 實測）

| # | 問題 | 位置 | 實例 |
|---|---|---|---|
| 1 | 同場又投又打，`game_logs.stats_json` 後寫蓋前 | `sync/players.py` gameLog UPSERT | 順序對調比對中 199 場受影響 |
| 2 | `stat_json.gp` 打擊/投球互蓋 | `sync/players.py` yearByYear | 499614 2013 Frisco 打擊 125 場、投球 1 場 |
| 3 | `pitches_per_pa` 打擊/投球互蓋，且被 `annotate_row` 當成打者 P/PA 別名 | `sync/field_maps.py::apply_advanced_fields`、`stats/core/annotate.py` | 806823 2025 ACL Reds 打者 P/PA 顯示投手值 3.878（實際 4.33） |
| 4 | **逐球資料混入另一角色的球** | `sync/statcast.py::_fetch_and_extract_game`（主要角色抽不到就換角色）+ `_compute_player_statcast`（依主要角色整包計算） | 林盛恩（P）84 場、1,437 顆「當打者看到的球」被算進投手 Statcast；林哲瑄（RF）16 場、113 顆投出的球被算進打者 Statcast；另 5 位各 1 場 |
| 5 | 同場又投又打時只存一個角色的逐球資料 | 同上 | — |
| 6 | sabermetrics 只解析主要角色的 group（請求本來就同時取 `pitching,hitting`） | `sync/advanced.py::_fetch_season_saber` | — |
| 7 | expectedStatistics 只抓主要角色的 group | `sync/statcast.py::_compute_player_statcast` | — |
| 8 | wRC+ 跳過 position = P 的球員 | `stats/advanced/wrc_plus.py` | 林盛恩打擊無 wRC+ |
| 9 | MiLB FIP 只算 position = P 的球員 | `sync/advanced.py::sync_season_advanced` | 林哲瑄 MiLB 投球無 FIP |
| 10 | `highest_level_row()` 同層級平手時取決於列的順序 | `stats/core/selectors.py` | 526269 2024 AAA Iowa Cubs / Piratas de Campeche |

因為上述「後蓋前」寫法，`api/stats.py` 目前刻意維持「MLB 一次 + `milb_all` 一次」兩次請求，
不敢改用官方 `leagueListId=mlb_milb` 一次取回。

### 1.3 打席中換人（換投、代打、代跑）的逐球歸屬錯誤（`sync/extract.py`）

原則是**對齊 Baseball Savant 的逐球資料**：每顆球、以及結束打席那一球帶的打席結果，都歸實際投、打那顆球
的人。「每顆球是誰投的」（`defense.pitcher.id`）現行已是如此；以下是現行不符這個原則的地方：

| # | 問題 | 實例 |
|---|---|---|
| 11 | 代跑被當成代打：`was_replaced_mid_pa` / `batter_handoff_idx` 只看換人事件的 `replacedPlayer`，不分代打（`position.code` `"11"`）與代跑（`"12"`） | 高國輝 2006-08-08（44359）在三壘被代跑換下，下一位打者看到的 1 顆球被算成他當打者看的球；打者列 `events_json` 另有 15 場、22 筆別人打席的牽制事件（`events_json` 目前無讀取端） |
| 12 | 換人前的球左右手錯誤：`pitch_hand` / `bat_side` 取自打席層級的 `matchup`（打完的人），換投/代打之前的球記成接手者的左右手 | 打者列 3 個打席、9 顆球投手慣用手錯誤（例：李灝宇 2022-08-24（670515）前 4 球左投記成右投；蔣智賢 2007-06-07（65383）、2014-05-09（387530））；投手列遇到不同打擊慣用手的代打，機制相同（未逐一統計） |
| 13 | 逐球 `batter_id` 取自 `matchup.batter`（打完這個打席的人），代打前的球也記成代打者的 ID | 張育成 2023-04-24（718447）前三球記成 Arroyo 的 624414；本機 DB 共 7 顆（張育成 6、高國輝 1） |

**Savant 的做法（CLAUDE.md 規則 7；2022–2025 逐日掃描 Savant `statcast_search/csv` 查證）**：
- 投手端：換投後的結果一律記給投最後一球的投手。2023-06-28（717579）Ríos 投到 3-0 後換 Pruitt、
  Pruitt 投出第四壞球，Savant 那顆保送球的 `pitcher` 是 Pruitt。
- 打者端：原打者帶兩好球被代打換下、代打者被三振的 12 例中，9 例把三振記給實際揮棒的代打者
  （例：2022-04-21 662593 Duggar → Dubón、2025-09-12 776366 Báez → Sweeney），只有 3 例改記給原打者
  （718447 張育成、717497 Rendon、776218 Fry），看不出規律，無法重現，採多數做法。
- 左右手：逐球 `stand` / `p_throws` 是該球的實際值。2024-04-21（746572）第 56 打席左投換右投，同一位
  左右開弓打者的 `stand` 由 R 變 L；717497 那顆改記給 Rendon（右打）的結束球，`stand` 仍是實際揮棒的
  Escobar 的 L。

**刻意與官方記錄不同（不修，寫進程式註解與 `docs/fields.md`）**：官方 box score 依記錄規則把少數打席結果
記給「沒有投/打最後一球」的人；我們對齊 Savant，不套用：
- 規則 9.15(b)：原打者帶兩好球離場、代打者被三振 → 三振與打數算原打者。例：718447 官方張育成 K 1、
  Arroyo 0 PA，我們記給 Arroyo；郭阜林 2013-05-29（352855）代打時前一位已 2-2，官方 PA 0，我們記一個
  三振打席給他。同型還有張育成 2017-08-15（498235）、林哲瑄 2010-07-20（274053）。
- 規則 9.16(h)：換投當下球數為 2-0、2-1、3-0、3-1、3-2 且最後保送 → 保送算前一位投手
  （[MLB Scoring Changes 說明](https://x.com/ScoringChanges/status/1817373574153576730)）。例：郭泓志
  2006-05-12（46227）、陽耀勳 2014-07-08（386064）的保送官方算他們、我們不算；陳品學 2016-06-29（464383）
  官方 BB 1、我們 2。

影響：逐球算出的 K、BB、AB、wOBA 分母在這類打席和官方 box score 差一筆；季賽計數數據（K%、BB% 等）
來自 API 官方數據，不受影響。

## 2. 目標與範圍

### 2.1 目標

1. DB 中每一筆資料都「角色明確」：不依賴球員的主要角色，也不因寫入/請求順序改變。
2. 兩個角色的原始資料（逐場、逐球）與衍生數據（Statcast、expected、sabermetrics、WAR、
   wRC+、FIP）都正確計算並存進 DB，適用於「該角色有資料」的所有球員，不設門檻、不需名冊標記。
3. 修完後改用 `leagueListId=mlb_milb`（refresh 約 208 → 130 次請求、完整 sync 約 1,940 → 970 次）。
4. 逐球資料在打席中換人時對齊 Savant：每顆球（含結束球帶的打席結果）歸實際投打的人，`batter_id` 與
   左右手為該球的實際值，代跑不再被當成代打（§1.3）。這些修正都在 `extract.py`，逐球資料必須全部重抓；
   與本次從頭重建 DB 一起做，只需重抓一次。

### 2.2 不在範圍內

- **前端顯示邏輯**：球員頁仍只依 `is_pitcher` 顯示主要角色；不新增雙角色分頁或區塊。
  樣板唯一的修改是 §4.4 的 P/PA 變數改名（純改名，畫面不變）。
  兩個角色都有出賽紀錄的球員頁「投手/打者數據切換」另案處理，屆時 `project_role` 的角色參數改為
  「目前檢視的角色」，無條件覆寫的規則不變（§4.1）。
- `positions.py` 的 `TWP` 守位對應：目前名冊沒有 `TWP` 球員，維持現狀。
- `season_stats` 唯一鍵缺 `sport_level`（`docs/bugs/UNFIXED_BUGS.md` #3）：理論上同年同隊名跨兩個層級時
  會互蓋（計數數據後蓋前、`sport_level`/`league_name` 後寫者勝），但 2026-09-25 掃描名冊 103 位球員
  的 yearByYear（MLB + `milb_all`），「同年同隊名、層級或聯盟不同」的 split 為 0 筆，本次不處理。

### 2.3 成功條件

- 同一份 API 資料以任意順序寫入，DB 內容逐筆相同。
- 全新 DB 以「兩次請求」與 `mlb_milb` 各同步一次，兩個 DB 逐筆相同。
- `role = pitcher` 的 `game_logs` 列，逐球資料的 `pitcher_id` 全為本人；`role = batter` 的列，
  `batter_id` 全為本人。
  - 打者端能用 `batter_id` 驗收，是因為 §3.5 把 `batter_id` 改成「這顆球實際的打者」（§1.3 #13）。
    用舊資料跑這個條件會誤判。
- §1.3 每個案例的逐球資料符合 Savant 的做法（清單見 §7 步驟 4）。
- 逐場比對：每位球員每個角色、每場有完整逐球資料的比賽，從逐球算出的 K、HBP、HR 與非故意保送數，
  和該列 `game_logs.stats_json`（gameLog 官方數據）比對。不一致的比賽逐筆歸類，只允許以下原因：
  §1.3 刻意不套用的 9.15(b) / 9.16(h)、自動故意四壞沒有投球、逐球資料缺漏；其他原因視為 bug。
- 重建前後 build 的 HTML，只有「兩個角色都有資料」的球員頁有差異，且差異經抽查合理。

## 3. 資料模型

### 3.1 `game_logs`：每個角色一列

- 新增 `role TEXT NOT NULL`，值為 `positions.PITCHER`（`"pitcher"`）或 `positions.BATTER`（`"batter"`）。
- 唯一鍵改為 `UNIQUE(player_mlb_id, game_id, role)`。
- 一列存在的條件：gameLog API 對該角色有 split。又投又打的比賽是兩列。
- `stats_json`、`pitches_json`、`events_json`、`pbp_version` 都只屬於該列的角色。
- `sport_level`、`pbp_version` 直接寫進 `CREATE TABLE`（目前只存在於 `ALTER TABLE` 遷移）。

### 3.2 `season_stats.stat_json`：打擊/投球共用的 key 全部拆開

一列本來就同時容納兩組數據，不加 `role` 欄位；只把會碰撞的 key 拆開。
慣例沿用既有 `p_hr`、`p_babip`、`p_k_pct`：**打擊不加前綴，投球加 `p_`**。

| 原 key（會碰撞） | 打擊 | 投球 | 來源 |
|---|---|---|---|
| `gp` | `gp` | `p_gp` | yearByYear `gamesPlayed` |
| `statcast` | `statcast`（`compute_batter_statcast`） | `p_statcast`（`compute_pitcher_statcast`） | 逐球資料 |
| `expected` | `expected`（`group=hitting`） | `p_expected`（`group=pitching`） | expectedStatistics |
| `saber` | `saber`（hitting group） | `p_saber`（pitching group） | sabermetrics |
| `war` | `war` | `p_war` | sabermetrics |

**注意**：`statcast`、`expected`、`saber`、`war` 過去在投手列存的是投手的值，改完後固定代表打擊。

**WAR 兩組是不同的值**：sabermetrics API 的 hitting group 與 pitching group 各回自己的 `war`
（大谷翔平 2021：投球 2.96、打擊 5.02；王建民 2008：投球 1.53、打擊 -0.04）。舊 DB 看起來只有一個
WAR，是因為 `_fetch_season_saber` 只解析主要角色那一組、另一組直接丟掉。本設計分開存 `war` / `p_war`，
不另存兩者合計。

只有單一角色會寫的 key 維持原名：投球的 `fip`、`xfip`、`lg_era`、`xwpct`；打擊的 `wrc_plus` 系列。

### 3.3 P/PA 改名（兩個角色都不用前綴，改以分子分母命名）

| 意義 | 公式 | 舊名 | 新名 |
|---|---|---|---|
| 打者每打席看球數 | `pitches_seen / pa` | `p_per_pa`（另有會碰撞的 `pitches_per_pa` 別名） | `pitches_seen_per_pa` |
| 投手每位打者用球數 | `pitches / bf` | `pitches_per_pa` | `pitches_per_bf` |

API `pitchesPerPlateAppearance`：hitting group 寫 `pitches_seen_per_pa`，pitching group 寫
`pitches_per_bf`。舊名全站刪除，不留別名。

### 3.4 `players.team` 平手規則

`highest_level_row()` 排序鍵改為 `(level_rank, -year, -((pa or 0) + (bf or 0)), team_name)`：
同層級先取最近一年，同年再取出賽量較多的隊，最後以隊名決定，保證結果固定。
`load_player_season_rows()` 的排序也加上 `team_name`。

`-year` 不可省略：退役頁把整個生涯傳給 `highest_level_row()` 決定層級標章，目前多年待在同一個最高層級時，
因輸入已依年度新到舊排序，`min()` 取到的是「最近一次」到達。若只用 `-(pa + bf)`，會改成取出賽最多的那年
（本機 DB 模擬：25 位球員的 `badge_year` 會變，例：王建民 2016 Royals → 2006 Yankees）。
`badge_year` 決定 `level_display()` 的年代名稱，最高層級橫跨 2021 改制的球員（例：2019 `A(Adv)`、
2021 `A+`）標章就會變。`sync/players.py` 只傳最近一季的列，`-year` 對它沒有影響；同年同層級的平手
（526269 2024 AAA Iowa Cubs / Piratas de Campeche）仍由出賽量決定。

### 3.5 逐球資料（`pitches_json`）欄位：一律歸實際投打的人（對齊 Savant）

| 欄位 | 語意 | 變更 |
|---|---|---|
| `pitcher_id` | 這顆球實際的投手（`playEvents[].defense.pitcher.id`，缺值退回 `matchup.pitcher.id`） | 不變 |
| `batter_id` | 這顆球實際的打者（§4.6 步驟 1） | 原為 `matchup.batter.id` |
| `pitch_hand` | 實際投手這顆球的投球手（§4.6 步驟 2） | 原為 `matchup.pitchHand.code` |
| `bat_side` | 實際打者這顆球的打擊邊（§4.6 步驟 2） | 原為 `matchup.batSide.code` |
| `at_bat_index` | `allPlays[].atBatIndex`，打席邊界 | **新增** |
| `is_pa_final`、`pa_event`、`pa_event_desc`、`runners`、`_pa_context()` 的欄位 | 打席實際的最後一球與打席結果，記在投/打這顆球的人身上 | 不變 |

打席中換人時，被換下的人只有自己那段球、沒有 `is_pa_final`；結果隨最後一球記給接手的人（§1.3 的
Savant 多數做法）。例：718447 張育成有第 1–3 球、無結果；Arroyo 有第 4–6 球，第 6 球帶 `strikeout`
（這場剛好是 Savant 改記給原打者的 3 個例外之一，我們照多數做法，不跟這個例外）。
717579 Ríos 有前 3 顆壞球、無結果；Pruitt 的第四壞球帶 `walk`。

`at_bat_index` 的用途：打席切分（`iter_plate_appearances`）改用它，不再依賴「遇到 `is_pa_final` 才切」。
被換下的人那段沒有 `is_pa_final` 的球，現在只因為他通常不會再上場才沒出錯；投手先改守其他位置、同場再
回來投球時（規則允許），那段球就會併進他下一個打席。

## 4. 元件設計

### 4.1 `positions.py`（角色的單一來源）

新增：

- `role_for_stat_group(group_name) -> Optional[str]`：`"hitting"` → `BATTER`、`"pitching"` → `PITCHER`，
  其他（如 `fielding`）→ `None`。
- `role_field(role, name) -> str`：`BATTER` 回 `name`，`PITCHER` 回 `"p_" + name`。§3.2 所有拆分 key 都經過它。
- `ROLE_SPLIT_FIELDS = ("gp", "statcast", "expected", "saber", "war")`。
- `project_role(row, role)`：`role == PITCHER` 時，把 `ROLE_SPLIT_FIELDS` 每個 `p_<name>` 的值放到 `<name>`；
  `BATTER` 不做事。只給 render 層用（§4.4）。
  **必須無條件覆寫**（`row[name] = row.get("p_" + name)`，缺值就是 None），不可只在 `p_<name>` 有值時才搬：
  否則投手檢視會拿到打擊的值。例：林盛恩 2024 ACL Reds 只打擊（`gp` 49、`pa` 215、無投球），拆開後
  `gp = 49`、`p_gp = None`；有值才搬的話投手頁該年 G 顯示 49、生涯出賽數也會加進打擊場次，
  無條件覆寫後 G 為「-」。

### 4.2 `stats/core/selectors.py`

- 新增 `appeared_roles(row) -> set[str]`：`pa > 0` → `BATTER`；`bf > 0` 或 `ip_to_outs(ip) > 0` → `PITCHER`。
  衍生數據「這個角色要不要算」的唯一判斷。
- `highest_level_row()` 平手規則見 §3.4。

### 4.3 寫入端

**`sync/players.py::_write_player_to_db`**
- yearByYear：hitting 寫 `gp`、pitching 寫 `p_gp`（經 `role_field`）。
- gameLog：以 `role_for_stat_group(log_group.group.displayName)` 決定 `role`，`ON CONFLICT(player_mlb_id, game_id, role)`。
- `players.team`：沿用 `highest_level_row()`（§3.4 已穩定）。

**`sync/field_maps.py`**：`apply_advanced_fields` 依 §3.3 改寫 P/PA 的目標 key。

**`sync/statcast.py`**
- Phase 1 `_games_to_fetch`：以 `(game_id, player_mlb_id, role)` 挑出 `pbp_version` 落後的列，
  回 `{game_pk: [(mlb_id, role), ...]}`，不再需要 `positions`。
- Phase 2 `_fetch_and_extract_game`：每場 live feed 抓一次，依列的 `role` 呼叫 `extract_pitch_logs()`；
  **刪除換角色重抽的備援**。`FetchedGame.pitches/events` 以 `(mlb_id, role)` 為鍵。
- Phase 3 `_write_pitch_logs`：`WHERE player_mlb_id=? AND game_id=? AND role=?`。
- 聚合 `_compute_player_statcast`：對每個角色呼叫 `load_all_pitches_for_player(cur, mlb_id, role)`，
  有逐球資料的角色各自計算；expectedStatistics 依角色帶 `group`，只查該角色有 MLB 逐球資料的年份。
- `_attach_statcast`：寫入 `role_field(role, "statcast")` 與 `role_field(role, "expected")`。
- `season_fetches` 登記依角色分開：source `EXPECTED_STATS`（打擊）與新增的 `P_EXPECTED_STATS`（投球）。

**`db/game_logs.py::load_all_pitches_for_player`**：新增必填 `role` 參數，SQL 加 `AND role = ?`。

**`sync/advanced.py`**
- `_fetch_season_saber` 不再帶 `is_pitcher`，回 `{role: stat}`（兩個 group 都解析；請求數不變）。
- 每列依 `appeared_roles(row)` 決定寫哪些角色：
  - 打擊：`saber`、`war`、`wrc_plus`（MLB 列；`wrc_plus` 為 API `wRcPlus` 四捨五入，沿用現行邏輯）。
    `wrc_plus` 不可漏：樣板（`tab_advanced.j2`、`m_advanced.j2`）先讀 `wrc_plus`、沒有才退回自算的
    `wrc_plus_calc`，漏寫不會報錯，而是悄悄改顯示自算值（例：張育成 2021 Cleveland 現為 API 值 87）。
  - 投球：`p_saber`、`p_war`、`fip`、`xfip`、`lg_era`、`xwpct`（MLB 列）；MiLB 列的 FIP 也改由「該列有投球」決定。
- 聯盟常數 `prefetch` 的條件同樣改為「該列有投球」。
- 不再需要 `positions` 參數；`build.py`／呼叫端同步調整。

**`stats/advanced/wrc_plus.py`**：刪除 `is_pitcher_position` 跳過判斷，改為該列有打擊 PA 就計算。

**`stats/core/annotate.py`**：刪除 `p_per_pa ← pitches_per_pa` 別名；打者 `pitches_seen_per_pa`
缺值時以 `pitches_seen / pa` 補算，投手 `pitches_per_bf` 缺值時以 `pitches / bf` 補算。

**`api/stats.py`**：`MLB_AND_MILB` 改為單次 `mlb_milb`，刪除「刻意維持兩次請求」的註解。
（實作時先查證 `docs/api/api_endpoint.md` 中 `mlb_milb` 的用法。）

### 4.4 讀取端（render；樣板除 P/PA 改名外不改）

- **`db/bundles.py`**：`game_logs` 查詢加 `AND role = ?`（`primary_role(player.position)`）。
  逐場表、`graph/season_trend.py` 走勢圖、`render/pages.py` 的池化「合計」Statcast 因此只看主要角色。
- **`render/pages.py`**：載入 season rows 後、`annotate_computed_stats` 與 `_merge_level_rows` 之前，
  對每列呼叫 `project_role(row, primary_role(player.position))`。其後的合併、生涯加總、樣板都照舊讀不帶前綴的 key。
- **樣板**：`tab_advanced.j2`（4 處）、`m_advanced.j2`（2 處）的 P/PA 儲存格改讀
  `pitches_seen_per_pa`（打者）／`pitches_per_bf`（投手）。表頭文字、tooltip、格式不變；
  已確認 `src/` 與 `render/` 沒有其他讀取點。

### 4.5 資料流總覽

```
API hitting split ──role_for_stat_group──▶ game_logs(role=batter)  ──extract(batter)──▶ pitches_json
API pitching split ─role_for_stat_group──▶ game_logs(role=pitcher) ──extract(pitcher)─▶ pitches_json
                                                   │
      load_all_pitches_for_player(role) ◀──────────┘
                 │
     compute_{batter,pitcher}_statcast ──role_field──▶ season_stats.stat_json{statcast | p_statcast}
                                                   │
  render: project_role(row, primary_role) ◀────────┘ ──▶ 樣板（不帶前綴的 key）
```

### 4.6 `sync/extract.py::extract_pitch_logs`：打席中換人的歸屬

簽名不變（`game_data, player_id, role`）。每個打席（`allPlays[]`）依序處理：

1. **逐事件標出實際投手與實際打者**（取代現行 `was_replaced_mid_pa` / `batter_takeover_idx` /
   `batter_handoff_idx`）：
   - 實際投手：投球事件用 `defense.pitcher.id`，缺值退回 `matchup.pitcher.id`（現行邏輯）。
   - 實際打者：只把 `details.eventType == "offensive_substitution"` **且** `position.code == "11"`
     （Pinch Hitter）視為換打者（修 §1.3 #11）。打席開始的打者 = 第一個代打事件的 `replacedPlayer.id`，
     沒有代打事件時為 `matchup.batter.id`；每遇到一個代打事件，之後的打者換成該事件的 `player.id`。
     代跑（`"12"`）與其他換人一律不影響打者。2026-09-25 抽樣 2002–2026 共 195 場，
     `offensive_substitution` 事件全部帶 `position.code`；缺值時視為非代打並記 `logger.warning`。
2. **左右手**（修 §1.3 #12）：資料來源 `gameData.players["ID<id>"].pitchHand.code / batSide.code`
   （抽樣 195 場、9,780 位球員 100% 有值）。
   - `pitch_hand`：實際投手 = `matchup.pitcher` 時取 `matchup.pitchHand.code`（保留左右開弓投手每個打席的
     實際投球手）；否則取該投手的 `pitchHand.code`，值為 `"S"` 或缺值時存 `""`（不進 L/R 分項，只進合計）。
   - `bat_side`：實際打者與實際投手都等於 `matchup` 時取 `matchup.batSide.code`；否則取該打者的
     `batSide.code`。左右開弓（`"S"`）時取這顆球 `pitch_hand` 的反邊（L → R、R → L）；`pitch_hand`
     為 `""` 時存 `""`。依據：Savant 746572 第 56 打席，左投換右投後同一打者 `stand` 由 R 變 L。
3. **依 `role` 取球**：`PITCHER` 取實際投手為本人的球；`BATTER` 取實際打者為本人的球。本人在這個打席
   沒有任何一顆球時整個打席略過。
4. **打席結果**：維持現行，`is_pa_final` 與 `pa_event` 等欄位只在打席實際最後一球；那顆球屬於誰
   （步驟 3），結果就在誰的資料裡。程式註解寫明這是對齊 Savant、刻意不套用官方記錄規則 9.15(b) / 9.16(h)
   （§1.3）。
5. **非投球事件（pickoff / stepoff）**：`PITCHER` 只收實際投手為本人的事件（事件的
   `defense.pitcher.id`，缺值退回 `matchup.pitcher.id`）；`BATTER` 只收事件發生時實際打者為本人的事件。
   `_condense_nonpitch_event()` 的 `pitcher_id` / `batter_id` 改寫實際值。
6. 每顆球新增 `at_bat_index`；`batter_id` / `pitch_hand` / `bat_side` 改用步驟 1、2 的實際值
   （修 §1.3 #13）。

換人判斷拆成模組內的私有函式（例：`_actual_participants(play)`、`_hand_for_pitch(...)`），各有單元測試
（§6）；`docs/functions_list.md` 同步更新。

**`constants.PBP_EXTRACT_VERSION`**：1 → 2（逐球欄位語意改變；本次從頭重建，版本號用於日後判斷）。

### 4.7 逐球資料的下游

- `stats/core/pitches.py::iter_plate_appearances`：打席邊界改為 `(game_pk, at_bat_index)` 變化，
  不再看 `is_pa_final`（理由見 §3.5）。docstring 同步改寫。
- 其餘讀取端（`aggregate_pitches` 的 `pa_final`、`pa_outcomes`、HR/FB、put-away、犧牲短打判定、Plinko、
  逐球紀錄頁）的欄位語意不變，不需修改。
- 讀 `bat_side` / `pitch_hand` 的左右分項（`tables/bat_side_splits.py`、`tables/vs_pitch_types.py`
  的 pitch hand 分項、`batted_ball/spray.py`）程式不變，改由正確的逐球值自動修正。

## 5. 錯誤處理與遷移

- **不做既有 DB 遷移，改為刪除 DB 後從頭重建**：`python build.py all`（sync → statcast → build，自動帶 `--full-history`）。
  需要重抓約 1.5 萬場逐球資料，耗時較長；重建完成後由使用者將新 DB 上傳 Google Drive 取代舊檔。
- **舊 DB 防呆**：`init_db()` 若發現既有 `game_logs` 沒有 `role` 欄位，直接 raise 並提示需重建，
  避免 CI 用舊 DB 靜默寫出錯誤資料。這是結構檢查，不是回補（符合 CLAUDE.md 規則 2）。
- 因為是全新 DB，不需要清除舊 key 的邏輯。
- `PBP_EXTRACT_VERSION` 1 → 2（§4.6）：全新 DB 本來就會抓每一場，版本號是為了讓日後任何沿用舊逐球資料的
  DB 都會重抓。

## 6. 測試

新增/修改於 `tests/`：

1. **與順序無關**：同一份 API bundle 以正序與反序各寫入一個 in-memory DB，斷言 `players`、`season_stats`、
   `game_logs` 完全相同（鎖住 #51）。
2. 同一場又投又打 → 兩列，`stats_json` 各為對應 group。
3. yearByYear：`gp` / `p_gp`、`pitches_seen_per_pa` / `pitches_per_bf` 各自正確。
4. statcast：依列的 role 抽取、沒有備援；`load_all_pitches_for_player` 依 role 過濾；`_attach_statcast` 寫到正確 key。
5. `positions`：`role_for_stat_group`、`role_field`、`project_role`（含 `p_<name>` 缺值時覆寫成 None）。
6. `selectors`：`appeared_roles`；`highest_level_row` 平手在列順序對調時結果相同；
   多年同層級時取最近一年（退役頁標章語意不變）。
7. advanced：兩個 group 都解析；`war` / `p_war` 各為對應 group 的值；MLB 打者列仍寫入 `wrc_plus`；
   非 P 球員 MiLB 投球列有 FIP；P 球員打擊有 wRC+。
8. `annotate_row`：同時有打擊與投球的列，打者 P/PA 不會拿到投手值。
9. `extract_pitch_logs` 打席中換人（§4.6）。fixture 從真實 `/game/{pk}/withMetrics` 裁出該打席，
   存到 `tests/fixtures/`，預期值依 Savant 的做法寫出：
   - 代打（兩好球被換下）：718447 張育成只有第 1–3 球、無 `is_pa_final`；Arroyo 有第 4–6 球，第 6 球
     `pa_event = "strikeout"`。每顆球的 `batter_id` 是實際打者。另加 662593 Duggar → Dubón（Savant
     多數做法的實例）作為同型對照。
   - 代打（非兩好球）：275960 唐肇廷（3-2 代打後保送）、224862 蔣智賢（1 好球離場，代打者三振）。
   - 換投保送：717579 Ríos 只有前 3 球、無結果；Pruitt 的第四壞球帶 `walk`。
   - 換投非保送：760110 張弘稜（2-1 下場，接手投手三振）。
   - 代跑：44359 高國輝，該打席沒有任何一顆球、也沒有非投球事件歸給他。
   - 左右手：670515 李灝宇前 4 球 `pitch_hand = "L"`；746572 第 56 打席左右開弓打者換投後 `bat_side`
     R → L；717497 Rendon 被代打換下後，Escobar 那顆結束球 `bat_side = "L"`。
   - `at_bat_index` 為 `allPlays[].atBatIndex`。
10. 下游（§4.7）：`iter_plate_appearances` 以 `(game_pk, at_bat_index)` 切分；同一球員同場兩段不同打席
    的球，即使前一段沒有 `is_pa_final`，也不會被併成一個打席。

## 7. 驗收（實際執行）

1. `python -m pytest tests/` 全數通過。
2. 重建前先以舊 DB build 一份 HTML 留存。
3. 全新 DB 分別以「兩次請求」與 `mlb_milb` 同步（sync），逐表比對應完全相同。
4. `python build.py all` 重建後：
   - DB 查詢確認 §2.3 的逐球角色一致性（違反數 0）。
   - §1.3 案例逐一查 DB：高國輝 44359 沒有別人打席的球與事件；李灝宇 670515、蔣智賢 65383 / 387530
     的 `pitch_hand` 正確；張育成 718447 前三球的 `batter_id` 是本人且無打席結果。
   - 執行 §2.3 的逐場比對（逐球 K / HBP / HR / 非故意保送 vs `game_logs.stats_json`），不一致逐筆歸類。
   - build HTML 與步驟 2 逐檔比對（扣除時間戳），差異只出現在兩角色都有資料的球員，逐一抽查
     （至少林盛恩、林哲瑄、蔣智賢、王建民）。

## 8. 文件更新

- `docs/functions_list.md`：新增/改簽名的函式（`positions`、`selectors`、`load_all_pitches_for_player`、
  statcast/advanced 內部函式、`extract.py` 新增的私有函式、`iter_plate_appearances` 的邊界改變）。
- `docs/db_schema.md`：`game_logs.role` 與新唯一鍵、`stat_json` 新 key、`pitches_json` 新欄位
  `at_bat_index` 與 `batter_id` / `pitch_hand` / `bat_side` 語意改變、
  `PBP_EXTRACT_VERSION` 2；§8 記錄本次需從頭重建。
- `docs/fields.md`：§3.2、§3.3 所有新 key 與改名，說明 P/PA 命名理由與 `p_` 前綴慣例；§3.5 逐球欄位語意、
  對齊 Savant 的歸屬原則，以及刻意不套用官方記錄規則 9.15(b) / 9.16(h) 造成的差異。
- `docs/data_sources.md`：gameLog/sabermetrics/expectedStatistics 依 group 寫入的位置、`mlb_milb`；
  withMetrics 新用到的路徑：`allPlays[].atBatIndex`、`playEvents[].position.code`（換人事件）、
  `gameData.players["ID<id>"].pitchHand.code / batSide.code`。
- `docs/bugs/UNFIXED_BUGS.md`：#4、#50、#51 移至附錄 A，並記錄 §1.2 #4 逐球污染、§1.3 #11–#13 的發現與修正、9.15(b) / 9.16(h) 刻意不套用的決定。
- `CLAUDE.md`：`positions.py` 權威表描述補上「角色欄位命名（`role_field`）」。

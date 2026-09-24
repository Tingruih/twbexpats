# SQLite 資料庫 Schema 參考

> 最後核對：2026-09-23
>
> 範圍：`site_builder/db/schema.py::init_db()` 建立的全部 9 個 table，逐欄核對
> 型別、NOT NULL/DEFAULT、UNIQUE/索引，以及每個 JSON 字串欄位內部實際會出現
> 哪些 key。所有欄位清單都對照 `schema.py` 原始碼與實際寫入程式逐一核對過。

這份文件回答「這張表有哪些欄位、JSON 裡有哪些 key、誰寫誰讀」，不用下 SQL 或翻原始碼就能理解 `data/tracker.sqlite3` 的完整結構。

- 逐球欄位（`pitches_json`/`events_json`）完整清單 → `docs/withmetrics_field_reference.md` §8.1、§8.3
- 每個統計欄位的 API 端點來源與計算公式 → `docs/fields.md`
- 每個讀寫這些表的函式在原始碼裡的定位 → `docs/functions_list.md`（本文件只點名函式，細節見該文件）

分層對照 `CLAUDE.md` 的架構：`db/` 只管 schema 與單純 row access（不打外部
API、不算統計）；`sync/` 負責寫入；`stats/`+`render/` 負責讀取後計算/渲染；
`league_constant/` 是唯一同時抓外部資料又寫自己快取表的層。

## 目錄

0. [總覽：9 個 table 一覽](#0-總覽9-個-table-一覽)
1. [players](#1-players)
2. [season_stats](#2-season_stats)
3. [game_logs](#3-game_logs)
4. [playbyplay_processed](#4-playbyplay_processed)
5. [league_constant 快取表](#5-league_constant-快取表)
6. [play_videos / game_content_processed](#6-play_videos--game_content_processed)
7. [表格間的邏輯關聯](#7-表格間的邏輯關聯)
8. [Schema 演進備註](#8-schema-演進備註)

---

## 0. 總覽：9 個 table 一覽

| Table | 用途 | 主鍵/唯一鍵 |
|---|---|---|
| `players` | 球員基本資料 + 最新一筆下一場賽事快取 | `mlb_id` UNIQUE |
| `season_stats` | 每個 `(球員,年,球隊)` 一列的球季數據（含 Statcast 彙整） | `(player_mlb_id, year, team_name)` UNIQUE |
| `game_logs` | 逐場數據 + 逐球/逐事件快取 | `(player_mlb_id, game_id)` UNIQUE |
| `playbyplay_processed` | 標記哪些比賽已抓過 playByPlay | `game_pk` PK |
| `tjstats_park_factors` | tjstats.ca 球場因子快取 | `(year, level, team_name)` UNIQUE |
| `tjstats_league_constants` | tjstats.ca 聯盟 wOBA/R-PA 常數快取 | `(year, level_code, league)` UNIQUE |
| `league_fip_constants` | 自算 MiLB FIP 常數 + 整層 lgERA 快取 | `(year, sport_level, league_name)` UNIQUE |
| `play_videos` | 單一 play 的 highlight mp4 URL 快取 | `(game_pk, play_id)` UNIQUE |
| `game_content_processed` | 標記哪些比賽的 `/content` 已抓過 | `game_pk` PK |

---

## 1. `players`

| 欄位 | 型別 | Nullable/Default | 說明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | 內部 rowid |
| `mlb_id` | INTEGER | NOT NULL UNIQUE | MLB Stats API 球員 ID，全站主要查找鍵 |
| `name_en` | TEXT | NOT NULL | 英文姓名 |
| `name_tw` | TEXT | DEFAULT `''` | 中文姓名（來自 `roster.json`，非 API） |
| `team` | TEXT | DEFAULT `'N/A'` | 見 §8 備註：寫入後不會被 UPDATE 覆蓋 |
| `level` | TEXT | DEFAULT `'Minors'` | 同上，寫入後不會被 UPDATE 覆蓋 |
| `position` | TEXT | DEFAULT `''` | 守備位置縮寫 |
| `height` | TEXT | DEFAULT `''` | 原始身高字串（如 `6' 2"`） |
| `weight` | INTEGER | nullable | 磅 |
| `birth_date` | TEXT | nullable | ISO 日期字串 |
| `birth_city` / `birth_country` | TEXT | DEFAULT `''` | |
| `is_active` | INTEGER | DEFAULT `1` | API 的 `active` flag；**不等於**站台 `/` vs `/retired` 的判定（那個由 `roster.py::is_active_player()` 另外用 `season_stats`+交易紀錄判斷，不讀這個欄位） |
| `bat_side` / `pitch_hand` | TEXT | DEFAULT `''` | |
| `latest_transaction` | TEXT | DEFAULT `''` | 最新一筆交易描述 |
| `roster_status` | TEXT | DEFAULT `''` | `rosterEntries[0].status` 顯示字串 |
| `roster_status_code` | TEXT | DEFAULT `''` | 同上的代碼版，供 `roster.py::categorize_roster_status()` 分類 |
| `roster_is_active` | INTEGER | DEFAULT `0` | |
| `team_id` | INTEGER | nullable | 目前球隊 MLB team ID |
| `transactions_json` | TEXT | DEFAULT `'[]'` | JSON list，見下 |
| `next_game_json` | TEXT | DEFAULT `'{}'` | JSON dict，見下 |
| `next_game_updated_at` | TEXT | nullable | 上次抓下一場賽事的 ISO 時間戳 |
| `next_game_for_season` | INTEGER | nullable | 該筆 `next_game_json` 對應的賽季年份 |

無額外索引（`mlb_id` 的 UNIQUE 本身自帶索引）。

**`transactions_json`**（list，每筆物件）：

| key | 說明 |
|---|---|
| `date` | 交易生效日 |
| `type` | 交易類型描述 |
| `description` | 交易文字描述 |

來源：`api/players.py::get_player_profile()`。

**`next_game_json`**（dict，無下一場賽事時為 `{}`）：

| key | 說明 |
|---|---|
| `date` | 比賽日期 |
| `opponent` | 對手球隊名 |
| `is_home` | 是否主場 |
| `venue` | 球場名 |
| `game_time` | 已轉 UTC+8 的顯示字串 |
| `status` | 賽事詳細狀態 |

來源：`api/schedule.py::get_next_game()`（查未來 7 天內第一場 `Preview` 狀態比賽）。

**誰寫**：`sync/players.py::_write_player_to_db()`（player 主欄位 UPSERT + `next_game_json` 獨立 UPDATE）。
**誰讀**：`db/bundles.py::load_player_bundle()`（渲染用）、`db/players.py::warn_orphaned_players()` / `get_cached_is_active()`（sync 管線用）。

---

## 2. `season_stats`

| 欄位 | 型別 | Nullable/Default | 說明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | |
| `player_mlb_id` | INTEGER | NOT NULL | 邏輯上對應 `players.mlb_id` |
| `year` | INTEGER | NOT NULL | 賽季年 |
| `team_name` | TEXT | NOT NULL | 該列所屬球隊（同年跨隊會有多列） |
| `league_name` | TEXT | DEFAULT `''` | 所屬聯盟名（MiLB 用於配對 FIP/wOBA 常數） |
| `sport_level` | TEXT | DEFAULT `''` | canonical tier code（`MLB`/`AAA`/… ，見 `levels.py`） |
| `stat_json` | TEXT | DEFAULT `'{}'` | 打擊/投球數據，見下 |
| `fielding_json` | TEXT | DEFAULT `'[]'` | 守備數據，見下 |

索引：UNIQUE `(player_mlb_id, year, team_name)`；`idx_season_stats_player_year ON (player_mlb_id, year)`。

### `stat_json`

這是全庫最複雜的欄位，內容分兩層寫入：

**第一層（`sync/players.py::_write_player_to_db()` 寫入，來自 yearByYear + seasonAdvanced 端點）**：

- `gp`：只從 hitting/pitching 分組寫入（fielding 分組的 `gamesPlayed` 是逐位置的，故意不寫進來蓋掉總數）
- 打擊/投球欄位由 `sync/field_maps.py::apply_yearbyyear_fields()` / `apply_advanced_fields()` 決定 key 名稱（如 `era`/`whip`/`ip`/`so`/`avg`/`obp`/…），**完整欄位對照表見 `docs/data_sources.md` §2.1、§2.2、§3.1、§3.2**，這裡不重複列。

**第二層（`sync/statcast.py::_merge_statcast_into_season()` 在 statcast 管線另外合併進同一個 dict，只寫入 `sport_level` 相符的那一列）**：

| key | 型別 | 說明 |
|---|---|---|
| `statcast` | dict | `stats/pitcher_statcast.py::compute_pitcher_statcast()` 或 `stats/batter_statcast.py::compute_batter_statcast()` 的完整回傳值（`pitch_arsenal`/`pitch_outcomes`/discipline/batted-ball 等，key 清單見 `docs/functions_list.md` §3.8） |
| `saber` | dict | 僅 MLB。`api/stats.py::get_player_sabermetrics()` 的原始回傳（含 `fip`/`xfip`/`war`/`wRcPlus`） |
| `expected` | dict | 僅 MLB。`api/stats.py::get_player_expected_stats()` 的原始回傳（`avg`/`slg`/`woba`/`wobaCon`） |
| `fip` | float | MiLB 由 `stats/advanced/fip.py::compute_fip()` 自算；MLB 直接取自 `saber.fip`（四捨五入到小數 2 位） |
| `lg_era` | float | 該 `(sport_level, year)` 整層平均自責分，`xwpct` 的分母來源 |
| `xwpct` | float | `stats/advanced/xwpct.py::compute_xwpct(fip, lg_era)` |
| `xfip` | float | 僅 MLB，直接取自 `saber.xfip` |
| `war` | float | 直接取自 `saber.war` |
| `wrc_plus` | int | 僅 MLB。整季合計值，**只寫入該年度第一筆 MLB 列**（避免轉隊球員每支球隊都顯示一次） |

> ⚠️ 網站上另外顯示的「TJBat+ 自算 wRC+」（`wrc_plus_calc`）**不在資料庫裡**——
> 它是每次 `build` 時由 `stats/advanced/wrc_plus.py::annotate_wrc_plus()` 即時算出、
> 只存在於 render 期間的記憶體物件，不會寫回 `stat_json`（見 `docs/data_sources.md` §3.6）。

### `fielding_json`（list，每個守備位置一筆，依 `position` 去重覆蓋）

| key | 說明 |
|---|---|
| `position` | 守備位置縮寫，list 內去重鍵 |
| `gp`/`gs` | 出賽/先發場數 |
| `innings` | 守備局數 |
| `assists`/`putouts`/`errors`/`chances` | 助殺/刺殺/失誤/守備機會 |
| `fielding_pct` | 守備率（字串，API 已算好） |
| `dp`/`tp` | 雙殺/三殺參與數 |
| `throwing_errors` | 傳球失誤 |
| `range_factor_game`/`range_factor_9` | 守備範圍值 |

**誰寫**：`sync/players.py::_write_player_to_db()`（基礎欄位）、`sync/statcast.py::_merge_statcast_into_season()`（Statcast/進階欄位）。
**誰讀**：`db/bundles.py::load_player_bundle()`——讀出後把 `stat_json` 整包 `dict.update()` 攤平進同一個列物件（跟 `year`/`team_name`/`sport_level` 平級），不是巢狀存取。

---

## 3. `game_logs`

| 欄位 | 型別 | Nullable/Default | 說明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | |
| `player_mlb_id` | INTEGER | NOT NULL | |
| `date` | TEXT | NOT NULL | 比賽日期 |
| `game_id` | INTEGER | NOT NULL | 即 MLB `game_pk` |
| `opponent` | TEXT | NOT NULL | |
| `is_home` | INTEGER | nullable | |
| `game_type` | TEXT | NOT NULL | `R`=例行賽，`F`/`D`/`L`/`W`=季後賽各輪（見 `constants.py::GAME_LOG_GAME_TYPES`；其餘 API 回傳的 game type 一律不寫入） |
| `stats_json` | TEXT | DEFAULT `'{}'` | 該場 gameLog 數據，原封存 API 回傳，欄位命名同 `season_stats` 的 yearByYear 欄位（見 `docs/data_sources.md` §5） |
| `pitches_json` | TEXT | DEFAULT `'[]'` | 逐球資料，見下 |
| `events_json` | TEXT | DEFAULT `'[]'` | 逐非投球事件，見下 |
| `sport_level` | TEXT | DEFAULT `''` | canonical tier code；**注意：這欄不在原始 `CREATE TABLE` 裡，見 §8** |
| `hit_coord_checked` | INTEGER | DEFAULT `0` | 是否已嘗試過 hit-coordinate 回補（見 §8） |

索引：UNIQUE `(player_mlb_id, game_id)`；`idx_game_logs_player_date ON (player_mlb_id, date)`。

**`pitches_json`**（list，每球一筆 dict）：完整欄位來源對照表見
`docs/withmetrics_field_reference.md` §8.1（例如 `pitch_type`/`start_speed`/`ivb`/`hb`/
`zone`/`ev`/`la`/`is_pa_final`/`runners`/`pa_xwoba`/`sz_*` 等數十個欄位）。
擷取函式：`sync/extract.py::extract_pitch_logs()`。

**`events_json`**（list，僅 `pickoff`/`stepoff` 兩種事件）：欄位清單見同一份文件
§8.1 末段（`type`/`index`/`play_id`/`inning`/`pre_*`/`balls`/`strikes`/`outs`/
`result_code`/`result_desc`/`disengagement_num`/`from_catcher`/`runner_going`/
`is_out`/`pitcher_id`/`batter_id`）。**目前只被寫入，程式沒有任何讀取消費端**
（保留給未來的單場報告功能，見 `docs/data_sources.md` §10.2 的設計構想）。

**誰寫**：
- `sync/players.py::_write_player_to_db()`：`date`/`opponent`/`is_home`/`game_type`/`stats_json`/`sport_level` 初值（yearByYear gameLog 階段）
- `sync/statcast.py`：`pitches_json`/`events_json`/`sport_level`/`hit_coord_checked`（playByPlay 階段，`_fetch_and_extract_game()` 抓、寫入邏輯在 `sync_statcast()` 內）

**誰讀**：
- `db/bundles.py::load_player_bundle()`（渲染用逐場列表，`events_json` 不讀）
- `db/game_logs.py::load_all_pitches_for_player()`（統計計算用，只讀 `game_type='R'`（例行賽）的 `pitches_json`，依 `sport_level` 分組；跨層級 Statcast 合併靠這個函式取原始球）
- `db/play_videos.py::content_fetch_candidates()`（JOIN `game_id` 找需要補抓 highlight 影片的比賽）

---

## 4. `playbyplay_processed`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `game_pk` | INTEGER | PK，即 MLB `game_pk` |
| `processed_at` | TEXT | NOT NULL，處理時間戳（ISO） |

用途：標記「這場比賽已經嘗試抓過 playByPlay」，讓 `sync_statcast()` 不會對本來就沒有逐球資料的比賽（例如太舊或低層級賽事）每次都重新嘗試抓取；判斷「未處理清單」時同時要看 `game_logs.pitches_json` 是否為空**且** `game_pk` 不在這張表裡。

**誰寫/讀**：`sync/statcast.py::sync_statcast()`（唯一存取點）。

---

## 5. `league_constant` 快取表

三張表都由 `site_builder/league_constant/` 依 `RefreshPolicy`（見 `league_constant/policy.py`）決定何時重抓，`db/` 本身不碰這幾張表。

### 5.1 `tjstats_park_factors`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `year` | INTEGER | NOT NULL |
| `level` | TEXT | NOT NULL，TJStats 自己的層級拼法（見 `api/tjstats.py::TJSTATS_LEVEL_PARAMS`） |
| `team_name` | TEXT | NOT NULL |
| `pf_final` | REAL | NOT NULL，最終球場因子 |
| `league` | TEXT | NOT NULL，該隊所屬聯盟 |

UNIQUE `(year, level, team_name)`。來源：`api/tjstats.py::fetch_park_factors()`。
誰寫/讀：`league_constant/batting.py::_load_park_factors()` / `_save_park_factors()`。

### 5.2 `tjstats_league_constants`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `year` | INTEGER | NOT NULL |
| `level_code` | TEXT | NOT NULL |
| `league` | TEXT | NOT NULL |
| `lg_woba` | REAL | NOT NULL，聯盟平均 wOBA |
| `lg_r_pa` | REAL | NOT NULL，聯盟平均每打席得分 |

UNIQUE `(year, level_code, league)`。來源：`api/tjstats.py::fetch_league_constants()`。
誰寫/讀：`league_constant/batting.py::_load_league_constants()` / `_save_league_constants()`；
再由 `_join()` 跟 park factors 合併成 `BattingConstant`，供 `stats/advanced/wrc_plus.py` 用。

### 5.3 `league_fip_constants`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `year` | INTEGER | NOT NULL |
| `sport_level` | TEXT | NOT NULL |
| `league_name` | TEXT | DEFAULT `''`，**空字串代表該層級整體聚合列**（非某個特定聯盟），是 `_merge_statcast_into_season()` 找 `level_wide`/`own_league` fallback 用的 sentinel row |
| `fip_constant` | REAL | NOT NULL |
| `lg_era` | REAL | DEFAULT `0`，`0` 被視為 cache miss（見 §8） |

UNIQUE `(year, sport_level, league_name)`。來源：`api/league_stats.py::fetch_team_league_map()` +
`fetch_team_pitching_totals()` → `stats/advanced/fip.py::compute_league_fip_constant()`。
誰寫/讀：`league_constant/pitching.py::_load()` / `_save()` / `_fetch_and_compute()`。

---

## 6. `play_videos` / `game_content_processed`

### 6.1 `play_videos`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `game_pk` | INTEGER | NOT NULL |
| `play_id` | TEXT | NOT NULL，對應 `pitches_json[].play_id` |
| `title` | TEXT | DEFAULT `''` |
| `mp4_url` | TEXT | NOT NULL |
| `fetched_at` | TEXT | NOT NULL |

UNIQUE `(game_pk, play_id)`。來源：`api/content.py::extract_play_videos()`（解析 `/game/{pk}/content`）。
誰寫：`db/play_videos.py::save_play_videos()`（呼叫端：`sync/statcast.py::fetch_highlight_videos()`）。
誰讀：`db/play_videos.py::load_video_map()`（build 時載入 `{game_pk: {play_id: mp4_url}}`，供 `render/pitch_log.py` 附加影片連結）。

### 6.2 `game_content_processed`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `game_pk` | INTEGER | PK |
| `processed_at` | TEXT | NOT NULL |
| `videos_found` | INTEGER | DEFAULT `0` |

用途：標記哪些 MLB 比賽的 `/content` 端點已經抓過；`videos_found=0` 的列會在
`retry_cutoff_date` 之後被視為候選重試（影片可能延遲上架）。
誰寫/讀：`db/play_videos.py::mark_content_processed()` / `content_fetch_candidates()`。

---

## 7. 表格間的邏輯關聯

SQLite 沒有宣告 FOREIGN KEY，以下關聯純靠程式邏輯維持一致：

- `players.mlb_id` ← `season_stats.player_mlb_id`、`game_logs.player_mlb_id`（一對多）
- `game_logs.game_id` ↔ `playbyplay_processed.game_pk` ↔ `play_videos.game_pk` ↔
  `game_content_processed.game_pk`：同一個 MLB `game_pk`，只是不同表欄位名不同
  （`game_id` vs `game_pk`）
- `season_stats.(year, sport_level, league_name)` 與 `league_fip_constants.(year, sport_level, league_name)`、
  `season_stats.(year, sport_level)` 與 `tjstats_park_factors.(year, level)` /
  `tjstats_league_constants.(year, level_code, league)`：不是 DB 層 JOIN，
  是 `sync/statcast.py` 和 `render/pages.py` 在 Python 端用 dict lookup 配對
  （`level` 拼法在 TJStats 表跟 `sport_level` 的 canonical code 不完全相同，
  轉換規則見 `api/tjstats.py` 的 `PF_LEVEL_PARAM`/`LC_LEVEL_CODE`）
- `game_logs.player_mlb_id` 與 `pitches_json[].batter_id`/`pitcher_id`：後者是
  API 原始 ID，理論上等於前者，但因為 `role="batter"/"pitcher"` 兩種掃描模式
  各自只收該角色的球，兩者不總是同一顆球都出現

---

## 8. Schema 演進備註

`init_db()` 的執行順序是：先跑一大段 `executescript()`（多個 `CREATE TABLE IF NOT EXISTS`），
再依序跑好幾個 `ALTER TABLE ... ADD COLUMN`（用 `try/except OperationalError` 包成冪等），
最後才建立 `play_videos`/`game_content_processed`。實際核對後：

- **`game_logs.pitches_json`、`game_logs.events_json`、`players.roster_status_code`、
  `players.roster_is_active`、`league_fip_constants.lg_era` 這五個欄位已經被直接寫進
  `CREATE TABLE` 那段 script 裡**，所以後面對應的 `ALTER TABLE ADD COLUMN`
  現在對全新資料庫來說是死程式碼（`try/except` 會吃掉 `OperationalError` 靜默跳過）；
  它們仍然有用，只是只服務「建表當時比這次更新還舊」的既有資料庫。
- **`game_logs.sport_level`、`game_logs.hit_coord_checked` 至今仍然只存在於
  `ALTER TABLE` 遷移裡，沒有寫進 `CREATE TABLE`**——代表每次對全新資料庫呼叫
  `init_db()`，這兩個欄位都是靠遷移語句補上的，不是說只有舊資料庫才會跑到。
  如果之後要精簡 `schema.py`，可以把前一類已經死掉的遷移直接刪掉，但這兩個
  不能刪。
- `league_fip_constants.lg_era` 的 `DEFAULT 0` 是刻意設計：`league_constant/pitching.py::_load()`
  把 `lg_era <= 0` 視為 cache miss，所以舊資料（遷移前寫入、只有 `fip_constant`
  沒有 `lg_era`）會在下次讀取時自動觸發重新抓取自我修復，不需要額外的 backfill script。
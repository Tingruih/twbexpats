# Taiwan MLB Tracker 函式索引

> 最後核對：2026-09-23
>
> 範圍：`site_builder/` 全部 120 個 Python 檔案，以及 CLI `build.py`。
> 第 1～8 章共盤點 261 個 function/method，包含公開函式、底線開頭的內部 helper、
> class method 與函式內 closure。清單以目前原始碼 AST 為準。

這份文件是實作時的「先去哪個檔案、該呼叫哪個函式」導覽。每個表格都同時回答：

- **函式做什麼**：核心輸入、輸出或副作用。
- **函式放在這裡的原因**：它在資料流中的定位，以及誰通常會呼叫它。
- **是否適合作為入口**：沒有底線的是模組對外介面；`_` 開頭、class method 或
  closure 是實作細節，除非正在修改該模組，否則不要跨模組直接依賴。

## 目錄

0. [整體資料流](#0-整體資料流)
1. [api/ — 外部資料來源](#1-api--外部資料來源)
2. [db/ + league_constant/ — 持久層與聯盟環境](#2-db--league_constant--持久層與聯盟環境)
3. [stats/ — 統計計算](#3-stats--統計計算)
4. [sync/ — 同步管線](#4-sync--同步管線)
5. [render/ — 靜態網站渲染](#5-render--靜態網站渲染)
6. [graph/ — 圖表資料](#6-graph--圖表資料)
7. [util/ — 通用工具](#7-util--通用工具)
8. [頂層模組](#8-頂層模組)
9. [build.py — CLI](#9-buildpy--cli)
10. [完整性核對方式](#10-完整性核對方式)
11. [新增功能時的掛接位置](#11-新增功能時的掛接位置)

---

## 0. 整體資料流

```text
build.py
├─ sync / update（refresh --full-history 走 sync）
│  └─ sync.players → api.* → db.*
├─ statcast
│  └─ sync.statcast → api.games/content/stats
│                   → sync.extract
│                   → stats.* + graph.*
│                   → db.*
│                   → sync.advanced → api.stats (sabermetrics)
│                                   → league_constant.pitching
│                                   → stats.advanced
└─ build
   └─ render.pages → db.bundles
                   → league_constant.batting
                   → stats.* + graph.season_trend
                   → Jinja2 templates + static assets
```

分層邊界：

- `api/` 只取得及解析外部資料，不寫 SQLite。
- `db/` 只管 schema、查詢與 upsert，不打外部 API。
- `league_constant/` 負責取得、計算、快取每年度/層級/聯盟的投打環境常數。
- `stats/` 是純計算層；聯盟環境一律由呼叫端以參數傳入。
- `sync/` 協調網路、平行 worker、資料抽取與 DB 寫入。
- `render/` 把 DB bundle 塑形成模板 payload 並輸出網站。
- `graph/` 產生前端圖表 payload，不負責 HTML。
- `util/` 不含棒球領域規則。

---

## 1. api/ — 外部資料來源

### 1.1 套件入口與 HTTP 基礎設施

| 檔案 | 所有函式 / method | 功能與定位 |
|---|---|---|
| `api/__init__.py` | 無函式 | Re-export API 公開入口與 `FetchError`；呼叫端可從 `site_builder.api` 匯入。 |
| `api/client.py` | `_RateLimiter.__init__(rate)`<br>`_RateLimiter.acquire()` | 建立 process-wide、thread-safe 節流器；`acquire()` 計算下一個請求時槽並在需要時阻塞。只供本模組使用。 |
|  | `_LoggingRetry.increment(method=None, url=None, response=None, error=None, _pool=None, _stacktrace=None)` | urllib3 `Retry` 子類別；每次重試記一行 WARNING（含 urllib3 只記 DEBUG 的 429/5xx 狀態碼重試），額度用完時照常丟 `MaxRetryError`。 |
|  | `_build_session()` | 建立帶連線池與 429/502/503/504、連線/讀取錯誤 retry/backoff（`_LoggingRetry`）的 `requests.Session`。 |
|  | `_session()` | 從 thread-local 取出 session；每個 worker thread 第一次呼叫時才建立。 |
|  | `_request(url, timeout=API_TIMEOUT)` | 所有 HTTP GET 的共同底層：先節流，再使用 thread-local session，最後 `raise_for_status()`。 |
|  | `_get_with_body_retry(url, timeout, parse)` | `parse(_request(url))`；body 讀到一半斷線（`ChunkedEncodingError`）或內容殘缺（`JSONDecodeError`）時以相同退避重試，這兩種發生在 urllib3 Retry 之後，Retry 管不到。 |
|  | `get_json(url, timeout=API_TIMEOUT)` | 對外 JSON GET；回傳解析後 dict，重試用盡丟 `FetchError`（`requests.exceptions.RequestException`）。 |
|  | `get_text(url, timeout=API_TIMEOUT)` | 對外文字 GET；供 TJStats HTML 解析使用，沿用同一套節流與 retry，失敗丟 `FetchError`。 |

### 1.2 MLB Stats API 與 TJStats

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `api/content.py` | `get_game_content(game_pk)` | 取得 `/game/{pk}/content`；失敗丟 `FetchError`（不能回 `{}`，否則會被記成「沒有影片」而不再重抓）。 |
|  | `extract_play_videos(content)` | 從 highlights 找出 `guid == playId` 且具有 `.mp4` playback 的片段，回傳 `{play_id,title,mp4_url}` 列表。 |
| `api/games.py` | `get_game_play_by_play(game_pk)` | 取得單場 `withMetrics` 完整 live feed（含 `gameData.status.abstractGameState`）；供 `sync.extract` 擷取逐球資料。失敗丟 `FetchError`。 |
| `api/league_stats.py` | `fetch_team_league_map(sport_id, year)` | 回傳 `{team_id: league_name}`；用來把球隊投球總量分到各聯盟。失敗丟 `FetchError`。 |
|  | `fetch_team_pitching_totals(sport_id, year)` | 回傳每隊 HR、BB、HBP、K、ER、outs；是反推聯盟 FIP 常數的原始資料。失敗丟 `FetchError`。 |
| `api/players.py` | `get_player_profile(mlb_id)` | 取得 profile、current team、transactions、rosterEntries，整理姓名、身體資料、守備位置、慣用手、現役與 roster 狀態、目前球隊/層級。主請求失敗丟 `FetchError`；球隊層級附帶請求失敗只記 warning 並留空。 |
| `api/schedule.py` | `get_next_game(team_id)` | 查未來七天第一場 Preview 比賽，轉成台灣時區的下一場賽事摘要；沒有賽事回 `None`，抓取失敗丟 `FetchError`（呼叫端據此保留舊的下一場比賽）。 |
| `api/stats.py` | `_fetch_stats(mlb_id, query, years=None, *, leagues=MLB_AND_MILB)` | 本檔唯一的請求迴圈：依「年份 → `leagues`」順序打 `/people/{id}/stats?{query}` 並串接 `stats`；`MLB_AND_MILB = ("mlb_milb",)`（MLB + 所有 MiLB 一次取回；資料與「不帶 + `milb_all`」兩次請求相同、只有順序不同，而 `sync/players.py` 的寫入與順序無關）、`MLB_ONLY = (None,)`。本檔所有函式任一請求失敗即丟 `FetchError`，不回傳部分結果。 |
|  | `get_player_stats(mlb_id)` | 同時查 MLB/MiLB `yearByYear` 的 hitting/pitching/fielding，回傳所有球季基礎數據。 |
|  | `get_player_advanced_stats(mlb_id, years=None)` | 逐年查 MLB/MiLB `seasonAdvanced`；供補入 BABIP、P/PA 等進階球季欄位。 |
|  | `get_game_logs(mlb_id, season)` | 同時查指定球季 MLB 與 MiLB gameLog，並帶上 `GAME_LOG_GAME_TYPES`（例行賽 R + 季後賽 F/D/L/W，刻意不含重複標記用的 P）；升降級球員不會漏掉任一端，每筆 split 各自帶 `gameType`。 |
|  | `get_player_sabermetrics(mlb_id, years=None)` | 查 MLB-only sabermetrics（FIP、xFIP、WAR、wRC+）原始 splits。 |
|  | `get_player_expected_stats(mlb_id, years=None, group="pitching")` | 查 MLB-only expectedStatistics（xwOBA、xBA、xSLG）；`group` 決定打擊或投球。 |
| `api/tjstats.py` | `_log_missing_table(year, what, url)` | 找不到預期 table 時的記錄：過去球季記 WARNING（版面可能改了），當季以後記 INFO（尚未發布）。 |
|  | `fetch_park_factors(level, year)` | 解析 TJStats park-factor 表，回 `{team_name: {pf_final, league}}`；未知層級或失敗回 `{}`（best-effort，不丟例外；抓取失敗或有列卻全部解析失敗會記 warning）。TJStats 專屬的 `TJSTATS_LEVEL_PARAMS` / `PF_LEVEL_PARAM` / `LC_LEVEL_CODE` 也定義在此。 |
|  | `fetch_league_constants(year)` | 解析 TJStats league-constants 表，回 `{(level_code, league): {lg_woba, lg_r_pa}}`；由 `league_constant.batting` 與 park factor join 後供 wRC+。 |

實作判斷：新增 MLB endpoint 放在語意對應檔案；只有共用 HTTP 行為才放
`client.py`。API 函式不要直接寫 DB，也不要在此計算玩家統計量。

---

## 2. db/ + league_constant/ — 持久層與聯盟環境

### 2.1 `db/` — 純 SQLite row access

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `db/__init__.py` | 無函式 | 套件說明，不做 re-export；此層只讀寫資料表，不抓外部資料或計算統計。 |
| `db/schema.py` | `_add_column(conn, table, column_ddl)` | `ALTER TABLE ... ADD COLUMN`；只忽略 "duplicate column name"，其他 `OperationalError`（資料庫被鎖、磁碟已滿）照常丟出。 |
|  | `_require_game_logs_role(conn)` | 既有 `game_logs` 沒有 `role` 欄位（角色拆分前的舊 DB）時 `SystemExit`，提示刪除 DB 以 `build.py all` 重建；結構檢查，不做回補。 |
|  | `init_db(conn)` | 先呼叫 `_require_game_logs_role`，再建立 players、season_stats、game_logs（每個角色一列，`UNIQUE(player_mlb_id, game_id, role)`）、play-by-play、聯盟常數/影片快取表、`season_fetches` 抓取登記表與索引；以可重複執行的 `CREATE IF NOT EXISTS` 和 `_add_column` 做正向 migration（`game_logs` 不再有 migration：舊表一律擋下重建）。新增的 `lg_era` 欄位預設 0，會由 pitching constant loader 視為 cache miss 自動修復。 |
| `db/season_stats.py` | `load_player_season_rows(cur, mlb_id)` | 讀一位球員所有球季列，`stat_json` 攤平成 `Obj` 列物件（附 `fielding_json`、`level_order`），依年度新到舊、層級高到低、同層級隊名排序（與 DB 讀出順序無關）；拆分欄位保持原樣（`gp`/`p_gp` 等），render 端再以 `positions.project_role` 投影；`load_player_bundle()` 與 sync 的層級判斷共用。 |
|  | `load_season_row(cur, mlb_id, year, team_name)` | 讀單一 `(球員, 年, 球隊)` 球季列並解析 JSON；不存在時回空 dict。 |
|  | `save_season_row(cur, mlb_id, year, team_name, league_name, sport_level, stat_json, fielding_json)` | 以同一複合 key upsert 球季數據及守備 JSON；`stat_json` 依 key 排序存，同一份資料不論寫入順序存出的文字相同。 |
|  | `players_with_existing_stats(conn)` | 回傳已有 season_stats 的 MLB ID set；refresh 用它判定新球員是否必須完整回補。 |
| `db/players.py` | `warn_orphaned_players(conn, roster_ids)` | 找出 DB 有但 roster 已移除的球員，以 logger.warning 輸出清單與清理 SQL；只診斷，不自動刪除。 |
|  | `get_cached_is_active(cur)` | 批次讀取 `{mlb_id: bool(is_active)}`，讓同步管線可跳過已知非現役球員。 |
|  | `get_incomplete_history_ids(cur)` | 回傳 `history_synced = 0`（上次全歷史抓取有請求失敗）的 MLB ID set；`_run_pipeline` 把它們當首次同步再抓一次全歷史。 |
| `db/game_logs.py` | `load_all_pitches_for_player(cur, mlb_id, role)` | 合併玩家該角色（`game_logs.role`，必填）所有 `pitches_json` 成 `{(year, sport_level): pitches}`；二刀流的投球與打擊逐球資料不會混在一起；只取例行賽（`game_type = REGULAR_SEASON_GAME_TYPE`），因為結果會併入只含例行賽數字的 season_stats；舊列缺層級時只在可唯一推定時補入。 |
| `db/bundles.py` | `load_player_bundle(cur, player_row)` | build 的主要讀取入口；建立 `(player, stats, logs)` 三元組，解析 JSON/date、計算年齡/status/headshot 層級、排序球季列，只讀主要角色（`primary_role(player.position)`）的 game_logs 列（經 `load_role_game_logs`）。 |
|  | `load_role_game_logs(cur, mlb_id, role)` | 讀某球員某角色（`game_logs.role`）的 game_logs，日期新到舊，每筆 log 附 `game_type`/`is_postseason`（`game_type != REGULAR_SEASON_GAME_TYPE`）；`load_player_bundle` 讀主要角色、`render/pages.py` 另讀雙角色球員的次要角色。 |
| `db/play_videos.py` | `save_play_videos(cur, game_pk, videos, now_iso)` | 將一場比賽的 play-level mp4 URL upsert 到 `play_videos`；不自行 commit。 |
|  | `mark_content_processed(cur, game_pk, videos_found, now_iso)` | 記錄 `/content` 已處理及影片數；不自行 commit。 |
|  | `content_fetch_candidates(cur, roster_ids, retry_cutoff_date)` | 回傳需要初抓或近期零影片重試的 MLB game PK。 |
|  | `load_video_map(cur)` | build 時載入 `{game_pk: {play_id: mp4_url}}`；舊 schema 沒有表時安全回 `{}`。 |
| `db/season_fetches.py` | `load_fetched(cur, source)` | 讀 `season_fetches` 中某個 source 已登記的 `{(subject, year)}`；整次執行讀一次。source 常數：`SABERMETRICS`、`EXPECTED_STATS`（打擊）、`P_EXPECTED_STATS`（投球）、`FIP_CONSTANTS`。 |
|  | `needs_fetch(fetched, subject, year, *, force)` | 外部逐年資料的共用抓取判斷：`force`、當季（`is_season_in_progress`）或過去球季未登記時回 True。 |
|  | `mark_fetched(cur, source, subject, years, now_iso=None)` | 登記成功抓過（含 API 成功但無資料）的過去球季；當季自動略過不登記。不自行 commit。 |

### 2.2 `league_constant/` — 聯盟環境供應層

這是唯一同時抓外部資料、計算環境值並寫 SQLite cache 的層。`stats/` 只接收已解
出的常數，`db/` 只保留 schema 與一般 row access。

| 檔案 | 所有函式 / method | 功能與定位 |
|---|---|---|
| `league_constant/__init__.py` | 無新函式 | Re-export batting/pitching resolver、one-shot helper 與 cache policy。 |
| `league_constant/policy.py` | `should_use_cache(year, *, policy, force_refresh)` | 共用 cache 決策；`force_refresh` 永遠略過 cache，`ACCUMULATES_IN_SEASON` 對當季重抓，`FINAL_ONCE_PUBLISHED` 一旦有值即重用。`RefreshPolicy` 是 Enum，沒有自訂 method。 |
| `league_constant/pitching.py` | `_load(conn, level, year)` | 讀 `{league_name: LeagueFipConstant}`；忽略 `lg_era <= 0` 的舊 cache row，促使自動重抓。 |
|  | `_save(conn, level, year, data)` | upsert 每聯盟與 `""` 層級總體的 FIP constant + lgERA，並 commit。 |
|  | `_fetch_and_compute(level, year)` | level→sportId，抓球隊 totals/league map，按聯盟及整層加總後呼叫 `compute_league_fip_constant()`。任一請求失敗回 `None`（不回只有整層合計的部分結果，以免被當成完整值永久快取）；確定沒有常數（未知層級、球季未開打、沒有自責分）回 `{}`。 |
|  | `_from_cache(conn, level, year, *, force_refresh, fetched)` | 不連網解析一個 slice：過去球季有 cache 回 cache、已登記「抓過但沒資料」回 `{}`；需要連網時回 `None`。 |
|  | `_store(conn, level, year, fetched)` | 寫入一次抓取結果：有常數寫 cache；`{}` 登記到 `season_fetches`；`None`（失敗）不登記。最後回該 slice 應使用的值（失敗時退回舊 cache）。 |
|  | `get_pitching_constants(conn, level, year, *, force_refresh=False)` | 單次查詢入口；等同 `PitchingConstants(...).for_level()`。 |
|  | `PitchingConstants.__init__(conn, *, force_refresh=False)` | 建立單次 sync 使用的 resolver、`(level,year)` 記憶體 cache，並讀一次 `season_fetches` 的 `fip_constants` 登記。 |
|  | `PitchingConstants.prefetch(slices)` | 一次解析多個 `(level,year)`：先查 cache/登記，剩下的 HTTP 請求以執行緒平行抓，SQLite 讀寫都留在呼叫端執行緒。 |
|  | `PitchingConstants.for_level(level, year)` | 多 slice 查詢入口；同一次 sync 每個 `(level,year)` 最多解析一次，未解析時走 `prefetch([key])`。 |
| `league_constant/batting.py` | `publishes_constants(level, year)` | 判斷 TJStats 是否涵蓋該層級/年度（`is_level(level, *TJSTATS_LEVEL_PARAMS)`，順帶驗證對照表的 key 都是 tier key）；render 也用它決定 wRC+ 欄位是否可能存在。 |
|  | `_load_park_factors(conn, level, year)` | 讀一個 `(level,year)` 的球隊 park factors。 |
|  | `_save_park_factors(conn, level, year, data)` | upsert park factors 並 commit。 |
|  | `_get_park_factors(conn, level, year, *, force_refresh)` | 依 final-once-published policy 選 cache 或 scraper；空結果不覆蓋舊值。 |
|  | `_load_league_constants(conn, year)` | 一次讀某年度所有層級/聯盟的 lg_wOBA、lg_R/PA。 |
|  | `_save_league_constants(conn, year, data)` | upsert league constants 並 commit。 |
|  | `_get_league_constants(conn, year, *, force_refresh)` | 依年度 cache 或抓取整張 TJStats league-constants 表。 |
|  | `_join(level, pf_entries, lc_entries)` | 以 league 將每隊 park factor 與 lg_wOBA/lg_R/PA join 成 `{team_name: BattingConstant}`；缺聯盟常數的球隊略過。 |
|  | `BattingConstants.__init__(conn, *, force_refresh=False)` | 建立 build-run resolver；分開 memoize `(level,year)` park factors 與年度 league constants。 |
|  | `BattingConstants.for_level(level, year)` | 多 slice 查詢入口；未涵蓋範圍回 `{}`，否則回每隊完整 wRC+ 環境。 |
|  | `get_batting_constants(conn, level, year, *, force_refresh=False)` | one-shot 等價入口；只查單一 slice 時使用。 |

`BattingConstant` 與 `LeagueFipConstant` 是 `NamedTuple` 資料載體，沒有自訂 method。
cache `_save*` helper 會自行 commit；一般 `db/play_videos.py` cursor 寫入函式則由
外層 transaction 決定 commit 時機。

---

## 3. stats/ — 統計計算

`stats/__init__.py` 本身無函式，只描述套件哲學。這一層不做 I/O；FIP、xWPCT、
wRC+ 所需的聯盟環境皆由 `league_constant/` 解析後以參數傳入。

### 3.1 `stats/core/` — 共用資料模型與聚合

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `core/__init__.py` | 無函式 | 共用核心套件標記。 |
| `core/innings.py` | `ip_to_outs(ip_value)` | 把棒球局數記法（`7.2` = 7⅔ 局）轉為 outs；所有投手率先走這裡。 |
|  | `outs_to_ip(outs)` | 把 outs 轉回棒球局數記法。 |
|  | `per_nine(count, outs, digits=2)` | 每九局比率 `count×27/outs`，以整數分數精確計算後四捨五入；`digits=None` 不捨入（只給會再被計算的中間值，目前僅聯盟 ERA）；count 缺值或 outs 為 0 回 `None`。ERA 與各 /9 率共用。 |
| `core/selectors.py` | `has_appearance(stat)` | gp/pa/ab/bf/IP 任一大於 0 即視為真正出賽。 |
|  | `appeared_roles(row)` | 這一列有出賽的角色集合：`pa > 0` → `BATTER`；`bf > 0` 或 IP > 0 → `PITCHER`。衍生數據（sabermetrics 各 group、wRC+、FIP）「這個角色要不要算」的唯一判斷；不看已依角色拆開的 `gp`。 |
|  | `highest_level_row(stats)` | 在傳入的列中，優先從有出賽列依 `level_rank` 找最高層級列；全無出賽才退回所有列。同層級平手依序取最近一年、出賽量（PA + BF）較多、隊名，結果與列的順序無關（`-year` 讓退役頁標章維持「最近一次到達」）。範圍由呼叫端決定：退役頁傳整個生涯，`_write_player_to_db()` 只傳最近一季。 |
|  | `highest_level(stats)` | 回傳最高層級的 canonical tier key，而非時代顯示字串。 |
| `core/pa_outcomes.py` | `compute_pa_outcome_totals(pa_final)` | 從打席結束球彙整 wOBA numerator/denominator、hits、AB；排除故意四壞、犧牲觸擊與非 PA 跑壘事件。 |
| `core/aggregate.py` | `sum_counting(stats, result)` | 依 `COUNTING_FIELD_GROUPS`（共用/打擊/投球）分組加總：某列整組沒有值時貢獻 0；某列有這組數據卻缺某欄時該欄總和為 `None`（未知，避免分子少算、分母照加）。會修改 `result`。 |
|  | `compute_rate_stats(agg)` | 從合計列重算 AVG/OBP/SLG/OPS 與 ERA/WHIP；會修改 `agg`。 |
|  | `aggregate_stats(stats)` | 建立新 `Obj`，加總 counting stats、以 outs 正確合併 IP，再計算 rate stats。 |
| `core/atypical.py` | `_flush_bunt_pa(group)` | 幫一個 PA（`iter_plate_appearances()` 產出的非空 list）內全部 pitch 打上 `_bunt_pa` 旗標：該 PA 以 `SAC_BUNT_EVENTS`（含 `sac_bunt_double_play`）或 `BUNT_TRAJECTORIES` 收尾即整段標記為觸擊嘗試。 |
|  | `annotate_atypical(pitches)` | 「異常情境」排除框架的前置 pass：對完整、未依 `pitch_hand` 拆分的球員逐球列表，以 `iter_plate_appearances()` 切成打席並逐一呼叫 `_flush_bunt_pa()`。須在任何過濾與 `compute_pitch_splits()` 之前執行；原地修改，可重複呼叫。 |
|  | `_matches(p, reason)` | 單一 `Reason` 對單球的判斷：`BUNT_PA` 讀 `_bunt_pa` 旗標，`BUNT_PITCH` 查 `BUNT_SWING_CODES`；未知 reason 拋例外。 |
|  | `exclude_atypical(pitches, reasons)` | 對外唯一入口：依傳入的 `Reason` 集合過濾球種表要排除的觸擊等異常球/打席；`Reason`、`Granularity` 是 `StrEnum`，沒有自訂 method。 |
| `core/annotate.py` | `_fill(s, field, value)` | value 非 `None` 才寫入欄位；是衍生欄位的共同 guard。 |
|  | `annotate_row(s)` | 在單列缺值時補打者/投手衍生數據，絕不覆蓋 API 既有值；會修改輸入列。 |
|  | `annotate_computed_stats(all_stats)` | 為每列設定 `np = pitches` 並呼叫 `annotate_row()`；回傳同一列表。 |
| `core/career.py` | `_teams_display(stats)` | 「層級 球隊」以 ` / ` 串接，層級依各列年份經 `level_display` 顯示；`compute_career` 與年度 summary 共用的唯一組字邏輯。 |
|  | `compute_career(stats, level_filter=None)` | 跨球季合計，選擇性篩 MLB（`is_mlb`）/MiLB（`is_milb`，不含冬季/獨立聯盟）；附球隊清單（層級依各列年份經 `level_display` 顯示）與年份範圍。 |
|  | `compute_year_groups(all_stats)` | 組成最近年度優先的 `{year, summary, rows, multi}`，供模板顯示年度總列與逐隊列。`summary` 是全站唯一的單一年度合計列（含 `annotate_row` 衍生欄位與 `teams_display`），bio 卡的本季合計（`season_combined`）直接取當年的 `summary`。 |
| `core/pitches.py` | `is_swing(p)` / `is_whiff(p)` / `is_called_strike(p)` | 依 MLB result code 判斷揮棒、揮空、主審好球。 |
|  | `is_in_zone(p)` / `is_out_of_zone(p)` | 依 zone 1–9 / 11–14 分類；缺 zone 兩者皆 False。 |
|  | `is_unknown_pitch_type(pitch_type, pitch_name=None)` | 判斷空值、UN/UNKNOWN placeholder，以及故意壞球、pitchout、自動好壞球、no-pitch 等沒有實際投球內容的事件代碼。 |
|  | `filter_known_pitch_events(pitches)` | 球種細分表的共同前處理：剔除未知球種與非實際投球事件。 |
|  | `pitch_type_key(p)` | 球種分組鍵：`pitch_type`，缺值時為 `"UN"`。 |
|  | `pitch_type_shares(type_counts, total)` | `[{type, count, pct}]`，依顆數由多到少、同顆數維持輸入順序，`pct` 以 `total` 為分母取 4 位；`graph/movement.py` 與 `graph/plinko.py`（整體與各球數節點）共用的球種佔比清單。 |
|  | `group_by_pitch_type(pitches)` | `{pitch_type: [pitch, ...]}`，保留球種首次出現順序；球種細分表共用。 |
|  | `pitch_type_display_name(pitches, pitch_type)` | 同一球種中第一個非空 `pitch_name`，整組皆空時退回代碼；所有球種表的名稱都走這裡以保持一致。 |
|  | `pre_count_tuple(p)` / `post_count_tuple(p)` | 安全取得投球前/後 `(balls, strikes)`；不完整或無法轉 int 時回 `None`。 |
|  | `count_label(count)` | `(balls, strikes)` 轉 `"B-S"`。 |
|  | `iter_plate_appearances(pitches)` | 打席邊界的唯一定義：`(game_pk, at_bat_index)` 改變即切分，不看 `is_pa_final`（打席中被換下的那段沒有結果球，以它切會把同場下一個打席併進來）；yield 非空打席 list，沒有結果球的打席也會 yield。 |
|  | `aggregate_pitches(pitches)` | 單次掃描建立 swings、whiffs、zone、in-play、PA-final、BBE、球路類型、barrel/hard-hit 與 spray 等共用聚合。 |

### 3.2 `stats/batting/` — 打者球季公式

`batting/__init__.py` 無函式。下列函式都是小型純函式；分母無效或必要輸入缺失時
回 `None`，避免模板把「不可計算」誤顯示為 0。

| 檔案 | 唯一函式 | 公式 / 定位 |
|---|---|---|
| `ab_per_hr.py` | `compute_ab_per_hr(ab, hr)` | AB ÷ HR，兩位小數（同 API）。 |
| `avg.py` | `compute_avg(hits, ab)` | H ÷ AB。 |
| `babip.py` | `compute_babip(hits, hr, ab, so, sac_flies=0)` | `(H−HR)/(AB−SO−HR+SF)`；打者與投手對手 BABIP 共用。 |
| `bb_pct.py` | `compute_bb_pct(bb, plate_appearances)` | BB ÷ PA。 |
| `go_ao.py` | `compute_go_ao(ground_outs, air_outs)` | GO ÷ AO，兩位小數。 |
| `iso.py` | `compute_iso(tb, hits, ab)` | `(TB−H)/AB`；直接用計數算，不拿已捨入的 SLG、AVG 相減。 |
| `k_pct.py` | `compute_k_pct(so, plate_appearances)` | SO ÷ PA/BF，由呼叫端決定分母語意。 |
| `obp.py` | `compute_obp(hits, bb, hbp, ab, sac_flies)` | `(H+BB+HBP)/(AB+BB+HBP+SF)`。 |
| `ops.py` | `compute_ops(obp, slg)` | 已捨入的 OBP + 已捨入的 SLG（MLB API 慣例）。 |
| `p_per_pa.py` | `compute_p_per_pa(pitches, plate_appearances)` | 用球數 ÷ PA/BF，三位小數（同 API）。 |
| `sb_pct.py` | `compute_sb_pct(sb, cs)` | SB ÷ (SB+CS)，回傳三位小數 float；缺值或分母為零回 `None`。 |
| `slg.py` | `compute_slg(tb, ab)` | TB ÷ AB。 |
| `xbh.py` | `compute_xbh(doubles, triples, hr)` | 2B + 3B + HR；三項皆為 0/空時回 `None`。 |

### 3.3 `stats/pitching/` — 投手球季與出手點公式

`pitching/__init__.py` 無函式。

| 檔案 | 所有函式 | 公式 / 定位 |
|---|---|---|
| `era.py` | `compute_era(earned_runs, outs)` | `ER×27/outs`（`per_nine`），兩位小數。 |
| `whip.py` | `compute_whip(hits_allowed, bb, outs)` | `(H+BB)×3/outs`，兩位小數；H 缺值回 `None`、BB 缺值視為 0。 |
| `k_per_9.py` | `compute_k_per_9(so, outs)` | `SO×27/outs`，兩位小數（同 API）。 |
| `bb_per_9.py` | `compute_bb_per_9(bb, outs)` | `BB×27/outs`，兩位小數。 |
| `h_per_9.py` | `compute_h_per_9(hits_allowed, outs)` | `H×27/outs`，兩位小數。 |
| `hr_per_9.py` | `compute_hr_per_9(hr_allowed, outs)` | `HR×27/outs`，兩位小數。 |
| `k_bb_ratio.py` | `compute_k_bb_ratio(so, bb)` | SO ÷ BB，兩位小數。 |
| `p_per_ip.py` | `compute_p_per_ip(pitches, outs)` | `pitches×3/outs`，兩位小數（同 API）。 |
| `rs_per_9.py` | `compute_rs_per_9(run_support, outs)` | `run_support×27/outs`，兩位小數；注意 API 的 `runsScoredPer9` 實為 RA9，語意不同（見模組 docstring）。 |
| `strike_pct.py` | `compute_strike_pct(strikes, pitches)` | 球季 API strikes ÷ pitches，回三位小數 float；不同於逐球 `compute_pitch_strike_pct()`。 |
| `win_pct.py` | `compute_win_pct(wins, losses)` | W ÷ (W+L)，回三位小數 float；缺值或分母為零回 `None`。 |
| `extension.py` | `compute_avg_extension(pitches)` | 平均非空 extension（ft）。 |
| `opponent_slash.py` | `_set_if_real(s, field, value)` | 值不為 `None` 才寫入欄位，讓分母為零時欄位保持缺值。 |
|  | `annotate_opponent_slash(s)` | 從投手對手 counting stats 補 `p_avg/p_obp/p_slg/p_ops`（三位小數 float）；任一必要分量不足就保留空值，會修改輸入列。OPS 缺新算值時以 `safe_float` 讀既有 `p_obp/p_slg`（相容舊 DB 字串）。 |
| `release_point.py` | `_origin_plane(p)` | 讀逐球 `y0` 軌跡原點；舊資料退回 50 ft 常數。 |
|  | `_at_plane(p, y_target)` | 解二次軌跡在指定 y 平面的 `(x,z)`；欄位不全或無有效根回 `None`。 |
|  | `compute_release_point(p)` | 用 extension 定出真正出手平面並回單球 `(h_rel,v_rel)`；缺 extension 不估算。 |
|  | `compute_avg_release_point(pitches)` | 平均一組球的出手點；整組皆無 extension 時才統一退回正規化 50 ft 平面。 |

### 3.4 `stats/discipline/` — 打擊紀律

| 檔案 | 唯一函式 | 分子 / 分母與用途 |
|---|---|---|
| `discipline/__init__.py` | `discipline_metrics(agg)` | 組裝球季紀律指標，並保存各率真實 denominator 欄位。 |
| `csw_pct.py` | `compute_csw_pct(agg)` | (called strikes + whiffs) ÷ total pitches。 |
| `o_swing_pct.py` | `compute_o_swing_pct(agg)` | zone 外揮棒 ÷ zone 外球。 |
| `pitch_strike_pct.py` | `compute_pitch_strike_pct(pitches)` | 依逐球結果/zone 判斷好球 ÷ pitches；供球種表與打者 Statcast。 |
| `put_away.py` | `compute_put_away(pitches)` | 兩好球後造成三振的比例；回 `(put_away_pct, two_strike_count)`。 |
| `swing_pct.py` | `compute_swing_pct(agg)` | swings ÷ total pitches。 |
| `swstr_pct.py` | `compute_swstr_pct(agg)` | whiffs ÷ total pitches。 |
| `whiff_pct.py` | `compute_whiff_pct(agg)` | whiffs ÷ swings。 |
| `z_contact_pct.py` | `compute_z_contact_pct(agg)` | zone 內接觸 ÷ zone 內揮棒。 |
| `z_swing_pct.py` | `compute_z_swing_pct(agg)` | zone 內揮棒 ÷ zone 內球。 |
| `z_whiff_pct.py` | `compute_z_whiff_pct(agg)` | zone 內揮空 ÷ zone 內揮棒；主要供球種 outcomes 表。 |
| `zone_pct.py` | `compute_zone_pct(agg)` | zone 內球 ÷ total pitches。 |

### 3.5 `stats/batted_ball/` — 擊球品質與方向

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `batted_ball/__init__.py` | `batted_ball_metrics(agg)` | 組裝 BBE、GB/LD/FB/PU/air、spray、barrel、hard-hit、avg EV 等打者/投手共用欄位；GB/LD/FB/PU/air 分母是有 trajectory 分類的球數、pull/straight/oppo/pull_air 分母是有噴射角分類的球數，兩者皆不用 `n_ip` 當分母以免被未分類球稀釋。 |
| `barrel.py` | `compute_barrel_pct(agg)` | barrels ÷ 有 EV 的 BBE。 |
|  | `is_barrel(ev, la)` | 依 Statcast 98 mph 起跳、隨 EV 放寬且 116 mph 封頂的角度窗判定單球 barrel。 |
| `hard_hit.py` | `compute_hard_hit_pct(agg)` | hard hits ÷ 有 EV 的 BBE。 |
|  | `is_hard_hit(ev)` | EV ≥ 95 mph。 |
| `exit_velocity.py` | `compute_avg_ev(bbe_ev)` | 平均 EV。 |
|  | `compute_max_ev(bbe_ev)` | 最大 EV。 |
|  | `compute_ev90(bbe_ev)` | EV 第 90 百分位；排序後依現有離散 index 取實際觀測值，不做插值。 |
| `launch_angle.py` | `collect_la_values(in_play)` | 有 LA 的擊球仰角清單；avg LA 與 SwSp% 共用的分母樣本（球季入口與走勢圖都用它）。 |
|  | `compute_avg_la(la_values)` | 平均 launch angle。 |
| `sweet_spot.py` | `is_sweet_spot(la)` | 8°–32° 判定。 |
|  | `compute_sweet_spot_pct(la_values)` | sweet-spot 球數 ÷ 有 LA 的球數。 |
| `hr_fb.py` | `compute_hr_fb_pct(pa_final, fb_count)` | PA-final HR ÷ fly balls；投手專用。 |
| `spray.py` | `_zone_to_direction(zone, bat_side)` | LF/CF/RF 區域加打者左右打轉成 pull/straight/oppo；座標與野手代碼兩種分類共用。 |
|  | `spray_direction_from_location(p)` | 缺 hit coordinate 時，以 `hit_location` zone 備援判斷 pull/center/opposite。 |
|  | `spray_direction_from_coordinates(p)` | 將 Gameday `(coord_x,coord_y)` 經透視修正換成噴射角度方向。 |
|  | `compute_spray(in_play)` | 優先座標、再用 location 分類，回各方向 count/rate 與可用樣本數。 |

### 3.6 `stats/advanced/` — 需要年度/聯盟常數的統計

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `advanced/__init__.py` | 無函式 | 標記需要聯盟環境或固定公式常數的統計；環境值仍由外層傳入，套件內不做 I/O。 |
| `advanced/fip.py` | `_fip_raw(hr, bb, hbp, k, outs)` | `(13·HR + 3·(BB+HBP) − 2·K) × 3 / outs`（未加常數），缺值計數視為 0；投手 FIP 與聯盟常數共用的唯一公式，呼叫端須先確認 `outs > 0`。 |
|  | `compute_fip(hr, bb, hbp, k, ip, c_fip=None)` | 純函式 FIP：`_fip_raw + c_fip`；棒球 IP 先轉 outs。`c_fip` 為 None（常數解不出）或無局數時回 `None`，不套預設常數。回 full precision。 |
|  | `compute_league_fip_constant(totals)` | 從聯盟 HR/BB/HBP/K/ER/outs 同時計算 lgERA（`per_nine(..., digits=None)`，不捨入）並以 `lgERA − _fip_raw` 反解 FIP constant，回 `LeagueFipConstant(fip_constant, lg_era)`；無有效局數或 `earned_runs` 為 0（2005 年以前 MiLB，API 不給自責分）回 `None`。 |
| `advanced/woba.py` | `compute_pitch_woba(totals)` | 從 `compute_pa_outcome_totals()` 結果算逐球 wOBA。 |
|  | `compute_season_woba(stat)` | 從球季 counting stats 算 wOBA；故意四壞從 numerator/denominator 排除。 |
| `advanced/xwpct.py` | `compute_xwpct(fip, lg_era)` | 用同一批聯盟投球 totals 算出的 lgERA 與固定 1.83 指數計算預期勝率；任一輸入缺失/非正數回 `None`，不再查表或套用預設 run environment。 |
| `advanced/wrc_plus.py` | `compute_wrc_plus(woba, pf_final, lg_woba, lg_r_pa)` | 套用 TJStats 公式與 park-factor midpoint，回整數 wRC+。 |
|  | `annotate_wrc_plus(bundles, batting_lookup)` | 接受 `BattingConstants.for_level` 類 callback，原地補入每列及同層轉隊合計 wRC+；不看守位，`(year, level)` 組內有任一列有打擊 PA（`appeared_roles`）才查常數並計算（投手上場打擊也有 wRC+）；本身不碰 network/DB，也不寫回 season_stats。 |
|  | `annotate_wrc_plus._wrc_plus_of(stat_row, env=env)` | closure；以該 `(year,level)` 主球隊已解析的 `BattingConstant` 計算單列或聚合列 wRC+。 |

### 3.7 `stats/tables/` — 球種與 split 表

現在沒有 `combine_*` 或 `weighted.py`。跨層級顯示由
`render.pages._build_statcast_entries()` 合併同年度原始 pitches，再重新呼叫
`compute_pitcher_statcast()` / `compute_batter_statcast()`；因此不同欄位的分母與
EV90 等百分位不會被錯誤加權。

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `tables/__init__.py` | 無函式 | 球種細分表套件標記。 |
| `tables/splits.py` | `compute_pitch_splits(pitches, split_specs, split_field, table_fns)` | 通用 all/L/R 等 split 組裝器；過濾指定欄位後對每個 table function 計算 payload。 |
| `tables/arsenal.py` | `compute_pitch_arsenal(pitches)` | 投手逐球種物理/結果表：usage、velo、IVB/HB、spin、extension、release、zone/chase/whiff/put-away、wOBA。 |
| `tables/outcomes.py` | `compute_pitch_outcomes(pitches)` | 投手逐球種結果表：strike、z-whiff、chase、SwStr、CSW、put-away、AVG/wOBA、barrel、hard-hit。 |
| `tables/bat_side_splits.py` | `compute_pitcher_bat_side_splits(pitches)` | 透過 `compute_pitch_splits()` 建立投手對 all/L/R 打者的 arsenal、outcomes、count usage。 |
| `tables/usage_by_count.py` | `_compute_usage_by_count(pitches, key_fn, ordered_keys=None)` | 球數情境 × 球種/球種群組的共用 cross-tab 核心。 |
|  | `compute_pitch_usage_by_count(pitches)` | 逐球種在各 count bucket 的數量與使用率。 |
|  | `compute_pitch_usage_by_count.key_fn(p)` | closure；把 pitch 映射為 `(pitch_type, 顯示名稱)`，名稱預先以 `pitch_type_display_name()` 按整個球種決定。 |
|  | `compute_pitch_group_usage_by_count(pitches)` | 將球種捲成 fastball/breaking/offspeed 後計算 count usage。 |
|  | `compute_pitch_group_usage_by_count.key_fn(p)` | closure；只將主表收錄的球種映射至固定球種群組，無對應者回 `None`。 |
| `tables/vs_pitch_types.py` | `_compute_pitch_bucket_row(key, name, ps)` | 球種與球種群組共用的打者表單列計算，避免欄位定義漂移。 |
|  | `compute_vs_pitch_types(pitches)` | 打者對逐球種的 discipline、AVG/wOBA 與 contact-quality 表；統一剔除未知/非投球事件與 `_ATYPICAL_REASONS`（觸擊 PA/觸擊球），但保留有正式代碼的稀有球種。 |
|  | `compute_vs_pitch_groups(pitches)` | 同一組指標依球種主表捲成 fastball/breaking/offspeed，同樣先排除 `_ATYPICAL_REASONS`；無群組對應者略過。 |
|  | `compute_batter_pitch_hand_splits(pitches)` | 建立打者對 all/L/R 投手的球種、球種群組與 count usage 表。 |

### 3.8 Statcast 彙整入口

| 檔案 | 唯一函式 | 功能與定位 |
|---|---|---|
| `stats/pitcher_statcast.py` | `compute_pitcher_statcast(pitches)` | 投手球季入口：聚合 pitches/PA，再組裝 wOBA against、HR/FB、extension、bat-side tables、Plinko、movement、discipline 與 batted-ball metrics。空輸入回 `{}`。 |
| `stats/batter_statcast.py` | `compute_batter_statcast(pitches)` | 打者球季入口：先 `annotate_atypical()`，再組裝逐球 strike%、wOBA、max EV/EV90/LA/sweet spot、pitch-hand splits（頂層 `vs_pitch_types`/`vs_pitch_groups`/`pitch_group_usage_by_count` 直接沿用 `"all"` 分組，不重算）、Plinko、discipline 與 batted-ball metrics。空輸入回 `{}`。 |

---

## 4. sync/ — 同步管線

### 4.1 套件入口與欄位映射

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `sync/__init__.py` | 無新函式 | Re-export `sync_database`、`update_database`、`sync_statcast`（`sync/advanced.py` 由 `sync_statcast` 呼叫，不另外 re-export）。 |
| `sync/field_maps.py` | `apply_yearbyyear_fields(stat_doc, group_name, stat)` | 把 yearByYear API camelCase 欄位安全轉型並寫入內部 snake_case schema；處理 hitting/pitching，fielding 由 `sync/players.py` 另行保存。 |
|  | `apply_advanced_fields(stat_doc, group_name, stat)` | 把 seasonAdvanced 特有欄位補入同一 stat dict；`pitchesPerPlateAppearance` 依 group 寫 `pitches_seen_per_pa`（打擊）或 `pitches_per_bf`（投球）。 |

### 4.2 `sync/players.py` — 基礎資料同步

| 函式 | 功能與定位 |
|---|---|
| `_is_first_sync(mlb_id, synced_ids)` | 不在 `synced_ids`（有 season_stats 且上次全歷史抓取完整）即需全歷史抓取；refresh 也要為新球員、或上次全歷史抓取有失敗的球員完整回補。 |
| `_fetch_player_data(pconf, year, fetch_all_years=True)` | thread worker；只做 API 抓取與 bundle 組裝，不寫 DB。完整模式抓所有 game-log 年份，快速模式只抓當年。profile 失敗丟 `FetchError`；其餘請求失敗記入 bundle 的 `failed_parts` 並略過該部分（寫入端保留舊值）。 |
| `_fetch_player_data.fetch_part(part, fn, *args, **kwargs)` | closure；呼叫一個 API，`FetchError` 時記 warning（球員名、部分、例外類型）並登記到 `failed_parts`，回 `None`。 |
| `_write_player_to_db(conn, bundle, year)` | 單一玩家的序列寫入：players、season_stats、game_logs（含 upsert 進去的 `game_type`，非 `GAME_LOG_GAME_TYPES` 的重複標記如 `P` 直接略過）、next_game（抓取失敗時不更新），yearByYear 的 `gamesPlayed` 依 `role_for_stat_group` 寫 `gp`（打擊）/`p_gp`（投球），fielding 的單一守位出賽數不寫進 gp；gameLog 每個 group 依角色寫一列（`ON CONFLICT(player_mlb_id, game_id, role)`，同場又投又打是兩列）；並處理目前層級/球隊（`players.level`/`level_year`：現役（`roster.is_active_player`，與首頁/退役頁分流同一定義）且有 currentTeam 時取其層級、年份為目標球季；否則（非現役或沒有 currentTeam）對 `season_stats` 最近一季呼叫 `highest_level_row()`（優先有出賽的列，再取最高層級），年份為該季。非現役球員的 currentTeam 仍是最後待過的球隊，照用會把 `level_year` 寫成今年）；所有層級欄位都經 `sport_to_tier_key()` 存 tier key；全歷史抓取時依 `failed_parts` 寫 `history_synced`。 |
| `_run_pipeline(db_path, roster_file, year, only_player=None, fetch_all_years=True, mode_label="Sync")` | 共用 orchestration：初始化 DB、判斷首次/非現役（`is_active=False` 的球員只在 update 模式跳過，`fetch_all_years=True` 時照樣重抓）、平行抓玩家、主執行緒逐一寫入；網路錯誤記一行 warning、程式錯誤記 traceback，結尾輸出已儲存/不完整/失敗人數。 |
| `sync_database(db_path, roster_file, only_player=None)` | 完整歷史同步薄包裝，`fetch_all_years=True`、當季為 `SEASON_YEAR`；含已退休球員。build.py 的 `sync`/`all`/`refresh --full-history` 使用。 |
| `update_database(db_path, roster_file, only_player=None)` | 日常快速更新薄包裝，僅更新當季（`SEASON_YEAR`）game logs。 |

### 4.3 `sync/extract.py` — live-feed 精簡 schema

| 函式 | 功能與定位 |
|---|---|
| `_extract_runners(play)` | 濃縮 PA-final runners movement 與守備 credit。 |
| `_condense_defense(d)` | 保留守備站位/球員必要欄位，移除 API boilerplate。 |
| `_condense_offense(d)` | 保留壘上進攻球員必要欄位。 |
| `_condense_nonpitch_event(ev, play, pitcher_id, batter_id)` | 將 pickoff/stepoff 等非投球事件轉成 `events_json` schema；`pitcher_id`/`batter_id` 為事件當下的實際投打（由 `_actual_participants` 傳入）。 |
| `_actual_participants(play)` | 回與 `playEvents` 一一對應的 `(實際投手, 實際打者)`：投手取事件 `defense.pitcher.id`（缺值退 `matchup.pitcher.id`）；打者只在 `offensive_substitution` 且 `position.code == "11"`（代打）時換人，代跑（"12"）不影響，打席起始打者是第一個代打事件的 `replacedPlayer`；換人事件缺 `position.code` 時視為非代打並記 warning。 |
| `_roster_code(players, player_id, field)` | 讀 `gameData.players["ID<id>"].<field>.code`（`pitchHand`/`batSide`），缺值回空字串。 |
| `_hand_for_pitch(matchup, players, pitcher_id, batter_id)` | 這顆球實際的 `(pitch_hand, bat_side)`：投打與 `matchup` 相同時沿用 `matchup` 值；否則取 `gameData.players` 登錄值，投手 "S"/缺值存 ""，左右開弓打者取投球手反邊（投球手為 "" 時存 ""）。 |
| `_pa_context(play)` | 擷取 PA-final WP、LI、drama 與上下文欄位。 |
| `extract_pitch_logs(game_data, player_id, role)` | 單次走訪 live feed，只取 `role` 那一側：`PITCHER` 取實際投手為本人的球與牽制事件，`BATTER` 取實際打者為本人的球與事件（對齊 Savant：打席中換投/代打時，被換下的人只有自己那段球、結果隨最後一球記給接手者；刻意不套用記錄規則 9.15(b)/9.16(h)）。每球 `batter_id`/`pitch_hand`/`bat_side` 為該球實際值，並帶 `at_bat_index`。回傳 `(pitches, nonpitch_events)`；此函式定義 `pitches_json` 與 `events_json` 的實際欄位契約。 |

### 4.4 `sync/statcast.py` — 逐球資料管線

| 函式 | 功能與定位 |
|---|---|
| `FetchedGame` | NamedTuple `(pitches, events, sport_level, is_final)`；一場比賽的抽取結果，`pitches`/`events` 以 `(mlb_id, role)` 為 key；`is_final=False` 表示抓取時比賽尚未完賽。 |
| `_games_to_fetch(cur, roster_ids)` | Phase 1：以 game_logs 的 (球員, 比賽, 角色) 列為單位，回 `{game_pk: [(mlb_id, role)]}`；條件只有 `pbp_version < PBP_EXTRACT_VERSION`，角色取自列本身。 |
| `_fetch_and_extract_game(game_pk, players_in_game)` | 每場只抓一次 live feed，依每一列的 `role` 抽 pitches/events，回 `FetchedGame`；抽不到就是空的，不改用另一個角色重抽。`is_final` 取自 `gameData.status.abstractGameState == "Final"`（進行中/延遲/暫停皆為 `Live`）；回應為空回 `None`。 |
| `_fetch_games(game_to_players)` | Phase 2：平行呼叫 `_fetch_and_extract_game`，回 `{game_pk: FetchedGame}`；抓取失敗的比賽不在結果內（`FetchError` 記一行 warning、其他例外記 traceback，結尾輸出失敗場數；兩者都不寫入，`pbp_version` 不變、下次重抓），未完賽的比賽照常回傳並記錄數量。 |
| `_write_pitch_logs(conn, fetched)` | Phase 3：寫回 `pitches_json`/`events_json`/`sport_level`；完賽的比賽才把 `pbp_version` 設為 `PBP_EXTRACT_VERSION`，未完賽的保留原值以便下次重抓；`WHERE` 含 `role`。回寫入的 (球員, 比賽, 角色) 列數。 |
| `_parse_expected_stats(exp_groups)` | expectedStatistics splits → `{(year, level): {xba, xslg, xwoba, xwobacon}}`；全為 0/缺值（MiLB）略過。 |
| `_compute_role_statcast(mlb_id, role, pitches_by_year_level, fetched, full_history)` | 一個角色的聚合：只對該角色有 MLB 逐球資料且 `needs_fetch()` 為真的年份抓 expectedStatistics（`group` 依角色），逐 `(year,level)` 呼叫該角色的 Statcast 入口。回 `({(year, level): {statcast, expected_stats}}, 成功抓取的年份)`；沒抓或抓取失敗的年份 `expected_stats` 為 None。 |
| `_compute_player_statcast(mlb_id, db_path, fetched, full_history)` | 平行唯讀 worker；`fetched` 為 `{role: 登記}`。對 `ROLES` 各讀一次該角色逐球資料，有資料的角色各自 `_compute_role_statcast`（不設門檻）。回 `(mlb_id, {role: results}, {role: 成功抓取的年份})`；沒有逐球資料的角色不在結果中。 |
| `_attach_statcast(cur, mlb_id, role, year, level, statcast_data, expected_stats)` | 把一個角色、一個 `(year,level)` 的結果寫進層級相符的 season_stats 列的 `role_field(role, "statcast")` / `role_field(role, "expected")`；另一角色的 key 不動；`level` 為空且該年多列時略過。 |
| `_aggregate_statcast(conn, db_path, roster_map, *, full_history=False)` | Phase 4：讀一次 `season_fetches`（`expected` / `p_expected`），平行 `_compute_player_statcast`，主執行緒依序 `_attach_statcast` 並依角色登記成功抓取的年份。 |
| `fetch_highlight_videos(conn, roster_ids, *, now_iso=None)` | Phase 6：找 `/content` 候選、抓取/抽取影片、寫 play video 與 processed cache；回新增/更新影片數。抓取失敗的比賽不標記已處理，下次仍是候選。 |
| `sync_statcast(db_path, roster_file, only_player=None, update_constants=False, full_history=False)` | 對外總入口：依序 Phase 1–4 → `sync_season_advanced()`（傳入 `PitchingConstants`）→ Phase 6。`update_constants` 強制重抓過去球季 FIP 常數；`full_history` 強制重抓過去球季 expectedStatistics / sabermetrics。 |

### 4.5 `sync/advanced.py` — 進階數據（FIP / WAR / wRC+ / xWPCT）

| 函式 | 功能與定位 |
|---|---|
| `_season_total_saber(saber_groups, target_group)` | 把 sabermetrics `stats[].splits[]` 轉成 `{year: stat}`，每年只取整季合計 split（沒有 `team`）；同年只有一筆直接採用，多筆卻無整季列則不寫。避免轉隊球員存成字母排最後那一隊的單隊值。 |
| `_fetch_season_saber(mlb_id, year)` | 平行 worker；抓一年 sabermetrics，hitting、pitching 兩個 group 都交給 `_season_total_saber`，回 `{role: 該年整季 stat}`（該 group 無資料的角色不在結果中）。不用 `seasons=a,b` 多年查詢：轉隊年份會少掉整季合計 split。 |
| `_level_wide_lg_era(constants)` | 取整層（`""`）lgERA 作為 xWPCT 分母；沒有常數回 `None`。 |
| `_mlb_advanced_fields(saber, role, lg_era)` | 一個角色要寫進 MLB 列的欄位：投球 `p_saber`/`fip`/`xfip`/`p_war`/`lg_era`/`xwpct`（FIP 缺值只寫 `p_saber`），打擊 `saber`/`war`/`wrc_plus`（四捨五入）。 |
| `_milb_fip_fields(stat_doc, league_name, constants)` | MiLB 投球列 `fip`/`lg_era`/`xwpct`；常數優先所屬聯盟、退整層；無局數或無常數回 `None`。 |
| `_load_rows(cur, roster_ids)` | 一次讀出名冊球員所有 season_stats 列 `(mlb_id, year, team, league, level, stat_json, fielding_json)`。 |
| `_fetch_all_saber(tasks)` | 以 `(mlb_id, year)` 為單位平行抓整季 sabermetrics，回 `{(mlb_id, year): {role: stat}}`；失敗的項目不在結果內（`FetchError` 記 warning、其他例外記 traceback）。 |
| `sync_season_advanced(conn, roster_ids, constants, *, full_history=False)` | 掃名冊球員每一列 season_stats（不看有沒有逐球資料、不看守位）：sabermetrics 只抓 `needs_fetch()` 為真的球員-年並登記；MLB 列對 `appeared_roles` 的每個角色以新抓或既有 `saber`/`p_saber` 重算欄位（每一隊的列都寫同一份，兩者皆無保留該角色舊值）；有投球的列需要的常數 slice 先 `constants.prefetch()`；MiLB 有投球的列自算 FIP/xWPCT，算不出來移除舊值。 |

---

## 5. render/ — 靜態網站渲染

### 5.1 Jinja 環境、filters 與 URL

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `render/__init__.py` | 無新函式 | Re-export `build_static_site`。 |
| `render/env.py` | `create_jinja_env(template_dir=None, base_url="/", site_url=SITE_URL)` | 建立 Jinja environment，註冊顯示 filters、level helper（`level_display`/`level_label` filter、`is_mlb`/`COMBINED_LEVEL` global、角色值 `PITCHER`/`BATTER` global）、站內連結（以 `base_url` 為前綴：`page_url`/`player_url`/`retired_player_url`/`static_url`、`RETIRED_INDEX_PATH`）與對外絕對 URL（以 `site_url` 為前綴：`absolute_url`/`site_url`）、headshot，以及後端生成的球種顯示資料、標籤 CSS 與「分類」欄 tooltip 文字（`pitch_group_tooltip`）等 globals。 |
| `render/filters.py` | `pitch_legend(rows)` | 將表格實際出現的球種依既有列序整理成中英對照 JSON；略過無中文對照與重複名稱，空結果回 `None`，供 tooltip 的 `data-legend`。 |
|  | `floatformat(value, digits=2)` | 固定位數格式，經 `round_half_up` 四捨五入；`None`、Jinja `Undefined`、無法解析（`.---`、`-.--`、`""`）顯示 `-`。也接受 API 數字字串（`".250"` → `0.250`），所以舊 DB 列與 `game_logs.stats_json` 的比率都走它。 |
|  | `default_if_none(value, fallback="-")` | 只在 `None` 時套 fallback，不把合法的 0 當空。 |
|  | `num_dash(value)` | 數值直接顯示，`None`/空字串顯示 `-`。 |
|  | `_json_html_safe(s)` | 轉義 `</`，避免 JSON 提前關閉 `<script>`。 |
|  | `tojson_safe(value)` | JSON serialize + HTML-safe `Markup`，供一般 script payload。 |
|  | `jsonld(value)` | 緊湊 JSON-LD serialize + HTML-safe `Markup`。 |
|  | `pct_fmt(value, digits=1)` | decimal fraction 以十進位乘 100 後經 `round_half_up` 轉百分比字串。 |
| `render/urls.py` | `headshot_cdn_urls(mlb_id, latest_level_is_mlb)` | 依最近實際出賽層級決定 MLB/MiLB CDN 主備 URL 順序。 |
|  | `player_page_path(mlb_id, is_retired=False)` | **球員頁路徑的唯一定義**（相對網站根目錄，如 `player/123/`、`retired/player/123/`）；連結、canonical/sitemap/JSON-LD、寫檔位置（`out_dir / path`）都由它推導。常數 `RETIRED_INDEX_PATH = "retired/"` 是退役列表頁路徑的唯一定義。 |
|  | `normalize_base_url(base_url)` | 站內連結前綴統一成 `/…/`；空字串（configure-pages 自訂網域時的 `base_path`）視為 `/`。 |
|  | `make_url_helpers(base_url)` | 回傳 `(page_url, player_url, retired_player_url, static_url)` 四個已綁 base URL 的 closure，供 Jinja globals。 |
|  | `make_url_helpers.page_url(path="")` | closure；任意站內路徑（如 `RETIRED_INDEX_PATH`）加上 base URL 前綴。 |
|  | `make_url_helpers.player_url(mlb_id)` | closure；`page_url(player_page_path(mlb_id))`。 |
|  | `make_url_helpers.retired_player_url(mlb_id)` | closure；`page_url(player_page_path(mlb_id, is_retired=True))`。 |
|  | `make_url_helpers.static_url(path)` | closure；產生靜態資產相對 URL。 |
|  | `make_absolute_url(site_url)` | 以對外正式網址建立絕對 URL closure，回 `(site_root, absolute_url)`；與站內 `base_url` 無關，本機 build 的 canonical 也指向正式站。 |
|  | `make_absolute_url.absolute_url(path="")` | closure；`site_url` + 相對路徑的 canonical 絕對 URL。 |

### 5.2 SEO 與 pitch-log 輸出

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `render/seo.py` | `player_display_name(player)` | 組合中文/英文顯示名稱。 |
|  | `player_description(player)` | 依球員、位置、球隊/層級產生 meta description。 |
|  | `index_structured_data(absolute_url, player_data)` | 建立首頁 WebSite + ItemList JSON-LD。 |
|  | `player_structured_data(absolute_url, player, is_retired=False)` | 建立球員 Person + BreadcrumbList JSON-LD。 |
|  | `write_robots(out_dir, sitemap_url)` | 寫 `robots.txt`。 |
|  | `write_sitemap(out_dir, urls)` | 寫 XML sitemap。 |
| `render/pitch_log.py` | `summarize_pitch_for_display(p, video_map=None, include_video=False)` | 將完整 pitch dict 投影成前端需要的精簡欄位；可按 `play_id` 附 mp4。 |
|  | `write_pitch_log_files(logs_by_year, out_dir, normalized_base_url, mlb_id, videos_by_game=None, role_dir=None)` | 每場輸出獨立延遲載入 JSON，並在 log 摘要附 `pitch_data_url`/`pitch_count`；`role_dir` 給雙角色球員的次要角色，檔案放 `data/pitchlogs/{mlb_id}/{role}/`，避免同一場又投又打時以 game_id 命名互相覆寫。 |

### 5.3 `render/pages.py` — payload 塑形與全站輸出

| 函式 | 功能與定位 |
|---|---|
| `_pick_display_stat(stats_current, player)` | 首頁/hero 代表列優先序：同隊 → 同目前層級 → 最高已出賽層級。 |
| `_statcast_row_qualifies(is_pitcher, s)` | 有 Statcast 即納入；沒有 Statcast 時，只有 `publishes_constants(level,year)` 涵蓋且已有計算 wRC+ 的打者列可納入 advanced 區。 |
| `_first_not_none(rows, field)` | 找同組列第一個實值，供只寫在其中一列的整季欄位。 |
| `_merge_level_rows(rows)` | 合併同 `(year,tier)` 的轉隊列：重加 counting/rates、IP-weighted FIP，取同層固定的 `lg_era` 重算 xWPCT，並取回 WAR/expected/saber/wRC+。 |
| `_pooled_year_pitches(logs)` | 從已解析 game logs 建 `{year: pitches}`，只採計例行賽 log（排除 `is_postseason`），跨層級合計時不重讀 DB。 |
| `_build_statcast_entries(is_pitcher, stats, logs)` | 建 `{year: entries}`；同層轉隊去重，多層級球季把原始 pitches pooling 後完整重算 `_combined`。`is_pitcher` 是該檢視的角色（雙角色球員的次要角色也走這裡），不是守位。 |
| `_page_roles(player, stats)` | 球員頁提供的角色檢視（主要角色在前）；只有投打兩個角色都有出賽（`appeared_roles`）才回傳兩個角色、頁面出現投手/打者切換。 |
| `_row_in_role(row, role)` | 某列（投影前原始列）是否列在該角色檢視：先看 `appeared_roles`，都沒有時看該角色自己的出賽數（`gp`/`p_gp`，如只代守沒打席），兩角色都沒出賽才兩邊都列。 |
| `_logs_in_role(logs_by_role, role)` | 雙角色球員某角色檢視要列的逐場紀錄：每場把兩個角色的 gameLog split 合成一列（PA/BF/IP/`gamesPlayed`）交給 `_row_in_role`；排除 gameLog API 在有投球的比賽另回的 0 PA hitting split，代守/代跑（當場沒投球）仍留在打者檢視。 |
| `_fielding_in_role(fielding, role)` | 雙角色球員某角色檢視要列的守備列：依守位 `primary_role(position)` 分流（`P` 歸投手，其餘含 `DH` 歸打者）。 |
| `_build_role_view(stats, logs, role, player, year, fielding, hero_fallback=False)` | 一個角色檢視的樣板變數（成績表年度分組、生涯、hero 代表列、本季合計、逐場、守備、走勢圖、Statcast）；`logs`／`fielding` 由呼叫端先篩成該角色（`_logs_in_role`／`_fielding_in_role`）；`hero_fallback` 讓次要角色在當季沒出賽時 hero 改顯示最近一季（`latest_team_stat_year`）。 |
| `_inline_css_imports(css_path, seen=None)` | 遞迴展開 CSS `@import`，用 `seen` 防循環且維持 cascade 順序。 |
| `_bundle_css(static_out_dir)` | build 時把 `style.css` import graph 壓成單檔，減少瀏覽器 request waterfall。 |
| `build_static_site(db_path, output_dir, base_url="/", roster_file=None, update_constants=False, site_url=SITE_URL)` | 唯一全站入口：重建 output、複製/壓平 static、初始化 Jinja/DB、載入 roster bundles、以 `BattingConstants.for_level` 標注 wRC+，再對每列 season_stats 呼叫 `positions.project_role(row, primary_role(position))`（之後一律讀不帶前綴的 key；雙角色球員投影前先深拷貝原始列給次要角色檢視用），切現役/退役、組球員/圖表/pitch-log payload、渲染所有 HTML、寫 sitemap/robots/`.nojekyll`。 |

`build_static_site()` 會刪除並重建指定 `output_dir`；呼叫端必須傳入明確且安全的輸出
路徑。純資料塑形應優先放進上面的 `_merge_*` / `_build_*` helper，避免讓主入口繼續膨脹。

---

## 6. graph/ — 圖表資料

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `graph/__init__.py` | 無函式 | 圖表 payload 套件標記。 |
| `graph/movement.py` | `compute_pitch_movement_chart(pitches, max_points=COMPUTE_MAX_POINTS)` | 產生投手逐球 HB/IVB、球種及可用的球速/轉速點位，並按上限降採樣；單層級與跨層級都直接從原始 pitches 計算；球種佔比走 `pitch_type_shares`（分母為降採樣前的點數）。每個點輸出為固定順序的 `[type,hb,ivb,velo,spin]` 陣列（缺 velo/spin 補 `None`）以省 payload，球種中英文名改由前端 `pitch_type_display` global 查表。 |
| `graph/plinko.py` | `_empty_plinko_nodes()` | 建立固定 count nodes 的零值 payload。 |
|  | `_empty_plinko_edges()` | 建立固定 count transitions 的零值 payload。 |
|  | `compute_pitch_plinko(pitches, *, split_field, split_specs)` | 依打者/投手慣用手 split，先以 `filter_known_pitch_events` 排除未知/非投球事件、並只保留 pre-count 在圖上的球，再累計 count node 與 transition edge，輸出前端 Pitch Plinko 結構；整體與各節點的球種佔比都走 `pitch_type_shares`（節點內同顆數依整體用量排序）。 |
| `graph/season_trend.py` | `_merge(acc, part)` | 逐場合併：數字相加、清單串接到 *acc* 的清單；其他型別丟 `TypeError`，強迫新欄位明確決定合併方式。 |
|  | `_Totals.empty()` / `_Totals.of_game(log)` / `_Totals.add(other)` | 逐場累積總帳（dataclass），分 `box`（gameLog 計數）、`agg`（`aggregate_pitches`）、`pa`（`compute_pa_outcome_totals`）三本帳；`of_game` 每場只彙整自己的球，`add` 只併進 `empty()` 建出的總帳，不改動被併入的單場。 |
|  | `TrendMetric(key, label, compute)` | 走勢圖指標定義（frozen dataclass）；`compute(totals)` 只把總帳交給 `stats/` 的 compute_*，不寫公式。`PITCHER_TREND_METRICS` / `BATTER_TREND_METRICS` 為公式表，`*_TREND_STAT_OPTIONS` 由它產生。 |
|  | `_cumulative_points(games, metrics, badge_year=None)` | 依序把 `(log, _Totals)` 併進總帳，每場對總帳算一次全部指標；`badge_year` 有值時每點附層級（All Levels 用）。 |
|  | `_build_year_entry(year_logs, year, metrics)` | 一季：每場彙整一次，依層級分組建立各層級序列；多層級時再以同一批單場總帳建立不中斷的 `_all` 序列。 |
|  | `_build_trend_by_year(logs_by_year, metrics)` | 逐年呼叫 `_build_year_entry`；只採計有日期的例行賽 game log（`not log.is_postseason`）。 |
|  | `build_pitcher_trend_by_year(logs_by_year)` | 對外投手入口，回 `year → level/_all → payload`，指標見 `PITCHER_TREND_METRICS`。 |
|  | `build_batter_trend_by_year(logs_by_year)` | 對外打者入口，指標見 `BATTER_TREND_METRICS`。 |

圖表模組不再提供 `combine_*`。需要跨層級時，應傳入跨層級原始 pitches/game logs
重新計算，而不是合併已經聚合的圖表結果。

---

## 7. util/ — 通用工具

| 檔案 | 所有函式 / method | 功能與定位 |
|---|---|---|
| `util/__init__.py` | 無函式 | 通用工具套件標記。 |
| `util/dates.py` | `parse_date(text)` | 安全解析 ISO 日期字串為 `date`；空值/格式錯誤回 `None`。`TW_TZ` 常數也在此。 |
| `util/json.py` | `loads_json(text, default)` | 安全 JSON decode；輸入為空或壞 JSON 時回指定 default。 |
|  | `loads_json_dict(text)` | `loads_json(...,{})` 的 dict 專用包裝。 |
|  | `loads_json_list(text)` | `loads_json(...,[])` 的 list 專用包裝。 |
|  | `dumps_json(value)` | 統一 JSON serialize 設定，保留中文。 |
| `util/numbers.py` | `safe_float(value, default=None)` | 安全轉有限 float；空值、無法解析或 NaN/inf 回 default。 |
|  | `safe_int(value, default=None)` | 安全轉 int；接受整數、整數字串等 `int()` 可處理的值，失敗回 default。 |
|  | `_round_rational(p, q, digits)` | 精確分數 p/q 以純整數運算四捨五入；`ratio`/`round_half_up` 共用。 |
|  | `_to_fraction(value)` | 精確轉 `Fraction`；float 以最短 repr 為準。 |
|  | `round_half_up(value, digits)` | 全專案唯一的捨入實作：四捨五入（負數遠離零），接受 int/Fraction/Decimal/float，float 以最短 repr 為準。 |
|  | `ratio(num, den, digits=3)` | 精確除法後四捨五入（整數輸入走純整數路徑）；零/缺分母回 `None`。 |
|  | `mean(values)` | 過濾 `None` 後平均；空樣本回 `None`。 |
|  | `mean_round(values, digits=1)` | `mean()` 後經 `round_half_up` 捨入。 |
| `util/obj.py` | `Obj.__getattr__(key)` | 將 dict key 暴露為 attribute；缺 key 回 `None`，方便模板讀稀疏欄位。 |
|  | `Obj.__setattr__(key, value)` | attribute assignment 寫回 dict key。 |
| `util/units.py` | `height_to_cm(height_str)` | 解析 `6' 2"` 類身高並轉公分。 |
|  | `lbs_to_kg(weight_lbs)` | 磅轉公斤，經 `round_half_up` 捨入到一位。 |
| `util/log.py` | `describe_exc(exc)` | `"TypeName: message"`；log 例外時帶上類型，`KeyError` 這類 `str(e)` 只剩 key 的也看得懂。 |
|  | `_use_color(stream)` | TTY 才輸出 ANSI 顏色；`NO_COLOR` 強制關閉、`FORCE_COLOR` 強制開啟。 |
|  | `ColorFormatter.__init__(color)`<br>`ColorFormatter.format(record)` | `HH:MM:SS LEVEL module message` 格式，logger 名稱去掉 `site_builder.` 前綴，WARNING/ERROR 上色；先補欄寬再上色，避免 ANSI 碼讓欄位對不齊。 |
|  | `_ProblemCollector.__init__()`<br>`_ProblemCollector.emit(record)` | logging handler；以 (等級, logger, 訊息模板) 統計 WARNING/ERROR 次數並保留第一則範例。 |
|  | `_DropUrllib3RetryWarnings.filter(record)` | 濾掉 urllib3 自己的 `Retrying (...)` 訊息，重試統一由 `api.client._LoggingRetry` 記錄。 |
|  | `setup_logging(level=logging.INFO)` | CLI 進入點呼叫：root logger 掛彩色 stderr handler 與摘要統計；重複呼叫不重複掛。 |
|  | `log_run_summary()` | 執行結束時印出 WARNING/ERROR 分類統計（次數多到少）；只報告，不影響 exit code。 |

---

## 8. 頂層模組

### 8.1 `site_builder/__init__.py`

無函式；只提供 package docstring。

### 8.2 `constants.py`

| 函式 | 功能與定位 |
|---|---|
| `_auto_season_year()` | 3 月起使用當年，1–2 月仍視為上一球季；用來初始化 `SEASON_YEAR`。 |
| `is_season_in_progress(year)` | `year >= SEASON_YEAR`；「當季」的唯一定義，`league_constant/policy.py` 與 `db/season_fetches.py` 共用。 |
| `_build_pitch_tag_css()` | 從 `PITCH_TYPES` 每代碼各自的配色產生 `.pitch-{code}` / `.pitch-{group}` 標籤規則（同色代碼如 FF/FA、CU/CB 共用一條 selector），避免 CSS 另行手抄球種配色。 |
| `_build_pitch_tag_css._rule(selector, bg, text)` | closure；把單一 selector 的底色/文字色轉成一條 CSS rule。 |

此檔其餘內容是路徑、`SITE_URL`（對外正式網址，全站唯一寫死網域處，見 `docs/custom_domain.md`）、timeouts/retry/workers、`SEASON_YEAR`、固定 wOBA weights、
pitch code、球種家族/中英名稱/配色、count/split/plinko、pitch-type groups、batted-ball 與
`COUNTING_FIELDS`（由 `SHARED_/HITTING_/PITCHING_COUNTING_FIELDS` 組成，分組存在 `COUNTING_FIELD_GROUPS`）。已不再維護年度 RA/9、FIP 或 TJStats 對照表；季別/聯盟環境
由 `league_constant/` 取得，TJStats 網站拼法放在 `api/tjstats.py`，層級與 roster
規則分別留在 `levels.py`、`roster.py`，守位 → 角色對照留在 `positions.py`。

### 8.3 `levels.py`

`Tier` 是 frozen dataclass，沒有自訂 method。DB 的層級欄位一律存 tier key。

公開常數：
- `MLB_KEY = "MLB"`：SQL 參數用（`WHERE sport_level = ?`）。
- `MINORS_KEY = "Minors"`：層級未知時的預設值（須與 `db/schema.py` 的 `players.level DEFAULT` 一致）。
- `COMBINED_LEVEL = "_combined"`：Statcast 年度合計列的 sentinel，也註冊成 Jinja global。
- `ALL_LEVELS = "_all"`：走勢圖跨層級序列的 key，也是前端「All Levels」選項的值（JS 端寫死同一字串）。
- `SCHEDULE_SPORT_IDS`：由 `TIERS` 推導的 sportId tuple（MLB + 現行附屬小聯盟，不含已廢除的 A-/ROA、WIN、Minors），供 `api/schedule.py::get_next_game` 查未來賽程。

| 函式 | 功能與定位 |
|---|---|
| `resolve_tier(raw)` | 將現代/舊制/別名層級解析成 `Tier`；未知回 `None`。 |
| `level_rank(raw)` | 回 hierarchy rank，數字越小層級越高；未知值用 50。 |
| `level_display(raw, year)` | 2021+ 顯示現代名稱、2020- 顯示舊制名稱（已廢除的 `A-`/`ROA` 一律顯示舊制名）；sentinel/未知值原樣回傳。全站唯一產生舊制名稱的地方。 |
| `level_label(raw, year)` | 顯示用標籤：`COMBINED_LEVEL`/`ALL_LEVELS` 回 `All Levels`，其餘同 `level_display`；註冊成 Jinja filter。 |
| `is_level(raw, *tier_keys)` | `raw`（任何拼法）是否屬於任一 `tier_keys`；`tier_keys` 不是合法 tier key（打錯字、傳舊制名稱）或為空時 `ValueError`；未知層級回 `False`。 |
| `is_mlb(raw)` | `is_level(raw, MLB_KEY)` 的捷徑；全站唯一的 MLB 判斷，也註冊成 Jinja global。 |
| `is_milb(raw)` | 附屬小聯盟（AAA/AA/A+/A/A-/ROA/ROK）；不含 `WIN`、`Minors` 與未知層級，所以不等於 `not is_mlb()`。 |
| `to_tier_key(raw)` | 任何拼法 → tier key；未知原樣回傳、`None` 回空字串。 |
| `sport_to_tier_key(sport)` | API sport 物件 → tier key，依序用 `id`、`abbreviation`、`name` 解析；都對不到時回 API 的 `abbreviation`。所有 DB 層級欄位的唯一寫入入口。 |

### 8.4 `roster.py`

公開常數：
- `STATUS_ACTIVE` / `STATUS_INJURED` / `STATUS_RESTRICTED` / `STATUS_INACTIVE` / `STATUS_OTHER`：`categorize_roster_status()` 的回傳值；字串同時是前端 `.status-pill.<category>` 的 CSS class，其他模組比對狀態時一律 import 這些常數。

| 函式 | 功能與定位 |
|---|---|
| `parse_roster_from_file(filepath)` | 讀 roster JSON 的 `players`；任何錯誤記 log 並回空列表。 |
| `build_roster_map(roster_file)` | 建 `{mlb_id: player_config}` 快速索引。 |
| `categorize_roster_status(code, is_active_entry, player_is_active)` | 將 MLB roster code 分成 `active/injured/restricted/inactive/other`。 |
| `is_national_team_tx(tx)` | 交易描述是否為 Chinese Taipei 國家隊徵召；不算 affiliated activity。 |
| `is_active_player(player, stats, year)` | 當年有 season row 或合格交易即視為站台現役；只剩國家隊徵召者歸退役頁。 |

### 8.5 `positions.py`

守位 → 角色的唯一權威表。`position` 為 `players.position`（`primaryPosition.abbreviation`）；
其他模組**不得**自行比對 position 字串（如 `== "P"`），一律 import 本模組。

公開常數：
- `PITCHER = "pitcher"` / `BATTER = "batter"`：角色值，同時是 `game_logs.role` 的值與 `sync/extract.py::extract_pitch_logs()` 的 `role` 參數。
- `ROLES = (BATTER, PITCHER)`：逐角色處理時的固定順序。
- `PITCHER_POSITIONS = frozenset({"P"})`：代表投手的守位縮寫。
- `ROLE_SPLIT_FIELDS = ("gp", "statcast", "expected", "saber", "war")`：`season_stats.stat_json` 中打擊/投球同名、依角色拆開存的 key。

| 函式 | 功能與定位 |
|---|---|
| `primary_role(position)` | 回 `PITCHER` 或 `BATTER`；空字串（players 表無該球員）或其他守位一律視為打者。只決定 render 顯示哪個角色，sync 端的資料一律依 API group / 出賽紀錄決定角色。 |
| `is_pitcher_position(position)` | `primary_role(position) == PITCHER` 的捷徑；`db/bundles.py` 的 `player.is_pitcher` 經由它判斷。 |
| `role_for_stat_group(group_name)` | `stats[].group.displayName`（不分大小寫）→ 角色：`hitting` → `BATTER`、`pitching` → `PITCHER`，其他（`fielding`）→ `None`。 |
| `stat_group_for_role(role)` | `role_for_stat_group` 的反向，API `group=` 參數用（expectedStatistics、sabermetrics 解析）。 |
| `role_field(role, name)` | 拆分欄位的實際 key：`BATTER` 回 `name`、`PITCHER` 回 `p_<name>`（沿用既有 `p_hr`/`p_babip` 慣例）。 |
| `project_role(row, role)` | render 專用：`role == PITCHER` 時把每個 `p_<name>` **無條件**覆寫到 `<name>`（缺值即 None，避免只打擊的列把打擊 `gp` 帶進投手頁）；`BATTER` 不動。就地修改。 |

---

## 9. build.py — CLI

| 函式 | 功能與定位 |
|---|---|
| `cmd_sync(args)` | lazy import 並呼叫 `sync_database()`。 |
| `cmd_build(args)` | lazy import 並呼叫 `build_static_site()`。 |
| `cmd_statcast(args)` | lazy import 並呼叫 `sync_statcast()`。 |
| `cmd_refresh(args)` | 日常管線：`update_database()`（`--full-history` 時改 `sync_database()`）→ `cmd_statcast()` → `cmd_build()`。 |
| `cmd_all(args)` | 首次/回補管線：設定 `full_history=True` 後呼叫 `cmd_refresh()`；單一球員模式會警告 build 仍渲染全 roster。 |
| `main()` | 建立 argparse 子命令/共用參數、驗證 command，呼叫 `setup_logging()` 後 dispatch `args.func(args)`，結束時（含例外）呼叫 `log_run_summary()`。 |

---

## 10. 完整性核對方式

本文件把「函式」定義為 AST 中的 `FunctionDef`/`AsyncFunctionDef`，因此 class
method 和 closure 也計入。第 1～8 章目前應有：

| 章節 | Python 檔案 | 函式 / method |
|---|---:|---:|
| `api/` | 9 | 24 |
| `db/` | 8 | 18 |
| `league_constant/` | 4 | 21 |
| `stats/` | 74 | 120 |
| `sync/` | 6 | 34 |
| `render/` | 7 | 36 |
| `graph/` | 4 | 13 |
| `util/` | 7 | 26 |
| 頂層 `__init__/constants/levels/positions/roster` | 5 | 20 |
| **合計** | **124** | **312** |

修改程式後可用下列唯讀檢查快速找出漏列：

```bash
find site_builder -type f -name '*.py' | sort
rg -n '^(async )?def |^ +((async )?def )' site_builder
```

`rg` 適合人工檢視；要精確包含任意縮排 closure，應使用 Python `ast.walk()`。

---

## 11. 新增功能時的掛接位置

| 需求 | 新函式通常放哪裡 | 還要掛到哪裡 |
|---|---|---|
| 新 MLB endpoint | `api/` 對應語意模組 | `api/__init__.py`（若需公開）與 `sync/` 呼叫點 |
| 新 DB table/query | `db/schema.py` + 專責 `db/*.py` | sync/render 的 transaction 邊界 |
| 新逐季/逐聯盟環境常數 | `league_constant/` 專責 supply chain | cache schema、`RefreshPolicy`、resolver 與 stats 呼叫參數 |
| 新球季衍生率 | `stats/batting/` 或 `stats/pitching/` | `core/annotate.py`；需要合計時也檢查 `COUNTING_FIELDS` / `aggregate.py` |
| 新逐球分類 | `stats/core/pitches.py` 或專責 stats 模組 | pitcher/batter Statcast 入口及相關 table |
| 新打擊紀律率 | `stats/discipline/` | `discipline_metrics()` 或只掛球種表，依統計層級決定 |
| 新球種表 | `stats/tables/` | pitcher/batter Statcast 入口、split 組裝與模板 |
| 新圖表 | `graph/` | `render/pages.py` payload 與前端模板/JS |
| 新頁面輸出 | `render/pages.py` 或拆出的 render helper | SEO、URL helper、sitemap 與模板 |
| 新 API 欄位 | `sync/field_maps.py` 或 `sync/extract.py` | DB JSON schema 消費端與本文件 |

最重要的資料正確性原則：跨球隊/層級合併率或百分位時，優先合併原始 counting
stats/pitches 後重新計算；不要假設一個共同權重能正確合併所有比率。

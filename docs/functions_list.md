# Taiwan MLB Tracker 函式索引

> 最後核對：2026-07-30
>
> 範圍：`site_builder/` 全部 119 個 Python 檔案，以及 CLI `build.py`。
> 第 1～8 章共盤點 254 個 function/method，包含公開函式、底線開頭的內部 helper、
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
├─ sync / update
│  └─ sync.players → api.* → db.*
├─ statcast
│  └─ sync.statcast → api.games/content/stats
│                   → sync.extract
│                   → league_constant.pitching
│                   → stats.* + graph.*
│                   → db.*
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
| `api/__init__.py` | 無函式 | Re-export API 公開入口；呼叫端可從 `site_builder.api` 匯入。 |
| `api/client.py` | `_RateLimiter.__init__(rate)`<br>`_RateLimiter.acquire()` | 建立 process-wide、thread-safe 節流器；`acquire()` 計算下一個請求時槽並在需要時阻塞。只供本模組使用。 |
|  | `_build_session()` | 建立帶連線池與 429/502/503/504 retry/backoff 的 `requests.Session`。 |
|  | `_session()` | 從 thread-local 取出 session；每個 worker thread 第一次呼叫時才建立。 |
|  | `_request(url, timeout=API_TIMEOUT)` | 所有 HTTP GET 的共同底層：先節流，再使用 thread-local session，最後 `raise_for_status()`。 |
|  | `get_json(url, timeout=API_TIMEOUT)` | 對外 JSON GET；回傳解析後 dict，錯誤交由呼叫端處理。 |
|  | `get_text(url, timeout=API_TIMEOUT)` | 對外文字 GET；供 TJStats HTML 解析使用，沿用同一套節流與 retry。 |

### 1.2 MLB Stats API 與 TJStats

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `api/content.py` | `get_game_content(game_pk)` | 取得 `/game/{pk}/content`；失敗記 warning 並回 `{}`。 |
|  | `extract_play_videos(content)` | 從 highlights 找出 `guid == playId` 且具有 `.mp4` playback 的片段，回傳 `{play_id,title,mp4_url}` 列表。 |
| `api/games.py` | `get_game_play_by_play(game_pk)` | 取得單場 v1.1 `withMetrics` 完整 live feed；供 `sync.extract` 擷取逐球資料。 |
|  | `get_game_sport_level(game_pk)` | 用 fields-filtered live feed 只查比賽層級，並經 `sport_obj_to_abbr()` 正規化；舊 DB 回補層級時使用。 |
| `api/league_stats.py` | `fetch_team_league_map(sport_id, year)` | 回傳 `{team_id: league_name}`；用來把球隊投球總量分到各聯盟。 |
|  | `fetch_team_pitching_totals(sport_id, year)` | 回傳每隊 HR、BB、HBP、K、ER、outs；是反推聯盟 FIP 常數的原始資料。 |
| `api/players.py` | `get_player_profile(mlb_id)` | 取得 profile、current team、transactions、rosterEntries，整理姓名、身體資料、守備位置、慣用手、現役與 roster 狀態、目前球隊/層級。 |
| `api/schedule.py` | `get_next_game(team_id)` | 查未來七天第一場 Preview 比賽，轉成台灣時區的下一場賽事摘要；沒有賽事或失敗時回 `None`。 |
| `api/stats.py` | `get_player_stats(mlb_id)` | 同時查 MLB/MiLB `yearByYear` 的 hitting/pitching/fielding，回傳所有球季基礎數據。 |
|  | `get_player_advanced_stats(mlb_id, years=None)` | 逐年查 MLB/MiLB `seasonAdvanced`；供補入 BABIP、P/PA 等進階球季欄位。 |
|  | `get_game_logs(mlb_id, season)` | 同時查指定球季 MLB 與 MiLB gameLog；升降級球員不會漏掉任一端。 |
|  | `get_player_sabermetrics(mlb_id, years=None)` | 查 MLB-only sabermetrics（FIP、xFIP、WAR、wRC+）原始 splits。 |
|  | `get_player_expected_stats(mlb_id, years=None, group="pitching")` | 查 MLB-only expectedStatistics（xwOBA、xBA、xSLG）；`group` 決定打擊或投球。 |
| `api/tjstats.py` | `fetch_park_factors(level, year)` | 解析 TJStats park-factor 表，回 `{team_name: {pf_final, league}}`；未知層級或失敗回 `{}`。TJStats 專屬的 `TJSTATS_LEVEL_PARAMS` / `PF_LEVEL_PARAM` / `LC_LEVEL_CODE` 也定義在此。 |
|  | `fetch_league_constants(year)` | 解析 TJStats league-constants 表，回 `{(level_code, league): {lg_woba, lg_r_pa}}`；由 `league_constant.batting` 與 park factor join 後供 wRC+。 |

實作判斷：新增 MLB endpoint 放在語意對應檔案；只有共用 HTTP 行為才放
`client.py`。API 函式不要直接寫 DB，也不要在此計算玩家統計量。

---

## 2. db/ + league_constant/ — 持久層與聯盟環境

### 2.1 `db/` — 純 SQLite row access

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `db/__init__.py` | 無函式 | 套件說明，不做 re-export；此層只讀寫資料表，不抓外部資料或計算統計。 |
| `db/schema.py` | `init_db(conn)` | 建立 players、season_stats、game_logs、play-by-play、聯盟常數/影片快取表與索引；以可重複執行的 `CREATE IF NOT EXISTS` 和容錯 `ALTER TABLE` 做正向 migration。新增的 `lg_era` 欄位預設 0，會由 pitching constant loader 視為 cache miss 自動修復。 |
| `db/season_stats.py` | `load_season_row(cur, mlb_id, year, team_name)` | 讀單一 `(球員, 年, 球隊)` 球季列並解析 JSON；不存在時回空 dict。 |
|  | `save_season_row(cur, mlb_id, year, team_name, league_name, sport_level, stat_json, fielding_json)` | 以同一複合 key upsert 球季數據及守備 JSON。 |
|  | `players_with_existing_stats(conn)` | 回傳已有 season_stats 的 MLB ID set；refresh 用它判定新球員是否必須完整回補。 |
| `db/players.py` | `warn_orphaned_players(conn, roster_ids)` | 找出 DB 有但 roster 已移除的球員並印出警告/清理 SQL；只診斷，不自動刪除。 |
|  | `get_cached_is_active(cur)` | 批次讀取 `{mlb_id: bool(is_active)}`，讓同步管線可跳過已知非現役球員。 |
| `db/game_logs.py` | `load_all_pitches_for_player(cur, mlb_id)` | 合併玩家所有 `pitches_json` 成 `{(year, sport_level): pitches}`；舊列缺層級時只在可唯一推定時補入。 |
| `db/bundles.py` | `load_player_bundle(cur, player_row)` | build 的主要讀取入口；建立 `(player, stats, logs)` 三元組，解析 JSON/date、計算年齡/status/headshot 層級、排序球季列，並相容沒有 `pitches_json` 的舊 DB。 |
| `db/play_videos.py` | `save_play_videos(cur, game_pk, videos, now_iso)` | 將一場比賽的 play-level mp4 URL upsert 到 `play_videos`；不自行 commit。 |
|  | `mark_content_processed(cur, game_pk, videos_found, now_iso)` | 記錄 `/content` 已處理及影片數；不自行 commit。 |
|  | `content_fetch_candidates(cur, roster_ids, retry_cutoff_date)` | 回傳需要初抓或近期零影片重試的 MLB game PK。 |
|  | `load_video_map(cur)` | build 時載入 `{game_pk: {play_id: mp4_url}}`；舊 schema 沒有表時安全回 `{}`。 |

### 2.2 `league_constant/` — 聯盟環境供應層

這是唯一同時抓外部資料、計算環境值並寫 SQLite cache 的層。`stats/` 只接收已解
出的常數，`db/` 只保留 schema 與一般 row access。

| 檔案 | 所有函式 / method | 功能與定位 |
|---|---|---|
| `league_constant/__init__.py` | 無新函式 | Re-export batting/pitching resolver、one-shot helper 與 cache policy。 |
| `league_constant/policy.py` | `should_use_cache(year, *, policy, force_refresh)` | 共用 cache 決策；`force_refresh` 永遠略過 cache，`ACCUMULATES_IN_SEASON` 對當季重抓，`FINAL_ONCE_PUBLISHED` 一旦有值即重用。`RefreshPolicy` 是 Enum，沒有自訂 method。 |
| `league_constant/pitching.py` | `_load(conn, level, year)` | 讀 `{league_name: LeagueFipConstant}`；忽略 `lg_era <= 0` 的舊 cache row，促使自動重抓。 |
|  | `_save(conn, level, year, data)` | upsert 每聯盟與 `""` 層級總體的 FIP constant + lgERA，並 commit。 |
|  | `_fetch_and_compute(level, year)` | level→sportId，抓球隊 totals/league map，按聯盟及整層加總後呼叫 `compute_league_fip_constant()`。 |
|  | `get_pitching_constants(conn, level, year, *, force_refresh=False)` | 單次查詢入口；依累積型 policy 讀 cache/重抓，失敗時退回舊 cache。 |
|  | `PitchingConstants.__init__(conn, *, force_refresh=False)` | 建立單次 sync 使用的 resolver 與 `(level,year)` 記憶體 cache。 |
|  | `PitchingConstants.for_level(level, year)` | 多 slice 查詢入口；同一次 sync 每個 `(level,year)` 最多解析一次。 |
| `league_constant/batting.py` | `publishes_constants(level, year)` | 判斷 TJStats 是否涵蓋該層級/年度；render 也用它決定 wRC+ 欄位是否可能存在。 |
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
| `core/formatting.py` | `fmt_avg(value)` | 格式化棒球小數，`0.333 → ".333"`；`None` 原樣保留。 |
| `core/selectors.py` | `has_appearance(stat)` | gp/pa/ab/bf/IP 任一大於 0 即視為真正出賽。 |
|  | `highest_level_row(stats)` | 優先從有出賽列中依 `level_rank` 找最高層級列；全無出賽才退回所有列。 |
|  | `highest_level(stats)` | 回傳最高層級的 canonical tier key，而非時代顯示字串。 |
| `core/pa_outcomes.py` | `compute_pa_outcome_totals(pa_final)` | 從打席結束球彙整 wOBA numerator/denominator、hits、AB；排除故意四壞、犧牲觸擊與非 PA 跑壘事件。 |
| `core/aggregate.py` | `sum_counting(stats, result)` | 依 `COUNTING_FIELDS` 加總；全部為 `None` 才保留 `None`，否則缺值視為 0。會修改 `result`。 |
|  | `compute_rate_stats(agg)` | 從合計列重算 AVG/OBP/SLG/OPS 與 ERA/WHIP；會修改 `agg`。 |
|  | `aggregate_stats(stats)` | 建立新 `Obj`，加總 counting stats、以 outs 正確合併 IP，再計算 rate stats。 |
| `core/annotate.py` | `_fill(s, field, value)` | value 非 `None` 才寫入欄位；是衍生欄位的共同 guard。 |
|  | `annotate_row(s)` | 在單列缺值時補打者/投手衍生數據，絕不覆蓋 API 既有值；會修改輸入列。 |
|  | `annotate_computed_stats(all_stats)` | 為每列設定 `np = pitches` 並呼叫 `annotate_row()`；回傳同一列表。 |
| `core/career.py` | `compute_career(stats, level_filter=None)` | 跨球季合計，選擇性篩 MLB/MiLB；附球隊清單與年份範圍。 |
|  | `compute_season_combined(stats, year)` | 同一年跨球隊/層級計數合計。 |
|  | `compute_year_groups(all_stats)` | 組成最近年度優先的 `{year, summary, rows, multi}`，供模板顯示年度總列與逐隊列。 |
| `core/pitches.py` | `is_swing(p)` / `is_whiff(p)` / `is_called_strike(p)` | 依 MLB result code 判斷揮棒、揮空、主審好球。 |
|  | `is_in_zone(p)` / `is_out_of_zone(p)` | 依 zone 1–9 / 11–14 分類；缺 zone 兩者皆 False。 |
|  | `is_unknown_pitch_type(pitch_type, pitch_name=None)` | 判斷空值、UN、UNKNOWN placeholder。 |
|  | `filter_known_pitch_events(pitches)` | 球種細分表的共同前處理：剔除未知球種事件。 |
|  | `pre_count_tuple(p)` / `post_count_tuple(p)` | 安全取得投球前/後 `(balls, strikes)`；不完整或無法轉 int 時回 `None`。 |
|  | `count_label(count)` | `(balls, strikes)` 轉 `"B-S"`。 |
|  | `ensure_pre_strikes(pitches)` | 為舊快取逐球回填 `pre_balls/pre_strikes`；依 game/PA 邊界重置，會原地修改 pitch dict。 |
|  | `aggregate_pitches(pitches)` | 單次掃描建立 swings、whiffs、zone、in-play、PA-final、BBE、球路類型、barrel/hard-hit 與 spray 等共用聚合。 |

### 3.2 `stats/batting/` — 打者球季公式

`batting/__init__.py` 無函式。下列函式都是小型純函式；分母無效或必要輸入缺失時
回 `None`，避免模板把「不可計算」誤顯示為 0。

| 檔案 | 唯一函式 | 公式 / 定位 |
|---|---|---|
| `ab_per_hr.py` | `compute_ab_per_hr(ab, hr)` | AB ÷ HR。 |
| `avg.py` | `compute_avg(hits, ab)` | H ÷ AB。 |
| `babip.py` | `compute_babip(hits, hr, ab, so, sac_flies=0)` | `(H−HR)/(AB−SO−HR+SF)`；打者與投手對手 BABIP 共用。 |
| `bb_pct.py` | `compute_bb_pct(bb, plate_appearances)` | BB ÷ PA。 |
| `go_ao.py` | `compute_go_ao(ground_outs, air_outs)` | GO ÷ AO。 |
| `iso.py` | `compute_iso(slg, avg)` | SLG − AVG。 |
| `k_pct.py` | `compute_k_pct(so, plate_appearances)` | SO ÷ PA/BF，由呼叫端決定分母語意。 |
| `obp.py` | `compute_obp(hits, bb, hbp, ab, sac_flies)` | `(H+BB+HBP)/(AB+BB+HBP+SF)`。 |
| `ops.py` | `compute_ops(obp, slg)` | OBP + SLG。 |
| `p_per_pa.py` | `compute_p_per_pa(pitches, plate_appearances)` | 用球數 ÷ PA/BF。 |
| `sb_pct.py` | `compute_sb_pct(sb, cs)` | SB ÷ (SB+CS)，回傳棒球小數字串。 |
| `slg.py` | `compute_slg(tb, ab)` | TB ÷ AB。 |
| `xbh.py` | `compute_xbh(doubles, triples, hr)` | 2B + 3B + HR；三項皆為 0/空時回 `None`。 |

### 3.3 `stats/pitching/` — 投手球季與出手點公式

`pitching/__init__.py` 無函式。

| 檔案 | 所有函式 | 公式 / 定位 |
|---|---|---|
| `era.py` | `compute_era(earned_runs, ip_actual)` | `9×ER/IP`；`ip_actual` 必須是真實分數局數。 |
| `whip.py` | `compute_whip(hits_allowed, bb, ip_actual)` | `(H+BB)/IP`。 |
| `k_per_9.py` | `compute_k_per_9(so, ip_actual)` | `9×SO/IP`。 |
| `bb_per_9.py` | `compute_bb_per_9(bb, ip_actual)` | `9×BB/IP`。 |
| `h_per_9.py` | `compute_h_per_9(hits_allowed, ip_actual)` | `9×H/IP`。 |
| `hr_per_9.py` | `compute_hr_per_9(hr_allowed, ip_actual)` | `9×HR/IP`。 |
| `k_bb_ratio.py` | `compute_k_bb_ratio(so, bb)` | SO ÷ BB。 |
| `p_per_ip.py` | `compute_p_per_ip(pitches, ip_actual)` | pitches ÷ IP。 |
| `rs_per_9.py` | `compute_rs_per_9(run_support, ip_actual)` | `9×run_support/IP`。 |
| `strike_pct.py` | `compute_strike_pct(strikes, pitches)` | 球季 API strikes ÷ pitches，回棒球小數字串；不同於逐球 `compute_pitch_strike_pct()`。 |
| `win_pct.py` | `compute_win_pct(wins, losses)` | W ÷ (W+L)，回棒球小數字串。 |
| `extension.py` | `compute_avg_extension(pitches)` | 平均非空 extension（ft）。 |
| `opponent_slash.py` | `annotate_opponent_slash(s)` | 從投手對手 counting stats 補 `p_avg/p_obp/p_slg/p_ops`；任一必要分量不足就保留空值，會修改輸入列。 |
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
| `batted_ball/__init__.py` | `batted_ball_metrics(agg)` | 組裝 BBE、GB/LD/FB/PU/air、spray、barrel、hard-hit、avg EV 等打者/投手共用欄位。 |
| `barrel.py` | `compute_barrel_pct(agg)` | barrels ÷ 有 EV 的 BBE。 |
|  | `is_barrel(ev, la)` | 依 Statcast 98 mph 起跳、隨 EV 放寬且 116 mph 封頂的角度窗判定單球 barrel。 |
| `hard_hit.py` | `compute_hard_hit_pct(agg)` | hard hits ÷ 有 EV 的 BBE。 |
|  | `is_hard_hit(ev)` | EV ≥ 95 mph。 |
| `exit_velocity.py` | `compute_avg_ev(bbe_ev)` | 平均 EV。 |
|  | `compute_max_ev(bbe_ev)` | 最大 EV。 |
|  | `compute_ev90(bbe_ev)` | EV 第 90 百分位；排序後依現有離散 index 取實際觀測值，不做插值。 |
| `launch_angle.py` | `compute_avg_la(la_values)` | 平均 launch angle。 |
| `sweet_spot.py` | `is_sweet_spot(la)` | 8°–32° 判定。 |
|  | `compute_sweet_spot_pct(la_values)` | sweet-spot 球數 ÷ 有 LA 的球數。 |
| `hr_fb.py` | `compute_hr_fb_pct(pa_final, fb_count)` | PA-final HR ÷ fly balls；投手專用。 |
| `spray.py` | `spray_direction_from_location(p)` | 缺 hit coordinate 時，以 `hit_location` zone 備援判斷 pull/center/opposite。 |
|  | `spray_direction_from_coordinates(p)` | 將 Gameday `(coord_x,coord_y)` 經透視修正換成噴射角度方向。 |
|  | `compute_spray(in_play)` | 優先座標、再用 location 分類，回各方向 count/rate 與可用樣本數。 |

### 3.6 `stats/advanced/` — 需要年度/聯盟常數的統計

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `advanced/__init__.py` | 無函式 | 標記需要聯盟環境或固定公式常數的統計；環境值仍由外層傳入，套件內不做 I/O。 |
| `advanced/fip.py` | `compute_fip(hr, bb, hbp, k, ip, c_fip=None)` | 純函式 FIP；棒球 IP 先轉 outs，未傳常數才用本模組的 `FIP_DEFAULT_CONSTANT` 最終 fallback。回 full precision。 |
|  | `compute_league_fip_constant(totals)` | 從聯盟 HR/BB/HBP/K/ER/outs 同時計算 lgERA 並反解 FIP constant，回 `LeagueFipConstant(fip_constant, lg_era)`；無有效局數回 `None`。 |
| `advanced/woba.py` | `compute_pitch_woba(totals)` | 從 `compute_pa_outcome_totals()` 結果算逐球 wOBA。 |
|  | `compute_season_woba(stat)` | 從球季 counting stats 算 wOBA；故意四壞從 numerator/denominator 排除。 |
| `advanced/xwpct.py` | `compute_xwpct(fip, lg_era)` | 用同一批聯盟投球 totals 算出的 lgERA 與固定 1.83 指數計算預期勝率；任一輸入缺失/非正數回 `None`，不再查表或套用預設 run environment。 |
| `advanced/wrc_plus.py` | `compute_wrc_plus(woba, pf_final, lg_woba, lg_r_pa)` | 套用 TJStats 公式與 park-factor midpoint，回整數 wRC+。 |
|  | `annotate_wrc_plus(bundles, batting_lookup)` | 接受 `BattingConstants.for_level` 類 callback，原地補入每列及同層轉隊合計 wRC+；本身不碰 network/DB，也不寫回 season_stats。 |
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
|  | `compute_pitch_usage_by_count.key_fn(p)` | closure；把 pitch 映射為 `(pitch_type,pitch_name)`。 |
|  | `compute_pitch_group_usage_by_count(pitches)` | 將球種捲成 fastball/breaking/offspeed 後計算 count usage。 |
|  | `compute_pitch_group_usage_by_count.key_fn(p)` | closure；排除雜訊球種並映射至固定球種群組。 |
| `tables/vs_pitch_types.py` | `_compute_pitch_bucket_row(key, name, ps)` | 球種與球種群組共用的打者表單列計算，避免欄位定義漂移。 |
|  | `compute_vs_pitch_types(pitches)` | 打者對逐球種的 discipline、AVG/wOBA 與 contact-quality 表。 |
|  | `compute_vs_pitch_groups(pitches)` | 同一組指標捲成 fastball/breaking/offspeed。 |
|  | `compute_batter_pitch_hand_splits(pitches)` | 建立打者對 all/L/R 投手的球種、球種群組與 count usage 表。 |

### 3.8 Statcast 彙整入口

| 檔案 | 唯一函式 | 功能與定位 |
|---|---|---|
| `stats/pitcher_statcast.py` | `compute_pitcher_statcast(pitches)` | 投手球季入口：先回填 count、聚合 pitches/PA，再組裝 wOBA against、HR/FB、extension、bat-side tables、Plinko、movement、discipline 與 batted-ball metrics。空輸入回 `{}`。 |
| `stats/batter_statcast.py` | `compute_batter_statcast(pitches)` | 打者球季入口：組裝逐球 strike%、wOBA、max EV/EV90/LA/sweet spot、球種/球種群組、pitch-hand splits、Plinko、discipline 與 batted-ball metrics。空輸入回 `{}`。 |

---

## 4. sync/ — 同步管線

### 4.1 套件入口與欄位映射

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `sync/__init__.py` | 無新函式 | Re-export `sync_database`、`update_database`、`sync_statcast`。 |
| `sync/field_maps.py` | `apply_yearbyyear_fields(stat_doc, group_name, stat)` | 把 yearByYear API camelCase 欄位安全轉型並寫入內部 snake_case schema；處理 hitting/pitching，fielding 由 `sync/players.py` 另行保存。 |
|  | `apply_advanced_fields(stat_doc, group_name, stat)` | 把 seasonAdvanced 特有欄位補入同一 stat dict。 |

### 4.2 `sync/players.py` — 基礎資料同步

| 函式 | 功能與定位 |
|---|---|
| `_is_first_sync(mlb_id, synced_ids)` | 該 ID 尚無 season_stats 即為首次同步；refresh 也要為新球員完整回補。 |
| `_fetch_player_data(pconf, year, fetch_all_years=True)` | thread worker；只做 API 抓取與 bundle 組裝，不寫 DB。完整模式抓所有 game-log 年份，快速模式只抓當年。 |
| `_write_player_to_db(conn, bundle, year)` | 單一玩家的序列寫入：players、season_stats、game_logs、next_game，並處理 fielding gp 與目前最高層級/球隊。 |
| `_run_pipeline(db_path, roster_file, year, only_player=None, fetch_all_years=True, mode_label="Sync")` | 共用 orchestration：初始化 DB、判斷首次/非現役、平行抓玩家、主執行緒逐一寫入。 |
| `sync_database(db_path, roster_file, year, only_player=None)` | 完整歷史同步薄包裝，`fetch_all_years=True`。 |
| `update_database(db_path, roster_file, year, only_player=None)` | 日常快速更新薄包裝，僅更新當年 game logs。 |

### 4.3 `sync/extract.py` — live-feed 精簡 schema

| 函式 | 功能與定位 |
|---|---|
| `_extract_runners(play)` | 濃縮 PA-final runners movement 與守備 credit。 |
| `_condense_defense(d)` | 保留守備站位/球員必要欄位，移除 API boilerplate。 |
| `_condense_offense(d)` | 保留壘上進攻球員必要欄位。 |
| `_condense_nonpitch_event(ev, play)` | 將 pickoff/stepoff 等非投球事件轉成 `events_json` schema。 |
| `_pa_context(play)` | 擷取 PA-final WP、LI、drama 與上下文欄位。 |
| `extract_pitch_logs(game_data, player_id, role)` | 單次走訪 live feed，依 pitcher/batter 身分回傳 `(pitches, nonpitch_events)`；此函式定義 `pitches_json` 與 `events_json` 的實際欄位契約。 |

### 4.4 `sync/statcast.py` — 逐球與進階數據管線

| 函式 | 功能與定位 |
|---|---|
| `_fetch_and_extract_game(game_pk, players_in_game)` | 每場只抓一次 live feed，為所有相關球員抽 pitches/events，並回 sport level；必要時嘗試另一角色。 |
| `_same_level(a, b)` | 透過 `resolve_tier()` 比較現代/歷史層級拼法；無法解析才退回字串相等。 |
| `_pitches_need_hit_coord_backfill(pitches)` | 判斷舊快取是否有 in-play 球缺 hit coordinates，需要重抓 live feed。 |
| `_merge_statcast_into_season(cur, mlb_id, year, position, statcast_data, fip_constants_lookup, sport_level="", sabermetrics=None, expected_stats=None)` | 將單一 `(year,level)` Statcast 合併進正確 season_stats 列；lookup 回 `LeagueFipConstant`。MiLB 優先用所屬聯盟 FIP constant、失敗退整層；MLB FIP 仍取 API。兩者 xWPCT 都使用整層 `lg_era`，並把它存回 stat JSON。 |
| `_compute_player_statcast_bundle(mlb_id, db_path, position)` | 平行唯讀 worker；載入玩家 pitches、抓 MLB saber/expected stats，逐 `(year,level)` 呼叫投手或打者 Statcast 入口。 |
| `fetch_highlight_videos(conn, roster_ids, *, now_iso=None)` | 找 `/content` 候選、抓取/抽取影片、寫 play video 與 processed cache；回新增/更新影片數。 |
| `sync_statcast(db_path, roster_file, year, only_player=None, update_constants=False)` | 對外總入口：建立 `PitchingConstants` resolver → 回補 level/coordinates → 找未處理比賽 → 平行抓與抽取 → 寫 pitch cache → 平行重算玩家 Statcast → 以 `for_level` merge season rows → 抓 highlights。 |

---

## 5. render/ — 靜態網站渲染

### 5.1 Jinja 環境、filters 與 URL

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `render/__init__.py` | 無新函式 | Re-export `build_static_site`。 |
| `render/env.py` | `create_jinja_env(template_dir=None, base_url="/", site_origin="https://tingruih.github.io")` | 建立 Jinja environment，註冊顯示 filters、level helper、相對/絕對 URL、headshot 與站台 globals。 |
| `render/filters.py` | `floatformat(value, digits=2)` | 固定位數格式，`None` 顯示 `-`。 |
|  | `default_if_none(value, fallback="-")` | 只在 `None` 時套 fallback，不把合法的 0 當空。 |
|  | `num_dash(value)` | 數值直接顯示，`None`/空字串顯示 `-`。 |
|  | `_json_html_safe(s)` | 轉義 `</`，避免 JSON 提前關閉 `<script>`。 |
|  | `tojson_safe(value)` | JSON serialize + HTML-safe `Markup`，供一般 script payload。 |
|  | `jsonld(value)` | 緊湊 JSON-LD serialize + HTML-safe `Markup`。 |
|  | `pct_fmt(value, digits=1)` | decimal fraction 轉百分比字串，使用 half-up rounding。 |
| `render/urls.py` | `headshot_cdn_urls(mlb_id, latest_level_is_mlb)` | 依最近實際出賽層級決定 MLB/MiLB CDN 主備 URL 順序。 |
|  | `make_url_helpers(base_url)` | 回傳三個已綁 base URL 的 closure，供 Jinja globals。 |
|  | `make_url_helpers.player_url(mlb_id)` | closure；產生現役球員頁相對 URL。 |
|  | `make_url_helpers.retired_player_url(mlb_id)` | closure；產生退役球員頁相對 URL。 |
|  | `make_url_helpers.static_url(path)` | closure；產生靜態資產相對 URL。 |
|  | `make_absolute_url(site_origin, base_url)` | 建立絕對 URL closure。 |
|  | `make_absolute_url.absolute_url(path="")` | closure；把站台 origin、base URL、path 正規化成 canonical 絕對 URL。 |

### 5.2 SEO 與 pitch-log 輸出

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `render/seo.py` | `player_display_name(player)` | 組合中文/英文顯示名稱。 |
|  | `player_canonical_path(player, is_retired=False)` | 依現役/退役目錄產生 canonical path。 |
|  | `player_description(player)` | 依球員、位置、球隊/層級產生 meta description。 |
|  | `index_structured_data(absolute_url, player_data)` | 建立首頁 WebSite + ItemList JSON-LD。 |
|  | `player_structured_data(absolute_url, player, is_retired=False)` | 建立球員 Person + BreadcrumbList JSON-LD。 |
|  | `write_robots(out_dir, sitemap_url)` | 寫 `robots.txt`。 |
|  | `write_sitemap(out_dir, urls)` | 寫 XML sitemap。 |
| `render/pitch_log.py` | `summarize_pitch_for_display(p, video_map=None, include_video=False)` | 將完整 pitch dict 投影成前端需要的精簡欄位；可按 `play_id` 附 mp4。 |
|  | `write_pitch_log_files(logs_by_year, out_dir, normalized_base_url, mlb_id, videos_by_game=None)` | 每場輸出獨立延遲載入 JSON，並在 log 摘要附 `pitch_data_url`/`pitch_count`。 |

### 5.3 `render/pages.py` — payload 塑形與全站輸出

| 函式 | 功能與定位 |
|---|---|
| `_pick_display_stat(stats_current, player)` | 首頁/hero 代表列優先序：同隊 → 同目前層級 → 最高已出賽層級。 |
| `_statcast_row_qualifies(player, s)` | 有 Statcast 即納入；沒有 Statcast 時，只有 `publishes_constants(level,year)` 涵蓋且已有計算 wRC+ 的打者列可納入 advanced 區。 |
| `_first_not_none(rows, field)` | 找同組列第一個實值，供只寫在其中一列的整季欄位。 |
| `_merge_level_rows(rows)` | 合併同 `(year,tier)` 的轉隊列：重加 counting/rates、IP-weighted FIP，取同層固定的 `lg_era` 重算 xWPCT，並取回 WAR/expected/saber/wRC+。 |
| `_pooled_year_pitches(logs)` | 從已解析 game logs 建 `{year: pitches}`，跨層級合計時不重讀 DB。 |
| `_build_statcast_entries(player, stats, logs)` | 建 `{year: entries}`；同層轉隊去重，多層級球季把原始 pitches pooling 後完整重算 `_combined`。 |
| `_inline_css_imports(css_path, seen=None)` | 遞迴展開 CSS `@import`，用 `seen` 防循環且維持 cascade 順序。 |
| `_bundle_css(static_out_dir)` | build 時把 `style.css` import graph 壓成單檔，減少瀏覽器 request waterfall。 |
| `build_static_site(db_path, year, output_dir, base_url="/", roster_file=None, update_constants=False)` | 唯一全站入口：重建 output、複製/壓平 static、初始化 Jinja/DB、載入 roster bundles，以 `BattingConstants.for_level` 標注 wRC+、切現役/退役、組球員/圖表/pitch-log payload、渲染所有 HTML、寫 sitemap/robots/`.nojekyll`。 |

`build_static_site()` 會刪除並重建指定 `output_dir`；呼叫端必須傳入明確且安全的輸出
路徑。純資料塑形應優先放進上面的 `_merge_*` / `_build_*` helper，避免讓主入口繼續膨脹。

---

## 6. graph/ — 圖表資料

| 檔案 | 所有函式 | 功能與定位 |
|---|---|---|
| `graph/__init__.py` | 無函式 | 圖表 payload 套件標記。 |
| `graph/movement.py` | `compute_pitch_movement_chart(pitches, max_points=COMPUTE_MAX_POINTS)` | 產生投手逐球 HB/IVB、球種及可用的球速/轉速點位，並按上限降採樣；單層級與跨層級都直接從原始 pitches 計算。 |
| `graph/plinko.py` | `_empty_plinko_nodes()` | 建立固定 count nodes 的零值 payload。 |
|  | `_empty_plinko_edges()` | 建立固定 count transitions 的零值 payload。 |
|  | `compute_pitch_plinko(pitches, *, split_field, split_specs, skip_types=None)` | 依打者/投手慣用手 split，累計 count node 與 transition edge，輸出前端 Pitch Plinko 結構。 |
| `graph/season_trend.py` | `_neumaier_add(total, compensation, x)` | 串流 Neumaier 補償加總一步，讓遞增 EV 等浮點結果與整批 `sum()` 一致。 |
|  | `_compute_pitcher_cumulative_metrics(games)` | 按日期逐場累積投手 ERA/K%/BB%/discipline/contact 等；每場 pitches 只掃一次。 |
|  | `_compute_batter_cumulative_metrics(games)` | 按日期逐場累積打者 AVG/K%/BB%/wOBA/discipline/contact 等。 |
|  | `_group_games_by_level(year_logs, year, metrics_seq_fn)` | 依層級分組、排序，再用指定累積函式建立各層級序列。 |
|  | `_build_all_levels_entry(year_logs, year, metrics_seq_fn)` | 合併同年所有層級 game logs 後一次累積，建立不中斷的 `_all` 走勢並保留每點 level badge。 |
|  | `build_pitcher_trend_by_year(logs_by_year)` | 對外投手年度趨勢入口，回 `year → level/_all → payload`。 |
|  | `build_batter_trend_by_year(logs_by_year)` | 對外打者年度趨勢入口，並依打者可用指標過濾 payload。 |

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
| `util/numbers.py` | `safe_float(value, default=None)` | 安全轉 float，失敗回 default。 |
|  | `safe_int(value, default=None)` | 安全轉 int；接受整數、整數字串等 `int()` 可處理的值，失敗回 default。 |
|  | `ratio(num, den, digits=3)` | 安全除法並 round；零/缺分母回 `None`。 |
|  | `mean(values)` | 過濾 `None` 後平均；空樣本回 `None`。 |
|  | `mean_round(values, digits=1)` | `mean()` 後捨入。 |
|  | `float_or_none(value)` | 轉 float 並拒絕 NaN/Infinity；外部資料清洗時使用。 |
| `util/obj.py` | `Obj.__getattr__(key)` | 將 dict key 暴露為 attribute；缺 key 回 `None`，方便模板讀稀疏欄位。 |
|  | `Obj.__setattr__(key, value)` | attribute assignment 寫回 dict key。 |
| `util/units.py` | `height_to_cm(height_str)` | 解析 `6' 2"` 類身高並轉公分。 |
|  | `lbs_to_kg(weight_lbs)` | 磅轉公斤並依顯示規則捨入。 |

---

## 8. 頂層模組

### 8.1 `site_builder/__init__.py`

無函式；只提供 package docstring。

### 8.2 `constants.py`

| 函式 | 功能與定位 |
|---|---|
| `_auto_season_year()` | 3 月起使用當年，1–2 月仍視為上一球季；用來初始化 `SEASON_YEAR`。 |

此檔其餘內容是路徑、timeouts/retry/workers、`SEASON_YEAR`、固定 wOBA weights、
pitch code、count/split/plinko、pitch-type groups、batted-ball 與
`COUNTING_FIELDS`。已不再維護年度 RA/9、FIP 或 TJStats 對照表；季別/聯盟環境
由 `league_constant/` 取得，TJStats 網站拼法放在 `api/tjstats.py`，層級與 roster
規則分別留在 `levels.py`、`roster.py`。

### 8.3 `levels.py`

`Tier` 是 frozen dataclass，沒有自訂 method。

| 函式 | 功能與定位 |
|---|---|
| `resolve_tier(raw)` | 將現代/舊制/別名層級解析成 `Tier`；未知回 `None`。 |
| `level_rank(raw)` | 回 hierarchy rank，數字越小層級越高；未知值用 50。 |
| `level_display(raw, year)` | 2021+ 顯示現代名稱、2020- 顯示舊制名稱；sentinel/未知值原樣回傳。 |
| `is_mlb(raw)` | 是否解析到 MLB tier。 |
| `sport_id_to_code(sport_id)` | MLB Stats API sportId → 儲存用 code；短期 1A 用 legacy fallback。 |
| `sport_name_to_code(name)` | API sport name → 儲存用 code；是缺 sportId 時的 fallback。 |
| `sport_obj_to_abbr(sport)` | sport dict 先用 id、再用 name 解析。 |
| `tier_keys_ordered()` | 依 rank 回傳 canonical tier keys；SQL CASE 排序會使用。 |

### 8.4 `roster.py`

| 函式 | 功能與定位 |
|---|---|
| `parse_roster_from_file(filepath)` | 讀 roster JSON 的 `players`；任何錯誤記 log 並回空列表。 |
| `build_roster_map(roster_file)` | 建 `{mlb_id: player_config}` 快速索引。 |
| `categorize_roster_status(code, is_active_entry, player_is_active)` | 將 MLB roster code 分成 `active/injured/restricted/inactive/other`。 |
| `is_national_team_tx(tx)` | 交易描述是否為 Chinese Taipei 國家隊徵召；不算 affiliated activity。 |
| `is_active_player(player, stats, year)` | 當年有 season row 或合格交易即視為站台現役；只剩國家隊徵召者歸退役頁。 |

---

## 9. build.py — CLI

| 函式 | 功能與定位 |
|---|---|
| `cmd_sync(args)` | lazy import 並呼叫 `sync_database()`。 |
| `cmd_build(args)` | lazy import 並呼叫 `build_static_site()`。 |
| `cmd_statcast(args)` | lazy import 並呼叫 `sync_statcast()`。 |
| `cmd_refresh(args)` | 日常管線：`update_database()` → `sync_statcast()` → `build_static_site()`。 |
| `cmd_all(args)` | 首次/回補管線：`cmd_sync()` → `cmd_statcast()` → `cmd_build()`；單一球員模式會警告 build 仍渲染全 roster。 |
| `main()` | 建立 argparse 子命令/共用參數、驗證 command，最後 dispatch `args.func(args)`。 |

---

## 10. 完整性核對方式

本文件把「函式」定義為 AST 中的 `FunctionDef`/`AsyncFunctionDef`，因此 class
method 和 closure 也計入。第 1～8 章目前應有：

| 章節 | Python 檔案 | 函式 / method |
|---|---:|---:|
| `api/` | 9 | 22 |
| `db/` | 7 | 12 |
| `league_constant/` | 4 | 18 |
| `stats/` | 73 | 108 |
| `sync/` | 5 | 21 |
| `render/` | 7 | 33 |
| `graph/` | 4 | 11 |
| `util/` | 6 | 15 |
| 頂層 `__init__/constants/levels/roster` | 4 | 14 |
| **合計** | **119** | **254** |

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

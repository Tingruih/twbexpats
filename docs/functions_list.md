# site_builder 函式清單

> 最後更新：2026-07-04
>
> 本文件盤點 `site_builder/` 套件目前的完整結構與每個模組的職責，做為日後修改
> 程式的導覽地圖。**舊版文件（2026-07-01）是為了替當時 9 個檔案的
> `site_builder/` 規劃拆分方案而寫的。那次拆分已經完成，而且拆得比舊文件建議
> 的更細、更徹底**——目前套件已有 114 個 Python 檔案、共 6919 行，依職責切成
> 8 個子套件（`api/` `db/` `graph/` `render/` `stats/` `sync/` `util/` 加上
> 3 個頂層模組）。本文件的目的因此從「該怎麼拆」轉為「現況長什麼樣子、還有
> 哪些地方沒拆完」。

## 目錄

0. [模組相依圖](#0-模組相依圖)
1. [api/ — 外部資料來源客戶端](#1-api--外部資料來源客戶端)
2. [db/ — SQLite 持久層](#2-db--sqlite-持久層)
3. [stats/ — 數據計算（一個檔案一個統計量）](#3-stats--數據計算一個檔案一個統計量)
4. [sync/ — 資料同步管線](#4-sync--資料同步管線)
5. [render/ — 靜態網站渲染](#5-render--靜態網站渲染)
6. [graph/ — 圖表資料](#6-graph--圖表資料)
7. [util/ — 通用工具](#7-util--通用工具)
8. [頂層模組：constants.py / levels.py / roster.py](#8-頂層模組constantspy--levelspy--rosterpy)
9. [build.py — CLI 進入點](#9-buildpy--cli-進入點)
10. [跨檔案重複與一致性檢查（對照舊文件）](#10-跨檔案重複與一致性檢查對照舊文件)
11. [觀察與建議](#11-觀察與建議)

---

## 0. 模組相依圖

```
                          ┌──────────────┐
                          │  build.py    │  CLI 進入點（sync / statcast / refresh / build / all）
                          └──────┬───────┘
                    lazy import  │  lazy import
              ┌───────────────────┴───────────────────┐
              ▼                                        ▼
        site_builder.sync                       site_builder.render
      (sync_database / update_database /       (build_static_site)
       sync_statcast)                                  │
              │                                        │
    ┌─────────┼─────────┬───────────┐        ┌─────────┼──────────┐
    ▼         ▼         ▼           ▼        ▼         ▼          ▼
  api/      db/       stats/     util/     db.bundles stats.combine  graph.*
              │          │                  levels    stats.core
              │          │                  roster     util
              ▼          │
        api/ (fetch)     │
        levels/ (等級)   │
        stats.core       │
        stats.advanced.fip
                          ▼
                    stats/ 內部：
                    core/ 是共用基礎，
                    batting/ pitching/ discipline/
                    batted_ball/ advanced/ tables/
                    都只依賴 core/ 與 constants/util，
                    彼此之間幾乎不互相依賴
                          │
                          ▼
                    graph/ （pitch_movement, pitch_plinko）
                    只依賴 stats.core + constants + util
```

分層原則（由下而上）：

- **`util/`**：零領域知識的泛用工具（日期、JSON、數字、`Obj`、單位換算）。被所有人依賴，自己不依賴任何人。
- **`levels.py` / `roster.py` / `constants.py`**：頂層單一事實來源，供 `api/` `db/` `stats/` `sync/` `render/` 共用。彼此獨立、互不依賴。
- **`api/`**：只做 HTTP 請求與 JSON→dict 轉換，不碰資料庫、不做統計計算。依賴 `levels.py`（sportId↔代碼轉換）與 `constants.py`（timeout）。
- **`stats/`**：純函式運算層。`stats/core/` 是共用基礎（pitch 分類、PA 結算、局數換算、聚合、annotate、selector）；`batting/` `pitching/` `discipline/` `batted_ball/` 是「一檔一個統計公式」的葉節點模組；`advanced/` 是需要外部資料或年度常數的統計（wOBA、wRC+、FIP、xWPCT，會反向依賴 `db.tjstats_cache` 與 `db.fip_constants_cache`）；`tables/` 是球種細分表；`combine.py` 是跨等級合併的總樞紐。`stats/` 內部彼此依賴但幾乎不依賴外部套件（`advanced/wrc_plus.py` 是唯一例外，需要 `db.tjstats_cache`）。
- **`graph/`**：圖表資料（球路位移散佈圖、Pitch Plinko），只依賴 `stats.core` + `constants` + `util`。
- **`db/`**：SQLite schema 與查詢層，依賴 `api/`（FIP 常數、TJStats 快取需要即時抓取資料）、`levels.py`、`roster.py`、`stats.core`、`stats.advanced.fip`。
- **`sync/`**：資料同步管線，依賴 `api/` + `db/` + `stats/` + `util/`。
- **`render/`**：靜態網站渲染，依賴 `db.bundles`（讀資料）、`stats.combine`（跨等級合併）、`stats.core.career`（生涯／年度加總）、`levels.py` `roster.py` `util/`，以及 Jinja2。
- **`build.py`**：唯一的進入點，用 lazy import 串接 `sync` 與 `render`，兩者互不直接依賴，只共用底層的 `api/db/stats/util`。

---

## 1. api/ — 外部資料來源客戶端

只負責「打 API、回傳 dict」，不寫資料庫、不算統計。所有函式對外部服務失敗都
採用 try/except + 記錄警告（log warning）後回傳空結果的「盡力而為」策略,
讓上層可以照樣運作（缺資料而非整個流程中斷）。

| 檔案 | 內容 |
|---|---|
| `client.py` | `BASE_URL`（v1）/`BASE_URL_V11`（live-feed 專用）；`get_json(url, timeout)` 共用的 GET + JSON 解析。 |
| `players.py` | `get_player_profile(mlb_id)`：`/people/{id}?hydrate=transactions,rosterEntries,currentTeam`。回傳姓名、身高體重、生日、慣用手、最新交易紀錄、球隊、**roster 狀態**（`roster_status` / `roster_status_code` / `roster_is_active`，供 `roster.py::categorize_roster_status` 使用）。 |
| `stats.py` | `get_player_stats`（yearByYear）、`get_player_advanced_stats`（seasonAdvanced）、`get_game_logs`（gameLog）、`get_player_sabermetrics`（FIP/xFIP/WAR，MLB only）、`get_player_expected_stats`（xwOBA/xBA/xSLG，MLB only）。**MLB／MiLB 兩個端點都各自包在獨立的 try/except 裡**，任一失敗只記錄警告、不影響另一端點——這是舊文件點名的不對稱問題，現在已經統一成對稱寫法。 |
| `games.py` | `get_game_play_by_play(game_pk)`：抓單場 live-feed 全文，統一用 `LIVE_FEED_TIMEOUT` 常數（舊文件點名的 timeout 字面值不一致問題已解決）。`sport_obj_to_abbr(sport)`：sportId 或 sport name 轉等級代碼，經由 `levels.py` 單一登記表。`get_game_sport_level(game_pk)`：只抓該場比賽的等級（用 `fields=` 過濾縮小 payload）。 |
| `schedule.py` | `get_next_game(team_id)`：查未來 7 天內第一場「Preview」狀態的比賽，換算成台灣時間字串。 |
| `league_stats.py`（新模組） | `fetch_team_league_map(sport_id, year)`：`{team_id: league_name}`。`fetch_team_pitching_totals(sport_id, year)`：各隊投手計數型數據加總，供反推 FIP 常數用。 |
| `tjstats.py` | `fetch_park_factors(level, year)` / `fetch_league_constants(year)`：BeautifulSoup 解析 tjstats.ca 同一頁面裡的兩張 `<table class="tjs-guts">`。依模組 docstring 定位為「best-effort 加值資料，非核心資料」，任何失敗都吞掉、回傳 `{}`。 |
| `__init__.py` | 統一 re-export 上述所有公開函式，呼叫端可直接 `from site_builder.api import get_player_profile`。 |

---

## 2. db/ — SQLite 持久層

| 檔案 | 內容 |
|---|---|
| `schema.py` | `init_db(conn)`：`CREATE TABLE IF NOT EXISTS` 建立 `players` / `season_stats` / `game_logs` / `playbyplay_processed`，以及 3 張新表 `tjstats_park_factors` / `tjstats_league_constants` / `league_fip_constants` + 2 個索引；接著跑 5 個包在 `try/except sqlite3.OperationalError` 裡的 `ALTER TABLE ... ADD COLUMN` 正向遷移（`game_logs.pitches_json`/`sport_level`、`players.roster_status_code`/`roster_is_active`、`game_logs.hit_coord_checked`、`game_logs.events_json`）。 |
| `season_stats.py` | `load_season_row` / `save_season_row`（`INSERT ... ON CONFLICT DO UPDATE`，key 是 `(player_mlb_id, year, team_name)`）；`players_with_existing_stats(conn)`：找出已有資料的球員 id，用來判斷是否為「首次同步」（首次同步即使在 `update`/`refresh` 模式下也要做完整回補）。 |
| `players.py` | `warn_orphaned_players`：印出資料庫裡有、但 roster.json 已移除的球員（並附上可直接執行的清理 SQL）；`get_positions` / `get_cached_is_active`：批次查詢輔助函式。 |
| `game_logs.py` | `load_all_pitches_for_player(cur, mlb_id)` → `{(year, sport_level): [pitch,...]}`。對舊資料裡 `sport_level` 為空字串的列做消歧義：若該球員該年只待過一個等級就直接指派，否則歸到 `(year, "")` 交給呼叫端處理。 |
| `bundles.py` | `load_player_bundle(cur, player_row)`：建出模板要用的完整球員 `Obj`（解析 `transactions_json`/`next_game_json`、算年齡、`is_pitcher`）；載入並依 `(-year, level_order)` 排序 `season_stats`；算出 `latest_stat` / `available_years` / **`latest_level_is_mlb`**（用 `has_appearance` 篩出「最近一個有實際出賽紀錄的等級」，而非「生涯是否曾上過大聯盟」，這樣被降回小聯盟的球員在挑選頭像 CDN 版本時才不會誤判）；相容處理沒有 `pitches_json` 欄位的舊資料庫（先用 `SELECT ... LIMIT 0` 探測欄位是否存在）。 |
| `fip_constants_cache.py` | FIP 聯盟常數的 SQLite 快取。**快取策略**：進行中賽季（`year >= SEASON_YEAR`）永遠即時重抓並覆寫；已結束賽季永久快取。`_fetch_and_compute`：等級→sportId（經 `levels.resolve_tier`）→抓各隊投手數據＋隊伍所屬聯盟 map→依聯盟與整體等級各加總一份→呼叫 `compute_league_fip_constant`。`get_fip_constants(conn, sport_level, year, force_refresh=False)` 為對外唯一入口。 |
| `tjstats_cache.py` | Park factor 與聯盟常數的 SQLite 快取，兩組資料各自一套 `_load_*`/`_save_*`/`get_*` 函式。**快取策略與 `fip_constants_cache.py` 不同**：任何年份的抓取結果只要非空就永久快取；若抓回空結果則**不快取**，下次 build 會自動重試（區別在於：TJStats 資料一旦公布就不會再變，只需要處理「還沒公布」的情況；FIP 常數則是進行中賽季本身數值就會一直變動）。 |
| `__init__.py` | 純文件註解，列出各子模組職責，不 re-export（呼叫端直接 `from .schema import init_db` 等）。 |

---

## 3. stats/ — 數據計算（一個檔案一個統計量）

`stats/__init__.py` 的 docstring 明白寫出這個套件的設計哲學與擴充方式：

> 新增一個統計量 = 新增一個帶有純 `compute_*` 函式的檔案，再掛進對應的組裝點：
> 球季列衍生統計 → `core/annotate.py`；投手 Statcast 摘要 →
> `pitcher_statcast.py`；打者 Statcast 摘要 → `batter_statcast.py`；跨等級
> 合併列 → `combine.py`。

### 3.1 `stats/core/` — 共用基礎

| 檔案 | 內容 |
|---|---|
| `pitches.py` | `is_swing` / `is_whiff` / `is_called_strike` / `is_in_zone` / `is_out_of_zone`；**`is_unknown_pitch_type(pitch_type, pitch_name=None)`**——舊文件點名跨檔案重複定義的函式，現在整個套件只有這一份；`pre_count_tuple` / `post_count_tuple` / `count_label`；`ensure_pre_strikes(pitches)`：替沒有 `pre_balls`/`pre_strikes` 欄位的舊快取資料回填（以 `game_pk` 邊界與 `is_pa_final` 重置計數）；**`aggregate_pitches(pitches)`**：單次掃描分類器，一次迴圈同時算出 `total`/`swings`/`whiffs`/`called`/`in_zone`/`out_zone`/`in_zone_swings`/`out_zone_swings`/`in_zone_contact`/`in_play`/`bbe_ev`/`pa_final`/`gb`/`fb`/`ld`/`pu`/spray 相關欄位（透過 `compute_spray`）/`barrels`/`hard_hits`，是投手與打者 Statcast 摘要共用的核心。 |
| `pa_outcomes.py` | `compute_pa_outcome_totals(pa_final)` → `{woba_num, woba_den, hits, ab}`，明確排除 `NON_PA_EVENTS`、故意四壞（`intent_walk`）、犧牲觸擊（`sac_bunt`）。 |
| `innings.py` | `ip_to_outs(ip_value)` / `outs_to_ip(outs)`：棒球記法（7.2 局 = 7⅔ 局）↔出局數換算，任何比率型投手數據都要先換算過再算，否則會有微幅誤差。 |
| `aggregate.py` | `sum_counting(stats, result)`（依 `COUNTING_FIELDS` 加總，全為 `None` 才維持 `None`，否則視 `None` 為 0）；`compute_rate_stats(agg)`（`ab>0` 才算打擊率／上壘率／長打率／OPS，`ip_actual>0` 才算防禦率／WHIP）；`aggregate_stats(stats)`：生涯／單季合併加總的共用核心。 |
| `annotate.py` | `annotate_row(s)`：舊 `helpers.py` 215 行 `_compute_advanced_stats` 的直接替代品，清楚分成「打者欄位」（p_per_pa、xbh、iso、babip、ab_per_hr、go_ao、sb_pct、k_pct、bb_pct）與「投手欄位」（pitches_per_pa、k_per_9/bb_per_9/h_per_9/hr_per_9/p_per_ip/rs_per_9 皆以 `ip_actual > 0` 為前提、k_bb_ratio、以 BF 為分母的 k_pct/bb_pct、strike_pct、p_babip、p_go_ao、win_pct，並呼叫 `annotate_opponent_slash`）。**內含一則重要的中文註解記錄了一個 bug 修正**：投手 BABIP 的分母改用 `p_ab`（對方打數）而非舊版的 `bf`（面對打者數）——舊版只從 BF 扣掉 BB，漏扣 HBP 與犧牲觸擊，導致分母灌水、BABIP 被系統性低估；新版改用與打者版對稱的 `(AB − SO − HR + SF)` 公式。`annotate_computed_stats(all_stats)`：設定 `np`（pitches 別名）後對每列呼叫 `annotate_row`。 |
| `career.py` | `compute_career(stats, level_filter=None)`：生涯（或篩選 MLB-only/MiLB-only）加總，附球隊清單與年份區間字串。`compute_season_combined(stats, year)`：單一年度跨隊加總。`compute_year_groups(all_stats)`：依年份分組，每組附加總列（MLB 優先排序、ERA/WHIP 用出局數換算確保跨隊防禦率正確）＋逐隊細項列＋`multi` 旗標（該年是否待過 2 隊以上）。 |
| `formatting.py` | `fmt_avg(value)`：棒球慣用去掉開頭 0 的格式化（0.333 → ".333"）。 |
| `selectors.py` | `has_appearance(stat)`（gp/pa/ab/bf/`ip_to_outs(ip)` 任一 > 0）；`highest_level_row(stats)`（優先挑有出賽紀錄的列，依 `level_rank` 排序）；`highest_level(stats)`（回傳等級字串）。 |

### 3.2 `stats/batting/` — 打者計數型公式（一檔一函式）

| 檔案 | 函式 | 說明 |
|---|---|---|
| `avg.py` | `compute_avg` | 打擊率 |
| `obp.py` | `compute_obp` | 上壘率 |
| `slg.py` | `compute_slg` | 長打率 |
| `ops.py` | `compute_ops` | OPS |
| `iso.py` | `compute_iso` | 純長打率（ISO） |
| `babip.py` | `compute_babip` | 場內球打擊率（打者／投手共用同一公式，見 §3.1 annotate.py 的 bug 修正說明） |
| `bb_pct.py` | `compute_bb_pct` | 四壞率 |
| `k_pct.py` | `compute_k_pct` | 三振率 |
| `xbh.py` | `compute_xbh` | 長打數；三項分量全為 0/空才回傳 `None`，否則加總 |
| `ab_per_hr.py` | `compute_ab_per_hr` | 每支全壘打打數 |
| `go_ao.py` | `compute_go_ao` | 滾飛比 |
| `sb_pct.py` | `compute_sb_pct` | 盜壘成功率（回傳 `fmt_avg` 字串） |
| `p_per_pa.py` | `compute_p_per_pa` | 每打席用球數 |

### 3.3 `stats/pitching/` — 投手計數型公式（一檔一函式）

| 檔案 | 函式 | 說明 |
|---|---|---|
| `era.py` | `compute_era` | 防禦率 |
| `whip.py` | `compute_whip` | WHIP |
| `k_per_9.py` / `bb_per_9.py` / `h_per_9.py` / `hr_per_9.py` | 對應 `compute_*_per_9` | 每 9 局率 |
| `k_bb_ratio.py` | `compute_k_bb_ratio` | 三振四壞比 |
| `p_per_ip.py` | `compute_p_per_ip` | 每局用球數 |
| `rs_per_9.py` | `compute_rs_per_9` | 每 9 局得分支援 |
| `strike_pct.py` | `compute_strike_pct` | 球季層級好球率（回傳 `fmt_avg` 字串，與 §3.5 pitch 層級的 `pitch_strike_pct` 是不同概念，各自模組docstring 有說明區分） |
| `win_pct.py` | `compute_win_pct` | 勝率（回傳 `fmt_avg` 字串） |
| `opponent_slash.py` | `annotate_opponent_slash(s)` | 對手三圍（p_avg/p_obp/p_slg/p_ops）合併在同一檔，因為 OPS 需要 OBP、SLG 的未捨入浮點數；只在欄位仍為 `None` 時才填入，且刻意在任一分量缺值時整項留白，避免用不完整資料算出偏低的對手 OBP。 |
| `extension.py` | `compute_avg_extension` | 平均延伸（投手釋放點延伸，ft）；原本放在 `batted_ball/`，因非打擊球質指標而搬到這裡 |

### 3.4 `stats/discipline/` — 打擊紀律（pitch 層級聚合）

`__init__.py` 的 `discipline_metrics(agg)` 彙整以下 8 個函式（吃 `aggregate_pitches` 的輸出）：
`compute_csw_pct`、`compute_o_swing_pct`、`compute_swing_pct`、`compute_swstr_pct`、
`compute_whiff_pct`、`compute_z_contact_pct`、`compute_z_swing_pct`、`compute_zone_pct`。

另外 3 個檔案**不在** `discipline_metrics()` 的彙整範圍內，但都經 grep 確認被
`stats/tables/` 底下的球種細分表直接引用，屬於刻意的架構分工（球季總彙整 vs.
球種層級細分表），並非死代碼：

| 檔案 | 函式 | 使用位置 |
|---|---|---|
| `put_away.py` | `compute_put_away(pitches)` → `(put_away_pct, two_strike_count)` | docstring 明寫「之前是三處重複的同一段迴圈」；現用於 `tables/arsenal.py`、`tables/outcomes.py`、`tables/vs_pitch_types.py` |
| `z_whiff_pct.py` | `compute_z_whiff_pct(agg)` | 用於 `tables/outcomes.py`，並被 `tab_advanced.j2:409`、`m_advanced.j2:338` 兩個模板直接引用 |
| `pitch_strike_pct.py` | `compute_pitch_strike_pct(pitches)` | pitch 層級好球率，用於多張球種細分表 |

### 3.5 `stats/batted_ball/` — 打擊球質

| 檔案 | 函式 | 說明 |
|---|---|---|
| `barrel.py` | `compute_barrel_pct` / `is_barrel(ev, la)` | Statcast 標準桶身球定義（98 mph 起跳，仰角窗隨球速線性放寬，116 mph 兩端封頂） |
| `hard_hit.py` | `compute_hard_hit_pct` / `is_hard_hit(ev)` | 硬擊球（EV ≥ 95 mph） |
| `sweet_spot.py` | `compute_sweet_spot_pct` / `is_sweet_spot(la)` | 甜蜜點仰角區間 8°–32° |
| `exit_velocity.py` | `compute_avg_ev` / `compute_max_ev` / `compute_ev90` | 平均／最大／90 百分位擊球初速；`compute_ev90` 註解說明樣本數 < 10 顆時會跟 TJStats 對不上 |
| `launch_angle.py` | `compute_avg_la` | 平均擊球仰角 |
| `hr_fb.py` | `compute_hr_fb_pct` | HR/FB%（投手專用） |
| `spray.py` | `spray_direction_from_coordinates` / `spray_direction_from_location`（座標缺失時的備援） / `compute_spray` | 依 Gameday 250×250 像素噴射圖座標算出拉打／中外野／反方向分類，含詳細中文註解說明座標系換算公式與 0.75 透視修正係數的來源（The Hardball Times, 2017） |
| `__init__.py` | `batted_ball_metrics(agg)` | 組裝 `bbe`/`gb_pct`/`ld_pct`/`fb_pct`/`pu_pct`/`air_pct`/拉打噴射欄位（若座標資料可用才填）/`barrel_pct`/`hard_hit_pct`/`avg_ev`，是投手與打者共用的組裝函式；`hr_fb_pct` 因為是投手專用欄位，不在這裡組裝，而是在 `pitcher_statcast.py` 裡單獨呼叫（`avg_extension` 現已移至 `stats/pitching/extension.py`，見 §3.3） |

### 3.6 `stats/advanced/` — 需要年度常數或外部資料的統計

`__init__.py` 註明這裡是「開季要重新檢視」的模組，常數都在 `constants.py` §2。

| 檔案 | 內容 |
|---|---|
| `woba.py` | `compute_pitch_woba(totals)`：吃 `compute_pa_outcome_totals` 的結果算 wOBA。`compute_season_woba(stat)`：從球季計數型數據算 wOBA（供 `wrc_plus.py` 使用），故意排除故意四壞的非故意部分之外的量，對齊 TJStats 定義。 |
| `fip.py` | `compute_fip(hr, bb, hbp, k, ip, c_fip=None)`：MiLB 用的 FIP 公式，本身不做任何 I/O，常數需由呼叫端經 `db.fip_constants_cache` 解出後傳入 `c_fip`，解不出來才退回 `FIP_DEFAULT_CONSTANT`（舊文件點名的「dead 參數」`year`/`sport_level` 已移除）。`compute_league_fip_constant(totals)`：反向代數解出聯盟 FIP 常數（`C = 聯盟ERA − (13HR+3(BB+HBP)−2K)/IP`），取代舊版手抄、容易過時的常數表。 |
| `xwpct.py` | `compute_xwpct(fip, sport_level, year=None)`：Pythagenpat 公式（指數 1.83），用 `constants.get_league_ra9` 查該等級年度聯盟 RA/9。 |
| `wrc_plus.py` | `compute_wrc_plus(woba, pf_final, lg_woba, lg_r_pa)`：TJStats glossary 公式。`annotate_wrc_plus(bundles, conn, force_refresh=False)`：build 時針對每位非投手球員，依 `(year, sport_level)` 分組，用 **PA 最多的那筆列**決定該組要套用哪個球隊的球場係數／聯盟常數（模仿 TJStats 處理球季內轉隊球員的方式），MLB 列寫入 `wrc_plus_calc`（不覆蓋 API 原生 `wrc_plus`），非 MLB 列直接寫入 `wrc_plus`（模板實際渲染的欄位）。 |

### 3.7 `stats/tables/` — 球種細分表（一表一檔）

每個檔案都有一對函式：`compute_*`（sync 時依單一等級的 pitch 清單算出）與
`combine_*`（build 時跨等級合併）。

| 檔案 | 內容 |
|---|---|
| `weighted.py` | `combine_pitch_type_data(entries, sc_key, rate_fields, include_pct)`：共用的「依球數加權平均」合併器，被下面所有球種表的 `combine_*` 共用；`put_away_pct` 一律另外用 `two_strike_count` 加權。 |
| `arsenal.py` | `compute_pitch_arsenal`（投手球種：球速/位移/轉速/延伸/進壘點＋好球率/引誘率/揮空率/致勝率/wOBA）/ `combine_pitch_arsenal` |
| `outcomes.py` | `compute_pitch_outcomes`（投手球種結果面：好球率/區內揮空率/引誘率/揮空進好球率/CSW/致勝率/對手打擊率/wOBA/桶身率/硬擊率）/ `combine_pitch_outcomes` |
| `vs_pitch_types.py` | `compute_vs_pitch_types`（打者對各球種的表現，同時排除 `BATTER_PLINKO_SKIP_TYPES={"EP","FA"}` 這類代打投球的雜訊球種，並在有具名球種時丟棄 UN 桶）/ `combine_vs_pitch_types` |
| `usage_by_count.py` | `compute_pitch_usage_by_count`（依球數優劣勢分桶統計球種配比）/ `combine_pitch_usage_by_count` |
| `bat_side_splits.py` | `compute_pitcher_bat_side_splits`（all/L/R 三份球種表）/ `combine_pitcher_bat_side_splits`（對舊資料缺 splits 欄位時 fallback 到頂層表當作 "all" split） |

### 3.8 統計彙整入口與跨等級合併

| 檔案 | 內容 |
|---|---|
| `pitcher_statcast.py` | `compute_pitcher_statcast(pitches)`：投手球季 Statcast 彙整入口，串接 `aggregate_pitches` → `compute_pa_outcome_totals` → `compute_pitcher_bat_side_splits` → 球路位移圖 (`graph.movement`) → Pitch Plinko (`graph.plinko`) → `discipline_metrics` → `batted_ball_metrics`，外加投手專屬的 `hr_fb_pct`/`avg_extension`。 |
| `batter_statcast.py` | `compute_batter_statcast(pitches)`：打者球季 Statcast 彙整入口，結構對稱但額外算 `max_ev`/`ev90`/`avg_la`/`swsp_pct`/`vs_pitch_types`，Pitch Plinko 依 `pitch_hand` 分 split 且排除 `BATTER_PLINKO_SKIP_TYPES`。 |
| `combine.py` | `combine_statcast_dicts(entries)`：舊 `builder.py` 跨等級合併邏輯的新家（舊文件優先度最高的建議，現在就放在它服務的 statcast 邏輯旁邊）。內部依三種加權基準分組（`pitch_pct_fields` 用 `total_pitches` 加權、`bbe_fields` 用 `bbe` 加權、`pa_fields` 用 `pa_count` 加權），`max_ev` 用 `max()` 而非平均，並把 `pitch_arsenal`/`vs_pitch_types`/`pitch_outcomes`/`pitch_usage_by_count`/`pitcher_bat_side_splits`/`pitch_plinko`/`pitch_movement` 都委派給各自的 `combine_*` 函式。 |

---

## 4. sync/ — 資料同步管線

`__init__.py` re-export `sync_database`/`update_database`（來自 `.players`）、
`sync_statcast`（來自 `.statcast`）。整個套件分兩條管線：

### 4.1 Pipeline A — `players.py`（基礎數據同步）

- `_is_first_sync(mlb_id, synced_ids)`：判斷是否為該球員第一次同步。
- `_fetch_player_data(pconf, year, fetch_all_years)`：thread-safe 的純抓取 worker；對已知非現役／退休球員有特殊處理（重複執行時跳過重量級請求，但首次回補仍會完整抓取）。
- `_write_player_to_db(conn, bundle, year)`：寫入 `players` 表；把 yearByYear + seasonAdvanced 寫進 `season_stats`（`fielding` 分割的 `gp` 特殊處理，避免蓋掉打擊/投球的 `gp`）；用依 `level_rank` 排序的 SQL `CASE` 更新球員目前等級/球隊；寫入 `game_logs`；寫入 `next_game` 快照。
- `_run_pipeline(db_path, roster_file, year, only_player, fetch_all_years, mode_label)`：兩階段（`ThreadPoolExecutor(max_workers=PLAYER_FETCH_WORKERS)` 平行抓取 → 循序寫入資料庫）；已知 `is_active=False` 的球員會跳過，除非是首次同步或指定 `--player`。
- `sync_database` / `update_database`：對外入口，分別是 `fetch_all_years=True`/`False` 的薄包裝。

### 4.2 Pipeline B — `statcast.py`（進階數據同步）

- `_fetch_and_extract_game(game_pk, players_in_game)`：抓單場 live-feed 並依球員抽取 pitch 清單，含角色 fallback（投打身份不明或雙向球員時，先試某個角色抽不到就試另一個）。
- `_pitches_need_hit_coord_backfill(pitches)`：判斷是否需要回補打擊座標。
- `_merge_statcast_into_season(cur, mlb_id, year, position, statcast_data, fip_constants_lookup, sport_level, sabermetrics, expected_stats)`：全模組最複雜的函式。只把 statcast/sabermetrics/expected-stats 寫進**對應的 sport_level 那一列**（防止同年多隊時寫錯列）；MiLB 用解出的 `c_fip` 算 FIP；MLB 用 sabermetrics 算 FIP+xFIP+WAR+xwpct；**WAR/wRC+ 只寫進該年第一筆 MLB 列**（用 `saber_written` 旗標控制），並附中文註解說明原因：wRC+ 與 WAR 是整季合計數值，若每支球隊記錄都各寫一次會造成轉隊球員的數字重複顯示。
- `_compute_player_statcast_bundle(mlb_id, db_path, position)`：平行 worker，各自開自己的唯讀 SQLite 連線，抓 sabermetrics（僅當該球員有 MLB 資料時）＋expectedStats（全等級皆抓），並呼叫 `compute_pitcher_statcast`/`compute_batter_statcast`。
- `sync_statcast(db_path, roster_file, year, only_player, update_constants)`：完整 5 階段管線：① 用輕量 live-feed 呼叫回補舊資料缺的 `sport_level` → ② 建立「尚未抓取」的 (球員, 比賽) 對照表 → ③ 平行抓取＋抽取 → ④ 寫入 pitch log（**空結果寫入 JSON `null` 而非 `[]`**，避免下次誤判為「已抓過但確實是空」而無限重抓）＋標記 `playbyplay_processed` → ⑤ 平行計算＋API 抓取後循序寫回資料庫。單次執行內用一個記憶體字典 `fip_constants_cache` 避免同一個 `(level, year)` 組合被每個球員各自重抓一次。

### 4.3 支援模組

| 檔案 | 內容 |
|---|---|
| `extract.py` | `_extract_runners(play)`：濃縮跑壘/守備功勞資料。`_condense_defense`/`_condense_offense`/`_condense_nonpitch_event`/`_pa_context`：4 個小 condenser，分別濃縮守備站位、攻方壘況、牽制/踏板事件、打席最終 WP/LI/drama 等 withMetrics 新節點。`extract_pitch_logs(game_data, player_id, role)`：走訪 withMetrics JSON，回傳 `(pitches, nonpitch_events)` 2-tuple——`pitches` 定義了 `game_logs.pitches_json` 快取 schema（含球種/結果/好壞球/好球帶座標/位移/轉速/擊球初速仰角/落點座標/計數/跑壘者，加上這次新增的 `play_id`/`pitch_number`/`sz_*`/`break_vertical`/`defense`/`offense`/PA-final WP/LI/drama 等約 25 個新欄位，共約 75 個欄位）；`nonpitch_events` 定義了 `game_logs.events_json` schema（`pickoff`/`stepoff` 非投球事件）。 |
| `field_maps.py` | `apply_yearbyyear_fields`（約 45 個投手欄位、25 個打者欄位，API camelCase → 內部 snake_case，經 `safe_float`/`safe_int`）、`apply_advanced_fields`（seasonAdvanced 專屬欄位：roe/wo/gidpo/xbh/babip/pitches_per_pa 等）。 |

---

## 5. render/ — 靜態網站渲染

`__init__.py` re-export `build_static_site`（來自 `.pages`）。

| 檔案 | 內容 |
|---|---|
| `env.py` | `create_jinja_env(template_dir, base_url, site_origin)`：註冊自訂 filter（floatformat/default_if_none/num_dash/tojson_safe/jsonld/pct_fmt/level_display）與 global（is_mlb/player_url/retired_player_url/static_url/headshot_cdn_urls/absolute_url/base_url/site_url/site_origin）。 |
| `filters.py` | `floatformat` / `default_if_none` / `num_dash`；`_json_html_safe`（把 `</` 轉義，避免 JSON 內容意外提前關閉 `<script>` 標籤）→ `tojson_safe` → `jsonld`；`pct_fmt`（用 `Decimal` + `ROUND_HALF_UP` 做百分比捨入，避免浮點誤差造成的捨入不一致）。 |
| `urls.py` | `HEADSHOT_CDN_TEMPLATE_MLB` / `_MILB`（Cloudinary 上 MLB Photos CDN 的兩種資產家族："67" vs "milb"）；`headshot_cdn_urls(mlb_id, latest_level_is_mlb)` 依球員最近一次「有出賽紀錄」的等級決定主/備選頭像順序；`make_url_helpers(base_url)` / `make_absolute_url(site_origin, base_url)`。 |
| `seo.py` | 站台層級常數（`SITE_TITLE`/`SITE_DESCRIPTION`/`SITE_SAME_AS`）與退役球員專屬文案；`player_display_name` / `player_canonical_path` / `player_description`；`index_structured_data`（WebSite + ItemList JSON-LD）/ `player_structured_data`（Person + BreadcrumbList JSON-LD）；`write_robots` / `write_sitemap`。 |
| `pitch_log.py` | `summarize_pitch_for_display(p)`：pitch dict 的精簡投影；`write_pitch_log_files(logs_by_year, out_dir, normalized_base_url, mlb_id)`：把逐場比賽的 pitch log 寫成延遲載入的獨立 JSON 檔（`data/pitchlogs/{mlb_id}/{game_id}.json`），並在每筆 log 上附加 `pitch_data_url`/`pitch_count`。 |
| `pages.py` | `_pick_display_stat(stats_current, player)`：三層優先序（完全同隊 > 目前等級相符 > 最高等級 fallback）。**`build_static_site(db_path, year, output_dir, base_url, roster_file, update_constants)`**——見下方說明，是本套件中唯一**尚未依照舊文件建議拆分**的大函式。 |

`build_static_site` 目前仍是單一函式（約 385 行），依序處理：載入 roster →
建輸出目錄 → 建 Jinja env → 開資料庫連線並跑 `init_db`（冪等）→ 用
`db.bundles.load_player_bundle` 載入所有球員 bundle → 呼叫
`annotate_wrc_plus` → 依 `is_active_player` 切分現役／退役名單 → 渲染首頁 →
渲染退役名單頁 → 逐球員渲染詳細頁（圖表資料、`compute_career` 生涯加總、
下一場比賽有效性檢查、透過 `combine_statcast_dicts` 為跨等級球季合成
`"_combined"` 條目、為只有 wRC+ 沒有實際 Statcast 資料的年份注入近乎空白的
statcast 條目）→ 渲染 404 頁 → 寫 sitemap/robots.txt → 寫 `.nojekyll`
標記檔。詳見 §11。

---

## 6. graph/ — 圖表資料

`__init__.py` 是純文件註解：「每個圖表模組各自擁有一組 `compute_*`（sync 時
依單一等級算）與 `combine_*`（build 時跨等級合併）配對函式」。

| 檔案 | 內容 |
|---|---|
| `movement.py` | `COMPUTE_MAX_POINTS = 700` / `COMBINE_MAX_POINTS = 900`；`compute_pitch_movement_chart(pitches, max_points)`：建立逐球 HB/IVB 散佈點（含降採樣）；`combine_pitch_movement(entries)`：跨等級合併，跳過 `sport_level == "_combined"` 的條目以避免重複計算。 |
| `plinko.py` | `_empty_plinko_nodes` / `_empty_plinko_edges`；`compute_pitch_plinko(pitches, *, split_field, split_specs, skip_types=None)`：建立依打者/投手慣用手分 split 的球數轉移圖（Pitch Plinko）payload；`combine_pitch_plinko(entries)`：跨等級加總原始計數。 |

---

## 7. util/ — 通用工具

零領域知識的泛用工具，被所有其他套件依賴，自己不依賴任何人。

| 檔案 | 內容 |
|---|---|
| `dates.py` | `TW_TZ`（UTC+8）、`parse_date`。 |
| `json.py` | `loads_json` / `loads_json_dict` / `loads_json_list` / `dumps_json`。 |
| `numbers.py` | `safe_float` / `safe_int`；`ratio(num, den, digits=3)`；`mean` / `mean_round`；`float_or_none`（與 `safe_float` 的差異：會拒絕 NaN/inf）。 |
| `obj.py` | `Obj(dict)`：屬性存取風格的字典類別，模板與各層資料結構的共同載體。 |
| `units.py` | `height_to_cm`（正規表示式解析）、`lbs_to_kg`。 |

---

## 8. 頂層模組：constants.py / levels.py / roster.py

### 8.1 `constants.py`（344 行）

分成三個區塊：

1. **路徑與執行期設定**：資料庫路徑、輸出目錄、`PLAYER_FETCH_WORKERS`、API/live-feed timeout 常數。
2. **年度常數**（開季要檢查/更新的區塊）：`SEASON_YEAR`（`_auto_season_year()` 自動跨年）、`LEAGUE_RA9` 表 + `get_league_ra9()`、`FIP_DEFAULT_CONSTANT = 3.2`。
3. **穩定的領域常數**：`SWING_CODES`/`WHIFF_CODES`/`CALLED_STRIKE_CODES`；`WOBA_WEIGHTS`/`WOBA_EVENT_MAP`/`WOBA_SCALE = 1.24`；`MIN_WRC_YEAR = 2021`；`TJSTATS_LEVEL_PARAMS`/`PF_LEVEL_PARAM`/`LC_LEVEL_CODE`/`WRC_LEVELS`；`NON_PA_EVENTS`；`BAT_SIDE_SPLITS`；`COUNT_USAGE_BUCKETS` + `COMBINED_COUNT_USAGE_BUCKETS`（程式碼內就有註解標明「未來可考慮與 COUNT_USAGE_BUCKETS 統一」，見 §10）；`PLINKO_COUNTS`/`PLINKO_COUNT_LABELS`/`PLINKO_EDGES`；`BATTER_PLINKO_SPLITS`/`PITCHER_PLINKO_SPLITS`/`BATTER_PLINKO_SKIP_TYPES = {"EP","FA"}`；`GB_TRAJECTORIES`/`LD_TRAJECTORIES`/`FB_TRAJECTORIES`/`PU_TRAJECTORIES`/`AIR_TRAJECTORIES`；`BATTED_BALL_RATE_DIGITS`；Gameday 噴射圖座標常數（`GAMEDAY_HOME_X/Y`、`GAMEDAY_SPRAY_CORRECTION`、角度門檻）；`HIT_LOCATION_ZONE` 座標缺失時的備援對照表；`COUNTING_FIELDS`（生涯／單季合併加總要用到的欄位清單）。

### 8.2 `levels.py`（149 行）

MLB/MiLB 等級邏輯的單一事實來源。`Tier` frozen dataclass；`TIERS` tuple 涵蓋
MLB(0)/AAA(1)/AA(2)/A+(3)/A(4)/A-(5，已於現代編制中淘汰)/ROK(6)/WIN(7)/
Minors(99)，同時保留現代與舊制顯示名稱、sportId、別名；
`resolve_tier`/`level_rank`/`level_display`（依 2021 年為分界的時代感知顯示）
/`is_mlb`/`sport_id_to_code`/`sport_name_to_code`/`tier_keys_ordered`。

### 8.3 `roster.py`（121 行）

docstring 明寫「仿照 `site_builder.levels` 的模式」設計，是相對於舊文件新增
的整併模組。`parse_roster_from_file`/`build_roster_map`；
`ROSTER_INJURED_CODES`/`ROSTER_RESTRICTED_CODES`/`ROSTER_OTHER_CODES`/
`ROSTER_INACTIVE_CODES` 四組狀態代碼集合；
`categorize_roster_status(code, is_active_entry, player_is_active)` 回傳
active/injured/restricted/inactive/other 五者之一；
`NATIONAL_TEAM_KEYWORD = "chinese taipei"`、`is_national_team_tx`、
`is_active_player(player, stats, year)`。

---

## 9. build.py — CLI 進入點

252 行，`argparse` 子命令：`sync` / `statcast` / `refresh` / `build` /
`all`。每個 `cmd_*` 函式都在函式本體內才 import `site_builder.sync`/
`site_builder.render` 的符號（而非放在檔案最上面），讓 CLI 的 `import
argparse` 保持輕量快速。`cmd_refresh` 依序執行 `update_database` →
`sync_statcast` → `build_static_site`（對應 CLAUDE.md 記載的每日排程）。
`cmd_all` 依序執行 `cmd_sync` → `cmd_statcast` → `cmd_build`；若同時指定
`--player` 與 `all` 會印出特別警告，因為 `build` 一律渲染完整名單，不會受
`sync`/`statcast` 的 `--player` 範圍限制。

---

## 10. 跨檔案重複與一致性檢查（對照舊文件）

舊文件（2026-07-01）列出的問題，逐項核對現況：

| 舊文件標記的問題 | 現況 |
|---|---|
| `_BAT_SIDE_SPLITS`/`_COUNT_USAGE_BUCKETS`/`_PLINKO_COUNTS`/`_PLINKO_EDGES` 在 statcast.py 與 builder.py 各自重複定義 | ✅ 已解決：全部統一收斂到 `constants.py` 單一定義，各處以 import 使用 |
| `_is_unknown_pitch_type` 重複定義 | ✅ 已解決：唯一定義在 `stats/core/pitches.py::is_unknown_pitch_type` |
| `_ratio` 重複定義 | ✅ 已解決：唯一定義在 `util/numbers.py::ratio` |
| `api/stats.py` MLB/MiLB try/except 不對稱 | ✅ 已解決：兩端點現在對稱地各自獨立 try/except |
| `api/games.py` timeout 字面值不一致 | ✅ 已解決：統一為 `LIVE_FEED_TIMEOUT` 常數 |
| 「致勝球比例（put-away%）」三處重複迴圈 | ✅ 已解決：唯一定義在 `stats/discipline/put_away.py::compute_put_away`，`put_away.py` 的 docstring 本身就寫著「之前是三處重複的同一段迴圈」 |
| `helpers.py` 215 行的 `_compute_advanced_stats` 該拆分 | ✅ 已解決：拆成 `stats/core/annotate.py::annotate_row` 調度一系列一檔一函式的模組 |
| `builder.py` 跨等級合併邏輯該搬到 statcast 附近 | ✅ 已解決：搬到 `stats/combine.py` + `graph/movement.py` + `graph/plinko.py` + `stats/tables/*.py` |
| `compute_pitcher_statcast`/`compute_batter_statcast` 的 `year`/`sport_level` 是 dead 參數 | ✅ 已解決：已移除，兩函式現在只吃 `pitches` 一個參數 |
| `compute_fip` 內部自己做 I/O 查常數 | ✅ 已解決：改成外部解出 `c_fip` 後傳入，`compute_fip` 本身零 I/O |
| （舊文件未提及，本次審閱新發現的 bug）投手 BABIP 分母 | ✅ 已修正：從 BF 基準改為 AB 基準，與打者版公式對稱，修正系統性低估（見 `stats/core/annotate.py` 內的中文註解） |
| （舊文件未提及）FIP 常數表、TJStats 常數表 | ✅ 已改進：從手抄靜態表格，改為即時反推計算／即時爬取，並依資料新鮮度差異分別套用兩種不同的 SQLite 快取策略（`db/fip_constants_cache.py` vs `db/tjstats_cache.py`，見 §2） |
| `builder.py::build_static_site` 應拆成 per-page-type 子函式 | ❌ **尚未解決**：`render/pages.py::build_static_site` 目前仍是單一約 385 行的函式，是舊文件所有建議中唯一沒有被落實的一項。詳見 §11。 |

以下兩點是本次審閱過程中發現、但認定為**刻意設計、非需要修正的問題**：

- `constants.py` 裡 `COUNT_USAGE_BUCKETS` 與 `COMBINED_COUNT_USAGE_BUCKETS`
  仍是兩張分開的表，程式碼自己已用註解標記「未來可考慮統一」——這是專案自我
  意識到、尚未執行的技術債，本文件在此如實轉達，不當作新發現提出。
- `stats/discipline/__init__.py::discipline_metrics()` 刻意不包含
  `compute_z_whiff_pct` 與 `compute_put_away`：這兩者服務的是球種層級細分表
  （`stats/tables/*.py`），而非球季層級彙整值，經 grep 確認在
  `stats/tables/` 與兩個 Jinja 模板中都有實際使用，屬於刻意的架構分工。

---

## 11. 觀察與建議

**headline 發現**：舊文件提出的所有拆分建議中，唯一沒有被執行的是
`render/pages.py::build_static_site` 這個約 385 行的單一函式。它一次處理
了：roster 載入、輸出目錄與 Jinja env 建立、資料庫連線與 schema 初始化、
全部球員 bundle 載入、wRC+ 標注、現役/退役名單切分、首頁渲染、退役名單頁
渲染、逐球員詳細頁渲染（含圖表資料組裝、生涯與跨隊加總、下一場比賽驗證、
跨等級 statcast 合成）、404 頁、sitemap/robots.txt、`.nojekyll` 標記檔。

相較之下，舊文件點出的其他所有問題——跨檔案常數重複、`_is_unknown_pitch_type`
重複定義、`_ratio` 重複定義、MLB/MiLB try/except 不對稱、timeout 字面值
不一致、致勝球比例三處重複迴圈、215 行的 `_compute_advanced_stats`、
跨等級合併邏輯的擺放位置、statcast 計算函式的 dead 參數——不僅全部解決，
拆分的細緻程度（一檔一函式）也遠超舊文件原本的建議範圍。這使得
`build_static_site` 相對顯眼：它是目前整個套件裡最後一個仍然遵循「舊風格」
（一個大函式處理一整個階段）的地方。

建議的拆分方向（比照 `stats/`、`graph/`、`db/` 已經驗證過的「依頁面類型切
子函式」模式）：

1. `_render_index(env, active_players, retired_players, ...)`
2. `_render_retired_page(env, retired_players, ...)`
3. `_render_player_page(env, player, stats, logs, conn, ...)`（目前佔
   `build_static_site` 篇幅最大的部分：圖表資料組裝、`compute_career`、
   下一場比賽驗證、跨等級 statcast 合成都可以在這裡獨立測試）
4. `_render_error_and_seo_pages(env, output_dir, ...)`（404、sitemap、
   robots.txt、.nojekyll）

`build_static_site` 本身可以縮成一個高層次的協調函式（載入資料 → 依序呼叫
上述 4 個子函式），如同 `sync/statcast.py::sync_statcast` 目前「5 個階段各
自獨立、由頂層函式依序呼叫」的組織方式。

其餘為次要觀察，不影響正確性，供未來參考：

- `COUNT_USAGE_BUCKETS` / `COMBINED_COUNT_USAGE_BUCKETS` 的統一（專案自己已
  用註解記錄此想法）。
- `stats/tables/*.py` 裡 `compute_pitch_arsenal`/`compute_pitch_outcomes`/
  `compute_vs_pitch_types` 三者的「依球種分組 → 逐組呼叫
  `aggregate_pitches`/`compute_pa_outcome_totals`」結構高度相似，未來若再新增
  第 4 張球種細分表，可以考慮把這段共用邏輯抽成 `tables/` 內部的輔助函式
  （目前 `weighted.py` 只共用了「合併」那一半，「計算」那一半仍是三份手寫
  迴圈——但目前只有三張表，重複量還不到需要強制抽象的門檻，暫不建議動）。

① 職責拆分是否過細 —— 這是最主要的問題

- 重災區:stats/batting/、stats/pitching/。13+13 個檔案裡多數是「1 docstring + 3~5 行函式」,而且多半只是 round(x/y, n)。建議併為 batting/rates.py + pitching/rates.py,可一併消掉 core/annotate.py:9-27 近 20 行 import。import 站點僅 6 處,合併風險低。
- 反向問題(檔案太大):sync/statcast.py 542 行把 game 抓取 / pitch 回寫 / sabermetrics 抓取 / FIP 計算 / merge 全塞一起;render/pages.py 454 行把 orchestration 與資料塑形(statcast_by_year 組裝 pages.py:330-375、chart data、fielding 聚合)混在單一 build 函式。兩者都可再切一層。
- 死程式碼:db/players.py:39-46 get_positions 全庫無呼叫。
- 相對地,stats/discipline/、stats/batted_ball/ 的細拆是合理的——它們各自持有一個「定義」(barrel 窗、hard-hit 門檻),且都吃共用的 aggregate_pitches 結果,不重複遍歷。

② 數據正確性

- combine.py / weighted.py 合計列加權(最實質):_wpct 對每個 rate 都用同一個權重欄位(total_pitches / bbe / count)。當 rate 的真實分母等於權重時(swing%、csw%、zone%、barrel%、gb/fb%)是精確的;但 whiff_pct(分母=揮棒數)、z_swing_pct/o_swing_pct(分母=區內/區外球)、z_contact_pct、hr_fb_pct(分母=飛球)被用 total_pitches/bbe 加權,只在「跨層合計(合計)」列會算出偏差值(可差幾個百分點)。正解:比照 career.py 對 AVG/OBP 的做法,存原始分子/分母並加總後重算,而非平均已算好的比率。
- xwpct.py:分子 FIP 是自責分尺度、分母 LEAGUE_RA9 是全失分尺度,系統性略高估;docstring 稱「Pythagenpat exponent 1.83」名稱有誤(1.83 是固定指數,非動態)。
- xbh.py:2B/3B/HR 皆為真實 0 時回 None 而非 0,有打數卻無長打者顯示空白。
- api/players.py:65-71:同函式 transactions 有 sorted(reverse=True),rosterEntries 卻直接 [0],取最新的假設未驗證。
- 兩個 cache 的 INSERT OR REPLACE:只 upsert 本次回傳的 league,某 league 這次沒回傳時舊列殘留。
- 邊界(低):era.py/whip.py 對 ER/BB 為 None 但 IP 存在時算出 0 而非 None(MLB 資料實務不缺,可接受)。

③ 小數精細度 / 截斷

- compute_ev90(exit_velocity.py:24):idx = min(int(len*0.9), len-1),int() 截斷 + 0-indexed,n=10 時直接取最大值 → EV90 偏高。註解已自承「小於 10 顆會與 TJStats 不符」,但 ≥10 也有系統性 off-by-one。建議用線性內插或一致的 nearest-rank。
- wOBA 兩種精度:compute_pitch_woba(woba.py:23,經 ratio 捨入到 3 位)vs compute_season_woba(woba.py:59,不捨入);前者的 3 位值又在 combine.py 被 PA 加權後再捨入(先捨再算)。應讓 pitch 版回未捨入值對齊。
- per-9 家族位數不一:k/bb/h 為 1 位、hr/rs 為 2 位。
- slash-line 型別混用:field_maps.py 把 win_pct/strike_pct/p_avg/p_obp/p_slg/p_ops/各 _pct 以 str() 存 DB;compute 版又回 fmt_avg 字串,opponent_slash.py:47-48 只好 safe_float 反解析回 float 才能算 OPS。
- 捨入模式不一致:filters.floatformat(Python 預設 round-half-even)vs filters.pct_fmt(ROUND_HALF_UP)。

④ 函式功能重複

- per-9 ×5、bb_pct≡k_pct(維度②同源)
- 三個 table builder(arsenal/outcomes/vs_pitch_types)骨架相同,僅 rate 欄位不同 → 可抽 build_pitch_type_table(pitches, columns_fn, ...)
- 兩個 cache 模組三組相同 load/save/get(僅 fip 多「進行中賽季強制重抓」)→ 抽 cached_lookup(load, fetch, save, force_refresh, always_refetch)
- api/stats.py 5 函式共 ~10 份相同 try/except/extend 樣板;api/tjstats.py 兩函式相同 requests→BeautifulSoup→select 流程
- pre-count 邏輯兩份:extract.py:96-182(抽取時計算)與 core/pitches.py:99-135 ensure_pre_strikes(cache 回填)各實作一次、reset 策略略不同
- type_name「有真名就升級」的小 pattern 散在 movement/plinko/usage_by_count 多處

⑤ 重造輪子 / 可重用既有 function

- batting/pitching counting 公式手寫 None-guard 除法,util.numbers.ratio() 早已存在(分母皆非負,not den 與 <=0 等價,可直接換)。注意:batted_ball 與 discipline 層已全面採用 ratio/mean_round,殘留主要在 batting/pitching。
- api/tjstats.py 用 print("WARNING") 而非 logging、手寫 float()+except 而非 float_or_none
- filters.jsonld 重複 dumps_json 的 compact separators(但需 Markup+HTML-safe,僅部分可重用)
- db/season_stats.load_season_row 用泛型 loads_json(...,{}) 而非既有 loads_json_dict/list
- 反例(做得對,值得肯定):sync/statcast.py 正確重用 compute_pitcher/batter_statcast,完全沒有重造逐球分類;graph/movement.py、graph/plinko.py 重用 core/pitches 的分類 helper;JSON 處理在 api/db 全走 util.json,無裸 json.loads。

⑥ 檔名是否符合功能

- pitching/strike_pct(counting,回字串)vs discipline/pitch_strike_pct(pitch-level,回 float):同名同顯示標籤「Strike%」但定義與型別皆不同 → 建議其一改名(如 strike_pct_counting)。
- babip.py/go_ao.py/p_per_pa.py:docstring 寫 batter+pitcher 共用,卻放 batting/(pitcher 版從 ..batting.* import)→ 宜移到 stats/core/ 或 stats/shared/。
- db/game_logs.py:名字像「game_logs 表存取層」,實際只有一個 pitch-cache 讀取函式;寫入散在 sync/players.py。db/players.py 同樣只讀、寫在 sync → 「db 層」持久化職責散落在 db/ 與 sync/ 兩處。
- api/games.py::sport_obj_to_abbr 較適合放 levels.py。
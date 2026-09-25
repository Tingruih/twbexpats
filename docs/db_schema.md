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
4. [playbyplay_processed（已刪除）](#4-playbyplay_processed已刪除)
5. [league_constant 快取表](#5-league_constant-快取表)
6. [play_videos / game_content_processed](#6-play_videos--game_content_processed)
6.3 [season_fetches](#63-season_fetches)
7. [表格間的邏輯關聯](#7-表格間的邏輯關聯)
8. [Schema 演進備註](#8-schema-演進備註)

---

## 0. 總覽：9 個 table 一覽

| Table | 用途 | 主鍵/唯一鍵 |
|---|---|---|
| `players` | 球員基本資料 + 最新一筆下一場賽事快取 | `mlb_id` UNIQUE |
| `season_stats` | 每個 `(球員,年,球隊)` 一列的球季數據（含 Statcast 彙整） | `(player_mlb_id, year, team_name)` UNIQUE |
| `game_logs` | 逐場數據 + 逐球/逐事件快取，每個角色一列 | `(player_mlb_id, game_id, role)` UNIQUE |
| `tjstats_park_factors` | tjstats.ca 球場因子快取 | `(year, level, team_name)` UNIQUE |
| `tjstats_league_constants` | tjstats.ca 聯盟 wOBA/R-PA 常數快取 | `(year, level_code, league)` UNIQUE |
| `league_fip_constants` | 自算 MiLB FIP 常數 + 整層 lgERA 快取 | `(year, sport_level, league_name)` UNIQUE |
| `play_videos` | 單一 play 的 highlight mp4 URL 快取 | `(game_pk, play_id)` UNIQUE |
| `game_content_processed` | 標記哪些比賽的 `/content` 已抓過 | `game_pk` PK |
| `season_fetches` | 過去球季的外部逐年資料「已成功抓過」登記 | `(source, subject, year)` PK |

---

## 1. `players`

| 欄位 | 型別 | Nullable/Default | 說明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | 內部 rowid |
| `mlb_id` | INTEGER | NOT NULL UNIQUE | MLB Stats API 球員 ID，全站主要查找鍵 |
| `name_en` | TEXT | NOT NULL | 英文姓名 |
| `name_tw` | TEXT | DEFAULT `''` | 中文姓名（來自 `roster.json`，非 API） |
| `team` | TEXT | DEFAULT `'N/A'` | 見 §8 備註：寫入後不會被 UPDATE 覆蓋 |
| `level` | TEXT | DEFAULT `'Minors'` | tier key。`sync/players.py::_write_player_to_db()` 的 level/team UPDATE 寫入：現役（`roster.is_active_player`）且有 currentTeam 時取 `/teams/{id}` 的 `sport.id`；否則對 `season_stats` 最近一季呼叫 `highest_level_row()`（優先有出賽的列） |
| `level_year` | INTEGER | nullable | `level` 對應的球季：現役且用 currentTeam = 目標球季（`constants.SEASON_YEAR`），其餘 = 選中那列 `season_stats` 的 `year`（退役球員的 currentTeam 仍是最後待過的球隊，不能配今年）。`level_display(level, level_year)` 靠它決定顯示 `A+` 或 `A(Adv)`；遷移前的列為 NULL，下一次 sync/refresh 寫入 |
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
| `history_synced` | INTEGER | NOT NULL DEFAULT `1` | 上次全歷史抓取（首次同步或 `sync` 指令）是否每個請求都成功；`0` 代表有請求失敗，下次 `refresh` 會再做一次全歷史抓取。既有列由 migration 補 `1`（視為已完成） |

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
抓取失敗時 `next_game_json` / `next_game_updated_at` / `next_game_for_season` 三欄都不更新，
保留上次的值；只有「確定七天內沒比賽」或球員已離隊才寫 `{}`。

**誰寫**：`sync/players.py::_write_player_to_db()`（player 主欄位 UPSERT + `next_game_json` 獨立 UPDATE + 全歷史抓取時的 `history_synced` UPDATE）。
**誰讀**：`db/bundles.py::load_player_bundle()`（渲染用）、`db/players.py::warn_orphaned_players()` / `get_cached_is_active()` / `get_incomplete_history_ids()`（sync 管線用）。

---

## 2. `season_stats`

| 欄位 | 型別 | Nullable/Default | 說明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | |
| `player_mlb_id` | INTEGER | NOT NULL | 邏輯上對應 `players.mlb_id` |
| `year` | INTEGER | NOT NULL | 賽季年 |
| `team_name` | TEXT | NOT NULL | 該列所屬球隊（同年跨隊會有多列） |
| `league_name` | TEXT | DEFAULT `''` | 所屬聯盟名（MiLB 用於配對 FIP/wOBA 常數） |
| `sport_level` | TEXT | DEFAULT `''` | tier key（`MLB`/`AAA`/`AA`/`A+`/`A`/`A-`/`ROA`/`ROK`/`WIN`，見 `levels.py`），寫入一律經 `levels.sport_to_tier_key()`；**不存舊制名稱**（`A(Adv)` 等由 `level_display(key, year)` 依年份產生）。API 無法對應的 sport（如獨立聯盟 `IND`）存 API 的 `abbreviation` |
| `stat_json` | TEXT | DEFAULT `'{}'` | 打擊/投球數據，見下 |
| `fielding_json` | TEXT | DEFAULT `'[]'` | 守備數據，見下 |

索引：UNIQUE `(player_mlb_id, year, team_name)`；`idx_season_stats_player_year ON (player_mlb_id, year)`。

### `stat_json`

這是全庫最複雜的欄位，內容分兩層寫入：

**第一層（`sync/players.py::_write_player_to_db()` 寫入，來自 yearByYear + seasonAdvanced 端點）**：

- `gp` / `p_gp`：hitting 分組的 `gamesPlayed` 寫 `gp`、pitching 分組寫 `p_gp`（經 `positions.role_field`）。兩者是不同的數（例：499614 2013 Frisco 打擊 125 場、投球 1 場），過去共用 `gp` 時後寫者蓋掉先寫者。fielding 分組的 `gamesPlayed` 是逐位置的，不寫進來
- P/PA：seasonAdvanced 的 `pitchesPerPlateAppearance` 兩個分組同名，hitting 寫 `pitches_seen_per_pa`（看球數 / PA）、pitching 寫 `pitches_per_bf`（用球數 / BF）；舊名 `pitches_per_pa` 已不再寫入
- 打擊/投球欄位由 `sync/field_maps.py::apply_yearbyyear_fields()` / `apply_advanced_fields()` 決定 key 名稱（如 `era`/`whip`/`ip`/`so`/`avg`/`obp`/…），**完整欄位對照表見 `docs/data_sources.md` §2.1、§2.2、§3.1、§3.2**，這裡不重複列。

**第二層（statcast 管線另外合併進同一個 dict）**：`statcast` / `expected`（與投球的 `p_` 版本）由 `sync/statcast.py::_attach_statcast()` 只寫入 `sport_level` 相符的那一列；其餘進階欄位由 `sync/advanced.py::sync_season_advanced()` 掃過每一列、依該列有出賽的角色（`stats/core/selectors.py::appeared_roles()`）寫入，不看該年有沒有逐球資料，也不看球員的主要守位。

**打擊/投球共用名稱的 key 一律拆開**（`positions.ROLE_SPLIT_FIELDS`，key 名由 `positions.role_field()` 決定）：打擊不加前綴、投球加 `p_`。一列同時容納兩個角色，所以不另加 `role` 欄位。render 端以 `positions.project_role()` 把主要角色的值投影到不帶前綴的 key。

| key | 型別 | 說明 |
|---|---|---|
| `statcast` / `p_statcast` | dict | 打擊：`stats/batter_statcast.py::compute_batter_statcast()`（`game_logs.role = 'batter'` 的逐球）；投球：`stats/pitcher_statcast.py::compute_pitcher_statcast()`（`role = 'pitcher'` 的逐球）。完整回傳值（`pitch_arsenal`/`pitch_outcomes`/discipline/batted-ball 等，key 清單見 `docs/functions_list.md` §3.8）。該角色在該 (年, 層級) 有逐球資料才寫，不設門檻 |
| `saber` / `p_saber` | dict | 僅 MLB。`api/stats.py::get_player_sabermetrics()` hitting / pitching group 的**整季合計** split `stat`（投球含 `fip`/`xfip`/`war`，打擊含 `war`/`wRcPlus`）；轉隊球員不取各隊 split（見 `sync/advanced.py::_season_total_saber()`），該年每一隊的 MLB 列都存同一份。當季每次重抓；過去球季抓過一次後登記在 `season_fetches`，之後 `fip`/`war`/`wrc_plus` 等欄位改由這份存下的整包重算 |
| `expected` / `p_expected` | dict | 僅 MLB。`api/stats.py::get_player_expected_stats()`（`group=hitting` / `group=pitching`）的原始回傳（`avg`/`slg`/`woba`/`wobaCon`）。只查該角色有 MLB 逐球資料的年份；抓取規則同 `saber`（`season_fetches` 的 `expected` / `p_expected`）；沒抓的年份保留既有值 |
| `fip` | float | **未捨入**（顯示時才捨入到兩位）。MiLB 由 `stats/advanced/fip.py::compute_fip()` 自算，該層級/年份沒有常數（2005 年以前 MiLB）時不存在此 key；MLB 直接取自 `saber.fip`（API 五位小數原值）。舊 DB 裡的值是兩位小數，下次 `statcast`（`sync_season_advanced` 每列都會重寫）後即更新 |
| `lg_era` | float | 該 `(sport_level, year)` 整層平均自責分，`xwpct` 的分母來源 |
| `xwpct` | float | `stats/advanced/xwpct.py::compute_xwpct(fip, lg_era)` |
| `xfip` | float | 僅 MLB，直接取自 `saber.xfip` |
| `war` / `p_war` | float | 僅 MLB，分別取自 `saber.war` / `p_saber.war`；兩個 group 各回自己的值（大谷翔平 2021：投球 2.96、打擊 5.02），不另存合計。整季值，該年每一隊的 MLB 列相同。`p_war` 與 `fip` 同時寫入（`p_saber` 缺 `fip` 時兩者都不寫） |
| `wrc_plus` | int | 僅 MLB、該列有打擊。`saber.wRcPlus` 四捨五入；整季值，該年每一隊的 MLB 列相同（render 以 `_first_not_none` 取值） |

`fip`/`xfip`/`lg_era`/`xwpct` 只由投球寫入、`wrc_plus` 只由打擊寫入，名稱不碰撞，維持不帶前綴。
存檔時 `stat_json` 的 key 依字母排序（`db/season_stats.py::save_season_row()`），同一份 API 資料不論回傳順序，存出的文字相同。

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
| `fielding_pct` | 守備率（float，API 已算好；分母為零的 `.---` 存 `None`。2026-09 以前寫入的列仍為 API 字串，重跑 `sync` 後更新） |
| `dp`/`tp` | 雙殺/三殺參與數 |
| `throwing_errors` | 傳球失誤 |
| `range_factor_game`/`range_factor_9` | 守備範圍值 |

**誰寫**：`sync/players.py::_write_player_to_db()`（基礎欄位）、`sync/statcast.py::_attach_statcast()`（`statcast`/`expected`/`p_statcast`/`p_expected`）、`sync/advanced.py::sync_season_advanced()`（`saber`/`p_saber`/`fip`/`xfip`/`war`/`p_war`/`wrc_plus`/`lg_era`/`xwpct`）。
**誰讀**：`db/bundles.py::load_player_bundle()`——讀出後把 `stat_json` 整包 `dict.update()` 攤平進同一個列物件（跟 `year`/`team_name`/`sport_level` 平級），不是巢狀存取。

---

## 3. `game_logs`

| 欄位 | 型別 | Nullable/Default | 說明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | |
| `player_mlb_id` | INTEGER | NOT NULL | |
| `date` | TEXT | NOT NULL | 比賽日期 |
| `game_id` | INTEGER | NOT NULL | 即 MLB `game_pk` |
| `role` | TEXT | NOT NULL | `positions.PITCHER`（`'pitcher'`）或 `positions.BATTER`（`'batter'`），由 gameLog 的 `stats[].group.displayName` 決定（`positions.role_for_stat_group()`）。gameLog 對該角色有 split 才有這一列；同場又投又打是兩列，`stats_json`/`pitches_json`/`events_json`/`pbp_version` 都只屬於該列的角色 |
| `opponent` | TEXT | NOT NULL | |
| `is_home` | INTEGER | nullable | |
| `game_type` | TEXT | NOT NULL | `R`=例行賽，`F`/`D`/`L`/`W`=季後賽各輪（見 `constants.py::GAME_LOG_GAME_TYPES`；其餘 API 回傳的 game type 一律不寫入） |
| `stats_json` | TEXT | DEFAULT `'{}'` | 該場 gameLog 數據，原封存 API 回傳，欄位命名同 `season_stats` 的 yearByYear 欄位（見 `docs/data_sources.md` §5） |
| `pitches_json` | TEXT | DEFAULT `'[]'` | 逐球資料，見下。`'[]'` = 尚未抓取或該球員這場以該角色沒有逐球資料（守備替補、代跑、打席中被換下前沒有球）；是否已抓看 `pbp_version`，不看這欄 |
| `events_json` | TEXT | DEFAULT `'[]'` | 逐非投球事件，見下 |
| `sport_level` | TEXT | DEFAULT `''` | tier key（`MLB`/`AAA`/`AA`/`A+`/`A`/`A-`/`ROA`/`ROK`/`WIN`，見 `levels.py`），寫入一律經 `levels.sport_to_tier_key()`；**不存舊制名稱**（`A(Adv)` 等由 `level_display(key, year)` 依年份產生） |
| `pbp_version` | INTEGER | DEFAULT `0` | 逐球資料以哪一版抽取程式抓到**完賽**資料（`constants.PBP_EXTRACT_VERSION`）；`< PBP_EXTRACT_VERSION` 就會（重）抓。比賽進行中抓到的部分資料照樣寫入 `pitches_json`，但本欄不更新，下次一定重抓（見 §8） |

索引：UNIQUE `(player_mlb_id, game_id, role)`；`idx_game_logs_player_date ON (player_mlb_id, date)`。

**`pitches_json`**（list，每球一筆 dict）：完整欄位來源對照表見
`docs/withmetrics_field_reference.md` §8.1（例如 `pitch_type`/`start_speed`/`ivb`/`hb`/
`zone`/`ev`/`la`/`is_pa_final`/`runners`/`pa_xwoba`/`sz_*` 等數十個欄位）。
擷取函式：`sync/extract.py::extract_pitch_logs()`（`PBP_EXTRACT_VERSION` 2）。

每顆球都歸「實際投、打那顆球的人」（對齊 Baseball Savant）：`role = 'pitcher'` 的列只有本人投出的球
（`pitcher_id` 全為本人），`role = 'batter'` 的列只有本人實際面對的球（`batter_id` 全為本人）。
以下欄位的語意因此與 `matchup`（打完打席的人）不同：

| 欄位 | 語意 |
|---|---|
| `pitcher_id` | 這顆球實際的投手：`playEvents[].defense.pitcher.id`，缺值退回 `matchup.pitcher.id` |
| `batter_id` | 這顆球實際的打者：打席起始打者為第一個代打事件（`offensive_substitution` 且 `position.code == "11"`）的 `replacedPlayer.id`，沒有代打時為 `matchup.batter.id`；每個代打事件之後換成該事件的 `player.id`。代跑（`"12"`）不影響 |
| `pitch_hand` | 實際投手這顆球的投球手：與 `matchup.pitcher` 相同時取 `matchup.pitchHand.code`，否則取 `gameData.players["ID<id>"].pitchHand.code`（`"S"`/缺值存 `""`） |
| `bat_side` | 實際打者這顆球的打擊邊：投打都與 `matchup` 相同時取 `matchup.batSide.code`，否則取 `gameData.players["ID<id>"].batSide.code`；左右開弓（`"S"`）取 `pitch_hand` 的反邊，`pitch_hand` 為 `""` 時存 `""` |
| `at_bat_index` | `allPlays[].atBatIndex`；打席邊界（`stats/core/pitches.py::iter_plate_appearances()`） |
| `is_pa_final` / `pa_event` / `pa_event_desc` / `runners` / `_pa_context()` 欄位 | 只在打席實際的最後一球；打席中換人時，被換下的人只有自己那段球、沒有結果（記給接手者，刻意不套用記錄規則 9.15(b) / 9.16(h)，見 `docs/fields.md`） |

**`events_json`**（list，僅 `pickoff`/`stepoff` 兩種事件）：欄位清單見同一份文件
§8.1 末段（`type`/`index`/`play_id`/`inning`/`pre_*`/`balls`/`strikes`/`outs`/
`result_code`/`result_desc`/`disengagement_num`/`from_catcher`/`runner_going`/
`is_out`/`pitcher_id`/`batter_id`；`pitcher_id`/`batter_id` 為事件當下實際的投打）。
投手列只收事件 `defense.pitcher.id`（缺值退 `matchup.pitcher.id`）為本人的事件，打者列只收
事件當下實際打者為本人的事件。**目前只被寫入，程式沒有任何讀取消費端**
（保留給未來的單場報告功能，見 `docs/data_sources.md` §10.2 的設計構想）。

**誰寫**：
- `sync/players.py::_write_player_to_db()`：`role`/`date`/`opponent`/`is_home`/`game_type`/`stats_json`/`sport_level` 初值（gameLog 階段，每個 group 一列，`ON CONFLICT(player_mlb_id, game_id, role)`）
- `sync/statcast.py`：`pitches_json`/`events_json`/`sport_level`/`pbp_version`（playByPlay 階段，`_fetch_and_extract_game()` 依列的 `role` 抽取、`_write_pitch_logs()` 依 `(player_mlb_id, game_id, role)` 寫；未完賽的比賽寫入部分資料但不更新 `pbp_version`）

**誰讀**：
- `db/bundles.py::load_player_bundle()`（渲染用逐場列表，只讀主要角色 `primary_role(players.position)` 的列，`events_json` 不讀）
- `db/game_logs.py::load_all_pitches_for_player()`（統計計算用，必須指定 `role`，只讀 `game_type='R'`（例行賽）的 `pitches_json`，依 `sport_level` 分組；跨層級 Statcast 合併靠這個函式取原始球）
- `db/play_videos.py::content_fetch_candidates()`（JOIN `game_id` 找需要補抓 highlight 影片的比賽）

---

## 4. `playbyplay_processed`（已刪除）

原本以 `game_pk` 記錄已抓過 playByPlay 的比賽。因為是以「比賽」為單位，球員後來才加入名冊時，他出賽的比賽已被標記，逐球資料永遠抓不到；
改為逐 (球員, 比賽, 角色) 判斷（現為 `game_logs.pbp_version`，見 `sync/statcast.py::_games_to_fetch()`）後就不再讀取。
`db/schema.py::init_db()` 以 `DROP TABLE IF EXISTS` 移除。

---

## 5. `league_constant` 快取表

三張表都由 `site_builder/league_constant/` 依 `RefreshPolicy`（見 `league_constant/policy.py`）決定何時重抓，`db/` 本身不碰這幾張表。

### 5.1 `tjstats_park_factors`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `year` | INTEGER | NOT NULL |
| `level` | TEXT | NOT NULL，tier key（只有 `MLB`/`AAA`/`AA`/`A+`/`A`）；轉成 TJStats 網址參數的規則見 `api/tjstats.py::TJSTATS_LEVEL_PARAMS` |
| `team_name` | TEXT | NOT NULL |
| `pf_final` | REAL | NOT NULL，最終球場因子 |
| `league` | TEXT | NOT NULL，該隊所屬聯盟 |

UNIQUE `(year, level, team_name)`。來源：`api/tjstats.py::fetch_park_factors()`。
誰寫/讀：`league_constant/batting.py::_load_park_factors()` / `_save_park_factors()`。

### 5.2 `tjstats_league_constants`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `year` | INTEGER | NOT NULL |
| `level_code` | TEXT | NOT NULL，TJStats 表格自己的拼法（`mlb`/`aaa`/`aa`/`hi-a`/`lo-a`，見 `api/tjstats.py::LC_LEVEL_CODE`） |
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
| `sport_level` | TEXT | NOT NULL，tier key；抓取時用該 tier 的 `sport_ids[0]`（例如 `ROA` 用 sportId 5442） |
| `league_name` | TEXT | DEFAULT `''`，**空字串代表該層級整體聚合列**（非某個特定聯盟），是 `sync/advanced.py::_milb_fip_fields()` 找 `level_wide`/`own_league` fallback 用的 sentinel row |
| `fip_constant` | REAL | NOT NULL |
| `lg_era` | REAL | DEFAULT `0`，`0` 被視為 cache miss（見 §8） |

UNIQUE `(year, sport_level, league_name)`。來源：`api/league_stats.py::fetch_team_league_map()` +
`fetch_team_pitching_totals()` → `stats/advanced/fip.py::compute_league_fip_constant()`。
誰寫/讀：`league_constant/pitching.py::_load()` / `_save()` / `_fetch_and_compute()`。
解不出常數的過去球季（2005 年以前 MiLB 沒有 `earnedRuns`）不會有列，改由 `season_fetches`
（`source = 'fip_constants'`）記錄「已抓過」，避免每次執行重抓。

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
`retry_cutoff_date` 之後被視為候選重試（影片可能延遲上架）。`/content` 抓取失敗
的比賽不寫入此表，所以不論日期多舊，下次都還是候選。
誰寫/讀：`db/play_videos.py::mark_content_processed()` / `content_fetch_candidates()`。

### 6.3 `season_fetches`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `source` | TEXT | NOT NULL，資料來源：`sabermetrics` / `expected`（打擊 expectedStatistics）/ `p_expected`（投球 expectedStatistics）/ `fip_constants`（常數定義在 `db/season_fetches.py`） |
| `subject` | TEXT | NOT NULL，`sabermetrics`/`expected`/`p_expected` 為球員 mlb_id（字串），`fip_constants` 為 tier key |
| `year` | INTEGER | NOT NULL，**只會有過去球季**：當季（`constants.is_season_in_progress()`）不登記 |
| `fetched_at` | TEXT | NOT NULL，UTC ISO 時間 |

PK `(source, subject, year)`。用途：外部 API 的逐年資料「當季每次重抓、過去球季成功抓過一次後
不再抓」。API 成功但沒有資料（2015 年以前沒有 expected stats、2005 年以前 MiLB 解不出 FIP 常數）
也會登記，抓取失敗（`FetchError`）不登記、下次重試。`--full-history`（`sabermetrics`/`expected`/`p_expected`）與
`--update-constants`（`fip_constants`）忽略此表全部重抓。換季後上一季不在表內，會再抓一次拿到最終值。
誰寫/讀：`db/season_fetches.py::mark_fetched()` / `load_fetched()` / `needs_fetch()`（呼叫端：
`sync/advanced.py::sync_season_advanced()`、`sync/statcast.py::_aggregate_statcast()`、
`league_constant/pitching.py::PitchingConstants`）。新表不需回填：空表等於全部沒抓過。

---

## 7. 表格間的邏輯關聯

SQLite 沒有宣告 FOREIGN KEY，以下關聯純靠程式邏輯維持一致：

- `players.mlb_id` ← `season_stats.player_mlb_id`、`game_logs.player_mlb_id`（一對多）
- `game_logs.game_id` ↔ `play_videos.game_pk` ↔
  `game_content_processed.game_pk`：同一個 MLB `game_pk`，只是不同表欄位名不同
  （`game_id` vs `game_pk`）
- `season_stats.(year, sport_level, league_name)` 與 `league_fip_constants.(year, sport_level, league_name)`、
  `season_stats.(year, sport_level)` 與 `tjstats_park_factors.(year, level)` /
  `tjstats_league_constants.(year, level_code, league)`：不是 DB 層 JOIN，
  是 `sync/statcast.py` 和 `render/pages.py` 在 Python 端用 dict lookup 配對。
  `season_stats`/`game_logs`/`league_fip_constants`/`tjstats_park_factors` 的層級欄位
  都是 tier key，直接字串相等即可；只有 `tjstats_league_constants.level_code` 是
  TJStats 拼法，轉換規則見 `api/tjstats.py` 的 `PF_LEVEL_PARAM`/`LC_LEVEL_CODE`
- `game_logs.(player_mlb_id, role)` 與 `pitches_json[].batter_id`/`pitcher_id`：
  `role = 'pitcher'` 的列每顆球 `pitcher_id == player_mlb_id`，`role = 'batter'` 的列
  每顆球 `batter_id == player_mlb_id`（兩者都是該球實際的投打，見 §3）

---

## 8. Schema 演進備註

`init_db()` 的執行順序是：先跑一大段 `executescript()`（多個 `CREATE TABLE IF NOT EXISTS`），
再依序跑好幾個 `ALTER TABLE ... ADD COLUMN`（`_add_column()`：只忽略 "duplicate column name"，
其他 `OperationalError` 例如資料庫被鎖照常丟出），
最後才建立 `play_videos`/`game_content_processed`。實際核對後：

- **`game_logs.role`、打擊/投球角色拆分（2026-09-25）：必須刪除 DB 從頭重建。**
  `game_logs` 改為每個角色一列（`UNIQUE(player_mlb_id, game_id, role)`），`season_stats.stat_json`
  的 `gp`/`statcast`/`expected`/`saber`/`war` 依角色拆成打擊與 `p_` 投球兩組、P/PA 改名為
  `pitches_seen_per_pa` / `pitches_per_bf`，逐球資料改歸實際投打的人（`PBP_EXTRACT_VERSION` 2，
  見 §3）。舊表的唯一鍵與逐球資料都無法就地轉換，**不做遷移**：`init_db()` 發現既有 `game_logs`
  沒有 `role` 欄位時直接 `SystemExit`（`_require_game_logs_role()`，結構檢查，不回補），避免 CI
  拿舊 DB 靜默寫出錯誤資料。重建方式：

  ```bash
  rm data/tracker.sqlite3
  python build.py all      # sync → statcast → build，自動帶 --full-history；約 1.5 萬場逐球資料全部重抓
  ```

  完成後把新 DB 上傳 Google Drive 取代舊檔。因為是全新 DB，不需要清除舊 key。
  `game_logs` 的所有欄位（含 `sport_level`、`pbp_version`、`pitches_json`、`events_json`）
  都寫在 `CREATE TABLE` 裡，`game_logs` 的 `ALTER TABLE` 遷移與 `_drop_column()` 已刪除。
- **`players.roster_status_code`、`players.roster_is_active`、`league_fip_constants.lg_era`
  已經被直接寫進 `CREATE TABLE` 那段 script 裡**，所以後面對應的 `ALTER TABLE ADD COLUMN`
  現在對全新資料庫來說是死程式碼（`_add_column()` 遇到欄位已存在會靜默跳過）；
  它們仍然有用，只是只服務「建表當時比這次更新還舊」的既有資料庫。
- **`game_logs.hit_coord_checked` → `pbp_version`（2026-09）**：`hit_coord_checked`
  是補抓落點座標時加的旗標，避免 API 本來就沒有座標的比賽每次重抓；`pitches_json`
  另用 JSON `null` 表示「抓過但沒資料」。兩者合併成抽取版本號（見
  `constants.PBP_EXTRACT_VERSION`）：`init_db()` 新增 `pbp_version`（DEFAULT 0）並
  `DROP COLUMN hit_coord_checked`。既有列的版本**不在 `init_db()` 回填**，改用下列
  一次性 SQL；沒跑的話所有列都是版本 0，下次 `statcast` 會把全部比賽（約 1.6 萬場
  withMetrics）重抓一次，結果正確但很慢。必須在新程式第一次執行**之前**對資料庫執行
  （之後 `hit_coord_checked` 已被刪除）：

  ```sql
  ALTER TABLE game_logs ADD COLUMN pbp_version INTEGER NOT NULL DEFAULT 0;
  -- 舊版寫入過的列（'null' = 抓過但沒資料）視為版本 1；
  -- hit_coord_checked = 0 的列原本就還要補抓座標，維持 0
  UPDATE game_logs SET pbp_version = 1
   WHERE pitches_json != '[]' AND hit_coord_checked = 1;
  UPDATE game_logs SET pitches_json = '[]' WHERE pitches_json = 'null';
  ALTER TABLE game_logs DROP COLUMN hit_coord_checked;
  ```

  （歷史紀錄：這段遷移已被上面的角色拆分取代，現行 `init_db()` 不再處理 `hit_coord_checked`。）
- **層級欄位統一存 tier key、`players.level_year`（2026-09）**：之前 `season_stats`
  存 API 原始 `abbreviation`（`A(Adv)`、`A (Full)`…）、`game_logs` 有兩個寫入端
  各存一種拼法、`players.level` 兩種混存，`ROA` 還被當成 `ROK` 的別名（實際是
  sportId 5442）。改成所有寫入端經 `levels.sport_to_tier_key()` 後，既有資料以
  一次完整回填重寫（沒有寫在 `site_builder` 內的回補程式碼）：

  ```sql
  -- 舊拼法的常數列不會再被讀到；ROA 舊列是從 sportId 16 算的，數值錯誤
  DELETE FROM league_fip_constants
   WHERE sport_level NOT IN ('MLB','AAA','AA','A+','A','A-','ROA','ROK','WIN','Minors')
      OR sport_level = 'ROA';
  ```

  接著執行 `python build.py all --update-constants`，重寫 `season_stats`/`game_logs`/
  `players`（含新欄位 `level_year`）並重抓常數。`sync` 會略過 `players.is_active = 0`
  的球員（見 `sync/players.py::_run_pipeline`），他們要逐一用 `--player` 強制重抓，
  再刪一次舊拼法常數列（advanced 階段會用這些球員尚未重寫的舊拼法把常數列寫回去），
  最後重跑 `statcast` 與 `build`：

  ```bash
  for id in $(sqlite3 data/tracker.sqlite3 "SELECT mlb_id FROM players WHERE is_active = 0"); do
    python build.py sync --player "$id"
  done
  sqlite3 data/tracker.sqlite3 "DELETE FROM league_fip_constants WHERE sport_level NOT IN
    ('MLB','AAA','AA','A+','A','A-','ROA','ROK','WIN','Minors')"
  python build.py statcast && python build.py build
  ```
- **`players.history_synced`（2026-09）**：同時寫在 `CREATE TABLE` 與 `_add_column()`
  migration。`DEFAULT 1` 讓既有列視為已完成全歷史同步，不需要回填；只有之後
  全歷史抓取有請求失敗時才會被寫成 `0`。
- `league_fip_constants.lg_era` 的 `DEFAULT 0` 是刻意設計：`league_constant/pitching.py::_load()`
  把 `lg_era <= 0` 視為 cache miss，所以舊資料（遷移前寫入、只有 `fip_constant`
  沒有 `lg_era`）會在下次讀取時自動觸發重新抓取自我修復，不需要額外的 backfill script。
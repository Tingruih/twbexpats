# Taiwan MLB Tracker — 未修復 Bug 整合清單

檢查日期：2026-07-10  
來源文件：`docs/BUG_REVIEW.md`、`docs/CODE_REVIEW_FIX_PLAN.md`、`docs/CODE_REVIEW_REPORT.md`、`docs/TODO.md`

> 說明：`site_builder` 已重構成子套件，以下位置皆以目前程式碼重新定位，不沿用舊文件行號。此文件只列「目前仍可在程式碼中確認未修」或「仍需修正/驗證的 bug」。純架構重構、一般 DRY 建議、已修復項目放在附錄。

> 2026-07-28：跨層級「合計」的整套加權演算法已移除，改由該年度所有層級的原始逐球資料池化重算（設計見 `docs/superpowers/specs/2026-07-28-statcast-level-tables-and-cross-level-totals-design.md`）。#7、#8、#9、#14、#43、#44 因此解除，移至附錄 A。編號保留空號以免既有交叉引用錯位。

## P0 / P1 — 優先修

### 2. `build_static_site()` 仍會無 guard 刪除輸出目錄

- 目前位置：`site_builder/render/pages.py`
- 證據：`out_dir = Path(output_dir).resolve()` 後，若存在即 `shutil.rmtree(out_dir)`。
- 影響：誤傳 `--output .`、專案根目錄、家目錄等可能造成大量資料刪除。
- 建議修法：限制 `out_dir` 必須在專案根目錄內，且不可等於專案根目錄；不安全時直接 raise。

### 3. `season_stats` UNIQUE key 仍缺 `sport_level`

- 目前位置：`site_builder/db/schema.py`、`site_builder/db/season_stats.py`
- 證據：schema 是 `UNIQUE(player_mlb_id, year, team_name)`；UPSERT 也是 `ON CONFLICT(player_mlb_id, year, team_name)`。
- 影響：同球員同年同隊名但不同層級時可能互蓋。
- 建議修法：migration 改為 `UNIQUE(player_mlb_id, year, team_name, sport_level)`，UPSERT 同步更新。

### 4. `game_logs` UNIQUE key 仍無 role/stat_type，二刀流同場投打可能互蓋

- 目前位置：`site_builder/db/schema.py`、`site_builder/sync/players.py`
- 證據：schema 是 `UNIQUE(player_mlb_id, game_id)`；game log UPSERT 同樣只用 `(player_mlb_id, game_id)`。
- 影響：同一球員同場同時有 hitting/pitching game log 時，後寫入者覆蓋前者。
- 建議修法：新增 role/stat_type 欄位，UNIQUE 改為 `(player_mlb_id, game_id, role)` 或 `(player_mlb_id, game_id, stat_type)`。

### 5. 桌機版 tabs 仍是不可鍵盤操作的 `<label>`

- 目前位置：`src/templates/player_detail.j2`、`src/static/js/tabs.js`
- 證據：tab nav 使用 `<label data-tab=...>`；JS 只綁 `click`，沒有 `role="tab"`、`aria-selected`、`keydown`。
- 影響：鍵盤和輔助科技無法正確操作桌機版分頁。
- 建議修法：改為 `<button role="tab">` + `role="tablist"` / `aria-controls` / `aria-selected`，並補 ArrowLeft/ArrowRight 鍵盤切換。

### 6. 球員頁仍雙重渲染桌機與手機 DOM

- 目前位置：`src/templates/player_detail.j2`
- 證據：同頁同時 include `tabs/*.j2` 與 `mobile/m_player_detail.j2`，再靠 CSS 顯示/隱藏。
- 影響：HTML/DOM 幾乎翻倍；hidden panels 仍會被下載與解析，桌機/手機也重複維護同一組欄位。
- 建議修法：短期先去重內嵌 JSON；中期抽共用 macro；長期收斂成單一 responsive markup。

## P2 — 數據正確性 / 安全健壯性

### 7–9. （已修，見附錄 A）

### 10. （已修，見附錄 A）

### 11. `ci` 有寫入但未納入 career/combined counting fields

- 目前位置：`site_builder/sync/field_maps.py`、`site_builder/constants.py`
- 證據：hitting mapping 寫入 `"ci"`，但 `COUNTING_FIELDS` 沒有 `"ci"`。
- 影響：單季列可能有 CI；生涯/合計列不會加總。
- 建議修法：把 `"ci"` 加入 `COUNTING_FIELDS`，或移除不使用的寫入。

### 12. WHIP 在 `bb is None` 時仍把 BB 當 0

- 目前位置：`site_builder/stats/pitching/whip.py`
- 證據：只檢查 `hits_allowed is None`，公式使用 `(bb or 0)`。
- 影響：若安打數存在但 BB 缺值，WHIP 會被靜默低估。
- 建議修法：`hits_allowed` 與 `bb` 都必須非 `None` 才計算。

### 13. （已修，見附錄 A）

### 14. （已修，見附錄 A）

### 15. （已修，見附錄 A）


### 17. EV90 percentile index 仍有 off-by-one

- 目前位置：`site_builder/stats/batted_ball/exit_velocity.py`
- 證據：`idx = min(int(len(ev_values) * 0.9), len(ev_values) - 1)`；n=10 時取 index 9。
- 影響：10 的倍數樣本會把 90th percentile 取到下一個 rank，n=10 時直接取最大值。
- 建議修法：nearest-rank 用 `ceil(n * 0.9) - 1`；或改線性內插並明確寫進 docstring。

### 18. Switch hitter / unknown bat side 的 spray direction 仍會走右打邏輯

- 目前位置：`site_builder/stats/batted_ball/spray.py`
- 證據：`bat = p.get("bat_side", "R")`；非 `"L"` 全部走右打分支。
- 影響：`"S"` 或未知打擊側會被誤判為右打拉打/反方向。
- 建議修法：只有 `"L"` / `"R"` 才分類；其他回傳 `None`。

### 19. `next_game` 快照有效性仍過寬

- 目前位置：`site_builder/render/pages.py`
- 證據：`player.next_game_for_season in (None, year) or ... >= datetime.date.today().year`。
- 影響：以舊年度 build 或資料異常時，可能顯示不屬於該頁年度的未來賽程。
- 建議修法：只接受 `{year, current_year}`，或更嚴格只接受 build year。

### 20. `get_next_game()` 仍用本機日期作 API 查詢起點

- 目前位置：`site_builder/api/schedule.py`
- 證據：`today = datetime.date.today()`，但顯示時間轉為 `TW_TZ`。
- 影響：CI / 本機時區與台灣日期不同時，7 天查詢窗口可能偏一天。
- 建議修法：`today = datetime.datetime.now(TW_TZ).date()`。

### 21. sabermetrics 寫入條件仍可能讓 MLB 列漏寫

- 目前位置：`site_builder/sync/statcast.py`
- 證據：外層已 `row_sport_level == "MLB"`，內層又要求 `not sport_level or row_sport_level == sport_level`。
- 影響：如果目前 merge 是 AAA/AA 層級觸發，MLB sabermetrics 不會寫入 MLB row，需等待另一次 MLB merge 才補上。
- 建議修法：sabermetrics 只看 `row_sport_level == "MLB"`，不要受當前 `sport_level` 限制。

### 22. expected stats 仍用 `any()` 判斷，合法 `0.0` 會被當無資料

- 目前位置：`site_builder/sync/statcast.py`
- 證據：`if not any([xba, xslg, xwoba, xwobacon]): continue`。
- 影響：若 API 回傳合法 0.0，整筆 expected stats 會被略過。
- 建議修法：改成 `if all(v is None for v in (...))`。

### 23. MiLB FIP constant fallback 仍缺明確警告

- 目前位置：`site_builder/db/fip_constants_cache.py`、`site_builder/stats/advanced/fip.py`、`site_builder/sync/statcast.py`
- 證據：`get_fip_constants()` 取不到 live/cached constants 時回空 dict；`sync/statcast.py` 傳入 `c_fip=None`；`compute_fip()` 直接 fallback 到 `FIP_DEFAULT_CONSTANT`。
- 影響：使用者和維護者無法從 log 看出某些 FIP 使用的是 generic fallback，而不是該層級/年度/聯盟常數。
- 建議修法：在 constants lookup 空值或 `c_fip is None` 時 log warning，含 `sport_level`、`year`、`league_name` 與 fallback 值。

### 24. `playbyplay_processed` 表仍是只寫不讀，且語意仍是 per-game

- 目前位置：`site_builder/db/schema.py`、`site_builder/sync/statcast.py`
- 證據：sync docstring 仍寫「game_pk is not in playbyplay_processed」，但 Phase 1 判斷只看 `game_logs.pitches_json` / `hit_coord_checked`；最後才 `INSERT OR REPLACE INTO playbyplay_processed`。
- 影響：表本身不參與去重；而 per-game processed 狀態也不適合「新增球員後補抓同場資料」這個需求。
- 建議修法：若保留，改成 per-player-game processed 欄位（例如 `game_logs.pitches_processed_at`）；否則移除表和 docstring。

### 25. 空 pitch cache 判斷仍不完全一致

- 目前位置：`site_builder/db/game_logs.py`、`site_builder/sync/statcast.py`
- 證據：有些查詢排除 `'null'`，有些只檢查 `None` / `"[]"`。
- 影響：已知無逐球資料的 game 可能在不同流程中被當成有資料或需重抓。
- 建議修法：定義共用 `EMPTY_PITCHES = (None, "[]", "null")`，所有讀寫判斷一致使用。

### 26. Jinja filters 仍未把 NaN 當缺值

- 目前位置：`site_builder/render/filters.py`
- 證據：`floatformat(float("nan"))` 會格式化成 `nan`；`pct_fmt(float("nan"))` 有機會顯示 `NaN%`。
- 影響：資料計算或 API 產生 NaN 時會直接出現在頁面。
- 建議修法：用 `math.isfinite()` / Decimal finite check，把 NaN/inf 視為缺值。

### 27. `safe_int("3.0")` 仍回 default

- 目前位置：`site_builder/util/numbers.py`
- 證據：`safe_int()` 直接 `int(value)`，字串 `"3.0"` 會 `ValueError`。
- 影響：若 API 或中間資料以 `"3.0"` 表示整數，會被靜默轉成 default。
- 建議修法：先走 `safe_float()` 再 `int()`，並視需求拒絕非整數小數。

### 28. `ip_to_outs()` 仍未防非法棒球小數

- 目前位置：`site_builder/stats/core/innings.py`
- 證據：`thirds = round((ip_value - whole) * 10)`，例如 `7.5` 會變成 5 個 thirds。
- 影響：非法 IP notation 會產生不可能的 outs。
- 建議修法：只接受小數位 0/1/2；其他回傳 default、clamp 或 raise/log。

## P3 — 低優先 / 邊界 / 維護性但仍是未解問題

### 29. 首頁 `data-level-order` 仍用 `loop.index`

- 目前位置：`src/templates/index.j2`
- 證據：`data-level-order="{{ loop.index }}"`。
- 影響：目前依賴上游已按 level 排序；若 builder 改排序，前端「層級」排序會靜默錯。
- 建議修法：builder 預先放 `item.level_order = level_rank(player.level)`，模板輸出該值。

### 30. （已修，見附錄 A）

### 31. Mobile pitch-log 預載仍用 inline style 字串 selector

- 目前位置：`src/static/js/mobile/m-pitch-log.js`
- 證據：`querySelector('.m-gamelog-year[style="display: flex;"], ...')`。
- 影響：顯示邏輯若改 class 或 inline style 多一個屬性，預載會失效。
- 建議修法：用 `.is-active` class，或用 JS 判斷 `el.style.display !== "none"`。

### 32. （已修，見附錄 A）

### 33. Chart.js 仍依賴第三方 CDN

- 目前位置：`src/templates/player_detail.j2`
- 證據：仍載入 `https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js`。
- 影響：雖已 pin 版本且有 SRI，但仍有第三方 request、離線/網路失敗風險；`CODE_REVIEW_FIX_PLAN.md` 的最終驗收要求 `cdn.jsdelivr.net` 為 0。
- 建議修法：vendor 到 `src/static/vendor/chart.umd.min.js` 或建立受控資產流程。

### 34. 全站仍每頁載入同一份 bundled CSS

- 目前位置：`src/templates/base.j2`、`site_builder/render/pages.py`
- 證據：所有頁面都 `<link rel="stylesheet" href=".../css/style.css">`；build 時雖已 bundle 消除 `@import` 瀑布，但沒有 per-page CSS。
- 影響：首頁/退役頁仍下載球員頁 tab、gamelog、advanced、chart、mobile 等樣式。
- 建議修法：拆 `common.css` + page-specific CSS，或 build 時產生不同 entry bundles。

### 35. Cloudflare Insights beacon 仍每頁載入

- 目前位置：`src/templates/base.j2`
- 證據：base template 無條件載入 `https://static.cloudflareinsights.com/beacon.min.js`。
- 影響：每頁都有第三方 JS/privacy overhead；本地 build 也會輸出該 script。
- 建議修法：只在 production deploy 注入，或用 build flag 控制。

### 36. 球種顏色/名稱 JS 常數仍在兩個圖表檔重複

- 目前位置：`src/static/js/pitcher-charts.js`、`src/static/js/pitch-plinko.js`
- 證據：兩檔都定義 `PITCH_COLORS` / `PITCH_NAMES`。
- 影響：新增或修正球種名稱/顏色需改兩處，容易漂移。
- 建議修法：抽 `pitch-meta.js` 或掛在 `window.TW` 的單一來源，兩個圖表共用。

### 37. （已修，見附錄 A）

### 38. CSS 仍有多處 `!important`

- 目前位置：`src/static/css/gamelogs.css`、`src/static/css/stats.css`、`src/static/css/charts.css`
- 證據：仍可搜尋到多處 `!important`。
- 影響：後續狀態樣式容易演變成 specificity 戰爭。
- 建議修法：把需要覆蓋 hover/繼承的 selector 寫得更明確，逐步移除 `!important`。

### 39. `build.py` 仍重複宣告 `--roster`

- 目前位置：`build.py`
- 證據：多個 subparser 各自 `add_argument("--roster", ...)`。
- 影響：改預設值/說明時需改多處。
- 建議修法：抽 common parent parser。

### 40. `get_player_profile()` 的 `is_active` 預設仍與 roster active 不一致

- 目前位置：`site_builder/api/players.py`
- 證據：`is_active` 缺失時預設 `True`；`roster_is_active` 缺失時預設 `False`。
- 影響：API 缺欄位時可能偏向把球員當現役。
- 建議修法：統一預設策略，或明確註解為刻意 conservative choice。

### 41. Transactions 排序鍵與顯示日期仍不一致

- 目前位置：`site_builder/api/players.py`
- 證據：transactions 以 `t.get("date", "")` 排序，但輸出日期使用 `effectiveDate or date`。
- 影響：當 `effectiveDate` 與 `date` 不同或其中之一缺失時，「最新交易」與交易列表順序可能和顯示日期不一致。
- 建議修法：排序鍵與輸出欄位使用同一個 normalized date，例如 `effectiveDate or date`。

### 42. `get_next_game()` 時間解析失敗 fallback 格式仍不一致

- 目前位置：`site_builder/api/schedule.py`
- 證據：正常路徑輸出 `"%m/%d %H:%M (UTC+8)"`；parse 失敗時使用 `game_date_str[:16]`，通常是 UTC ISO 片段。
- 影響：頁面可能混用 UTC ISO 片段與 UTC+8 顯示格式，造成使用者誤判開賽時間。
- 建議修法：fallback 也標明原始時區/格式，或回傳空字串並記 warning。

### 43–44. （已修，見附錄 A）

### 45. Workflow / 基礎設施仍有幾項未修

- 目前位置：`.github/workflows/pages.yml`、`.gitignore`、`requirements.txt`
- 未修項：
  - Google Drive secrets 仍放 job-level `env`，所有 steps 可見。
  - `curl` 仍缺 `--max-time` / `--retry`，job 也未設 `timeout-minutes`。
  - Python 仍 pin exact patch：`3.13.12`。
  - `.gitignore` 仍缺 `.env`、`.env.*`、`.venv/`、`*.sqlite3`。
  - `requirements.txt` 仍無 hash lock。
- 已修項：OAuth token 失敗時已不再 echo 完整 `TOKEN_JSON`。

### 46. TJStats 常數在賽季中不會更新，整季 wRC+ 可能用四月的 park factor

- 目前位置：`site_builder/league_constant/batting.py`、`site_builder/league_constant/policy.py`
- 證據：`batting.py` 宣告 `RefreshPolicy.FINAL_ONCE_PUBLISHED`，`should_use_cache()` 因此對「當年球季」也回 True。park factor 與 lg_wOBA/lg_R∕PA 只要在四月抓到過一次，整季都不會再更新，除非手動 `--update-constants`。
- 影響：賽季進行中的 wRC+ 分母偏舊。tjstats.ca 是否在季中重算這些數字尚未實測，所以嚴重程度未定。
- 建議修法：先實測（抽一年，對照已快取值與現場值）確認 tjstats.ca 季中是否真的會變；若會，把 `batting.py` 的政策改成 `ACCUMULATES_IN_SEASON`（`policy.py` 已經有這個選項，改一行即可）。
- 備註：2026-07-30 抽出 `league_constant/` 套件時發現——把兩條供應鏈的快取政策攤成具名 enum 之後才看得出這個差異。
- 2026-09-24 實測：tjstats.ca 現場的 2025、2026 league constants（13 個聯盟）與 MLB/AAA park factors 和 DB 快取完全一致；但 2026 的 lg_R/PA 與 MLB Stats API 球季至今實際值對不上（例：FSL tjstats 0.129 / 實際 0.1424、Eastern 0.142 / 0.1351，MLB 0.118 / 0.1183 則吻合），表示 tjstats 頁面本身季中沒有跟著更新，每天重抓也拿不到新數字，因此維持 `FINAL_ONCE_PUBLISHED`。仍未確認的是：tjstats 是否在球季結束後才發布最終值；若是，需要在換季後對上一季跑一次 `--update-constants`。

### 47. `stats/advanced/woba.py` 與 `api/tjstats.py` 目前沒有測試覆蓋

- 目前位置：`site_builder/stats/advanced/woba.py`、`site_builder/api/tjstats.py`
- 證據：舊的 `tests/test_wrc_plus.py` 曾涵蓋 `compute_woba` 與兩支 HTML 抓取函式，但它 import 的是兩次重構前的 `site_builder.wrc_plus` 單一模組，已長期無法 import；2026-07-30 改寫該檔時只復活了 `compute_wrc_plus` 與 `annotate_wrc_plus` 的部分。
- 影響：wOBA 公式與 tjstats.ca HTML 解析（欄位位置、`table.tjs-guts` 選擇器）若因對方改版而失效，不會有測試攔下來。
- 建議修法：新增 `tests/test_woba.py`（`compute_season_woba` / `compute_pitch_woba`）與 `tests/test_api_tjstats.py`（以 `unittest.mock.patch("site_builder.api.tjstats.get_text")` 餵固定 HTML）。注意：`tests/` 目錄本身從未被 git 追蹤（見 `.gitignore`），所以舊檔的測試資料與斷言無法從 git 歷史取回，只能重新撰寫。

### 48. MiLB xWPCT 混用所屬聯盟 FIP constant 與整層級 lgERA，跨聯盟基準不一致

- 目前位置：`site_builder/league_constant/pitching.py`、`site_builder/sync/statcast.py`
- 證據：MiLB FIP 優先使用投手所屬聯盟的 `fip_constant`，但 xWPCT 分母固定取 `league_constants[""].lg_era`（整個層級合計），而非同一筆所屬聯盟常數中的 `lg_era`。以資料庫快取的 2026 AAA 為例，International League lgERA 為 4.899、Pacific Coast League 為 5.471，level-wide lgERA 為 5.092；因此兩聯盟各自的平均投手代入目前公式後，IL 約為 `.518`、PCL 約為 `.467`，不會同時落在 `.500`。
- 影響：若 xWPCT 的語意是「相對所屬聯盟平均的中立預期勝率」，目前做法會系統性高估低得分聯盟、低估高得分聯盟，AAA、A、ROK 等同層級含多個聯盟時尤其明顯。若產品刻意要保留各聯盟得分環境的絕對差異，現況可視為設計選擇而非計算 bug，但欄位說明必須明確標示它不是 league-neutral 指標。
- 建議修法：先確定指標語意。若要 league-relative，xWPCT 應使用與 FIP constant 同一筆 `own_league.lg_era`，僅在聯盟無法解析時退回 level-wide，並新增「各聯盟平均 FIP 對應 xWPCT = .500」測試；若要 level-wide absolute comparison，則保留現行分母，但更新 tooltip／文件說明基準，並另行評估球場與聯盟 run environment 調整，避免把環境差異誤當投手能力。

### 49. Statcast 球種表的「全部」在 DB 裡存兩份（頂層欄位與 splits["all"]）

- 目前位置：`site_builder/stats/pitcher_statcast.py`、`site_builder/stats/batter_statcast.py`、`site_builder/render/pages.py::_COMBINED_EMPTY_DEFAULTS`、`src/templates/tabs/tab_advanced.j2`、`src/templates/mobile/sections/m_advanced.j2`
- 背景：2026-09-24 已修掉「打者球種表算兩次」——`compute_batter_statcast()` 原本頂層 `vs_pitch_types` / `vs_pitch_groups` / `pitch_group_usage_by_count` 各自重算一次，`compute_batter_pitch_hand_splits()` 的 `"all"` 又算一次；現在與投手端一致，只算一次分組，頂層欄位直接指向 `"all"` 那份物件（`tests/test_stats_tables.py::test_top_level_tables_reuse_all_split` 用 `assertIs` 鎖住）。**計算只剩一次，但儲存仍是兩份**。
- 證據：`season_stats.stat_json.statcast` 以 `util/json.py::dumps_json()`（`json.dumps`）序列化。JSON 沒有「引用」的概念，同一個 Python 物件被兩個 key 指到，就會被完整寫出兩次；讀回來後也變成兩個互不相干的 list/dict。重複的 key：
  - 投手：`pitch_arsenal`、`pitch_outcomes`、`pitch_usage_by_count` ＝ `pitcher_bat_side_splits["all"]` 的同名欄位
  - 打者：`vs_pitch_types`、`vs_pitch_groups`、`pitch_group_usage_by_count` ＝ `batter_pitch_hand_splits["all"]` 的同名欄位
- 規模（2026-09-24 本機 DB 實測）：644 列有 statcast，`stat_json` 合計約 5.81 MB，其中頂層這六個重複欄位約 0.53 MB（約 9.1%；投手 0.35 MB、打者 0.18 MB）。
- 影響：
  1. DB 與 build 時讀取的 JSON 多約一成體積（DB 放在 Google Drive、每天由 GitHub Action 下載上傳）。
  2. 對新資料來說頂層那份**畫面用不到**：樣板優先讀 `*_splits["all"]`，只有 splits 不存在時才退回頂層欄位（相容舊資料）。有人只改頂層欄位的讀取端時，畫面不會有任何變化，容易誤判。
  3. 以後若有人在 sync 之後單獨改寫其中一份（例如手動修補 DB、或新增只更新頂層的程式），兩份「全部」會不一致，而且沒有檢查會攔下來。
- 為什麼這次沒一起修：要真正只存一份，必須拿掉頂層六個 key，連帶牽動：
  1. 投手與打者兩個 `compute_*_statcast()` 的回傳結構（`docs/functions_list.md` §3.8、`docs/db_schema.md` 的 `statcast` 說明要同步改）。
  2. `tab_advanced.j2` / `m_advanced.j2` 的「splits 不存在時退回頂層」分支要刪，改成只讀 splits；`src/templates/partials/chart_data.j2` 也要一併確認。
  3. `render/pages.py::_COMBINED_EMPTY_DEFAULTS` 的對應項目要刪。
  4. 舊 DB 列：沒有 splits、只有頂層欄位的舊資料（splits 出現前寫入的列）會在樣板改完後變成空表。必須先確認全庫每一列 statcast 都已有 splits，或跑一次 `python build.py statcast` 全量重算後再改樣板。依 CLAUDE.md 規則 2，不在 `site_builder` 內寫回補代碼。
  5. 其他讀頂層 key 的地方（例如未來的 API/匯出）要先全庫搜尋確認沒有。
- 建議修法：
  1. 先用唯讀查詢確認 DB 內所有 statcast 列都有 `pitcher_bat_side_splits` / `batter_pitch_hand_splits`，沒有的先重跑 statcast。
  2. 樣板改成只讀 `splits["all"]`，刪除退回頂層的分支。
  3. 兩個 `compute_*_statcast()` 刪除頂層六個 key；`_COMBINED_EMPTY_DEFAULTS` 同步刪除。
  4. 更新 `docs/functions_list.md`、`docs/db_schema.md`、`docs/fields.md` 中提到頂層 key 的說明（例如 `docs/fields.md` 的 `sc.vs_pitch_types[]`）。
  5. 全站 build 前後逐檔比對 HTML（扣除時間戳）應無差異。
- 優先度：低。數字正確、只是體積與維護成本；DB 體積真的成為問題（例如 Drive 上傳時間）再處理即可。

### 50. 二刀流球員的 P/PA 被投球數據覆蓋（`pitches_per_pa` 打擊/投球共用同一個 key）

- 目前位置：`site_builder/sync/field_maps.py::apply_advanced_fields()`、`site_builder/stats/core/annotate.py::annotate_row()`
- 證據：`apply_advanced_fields()` 的打擊組與投球組都把 API `pitchesPerPlateAppearance` 寫進同一個 `stat_json.pitches_per_pa`；season_stats 同一列會同時帶兩組數據（`sync/players.py` 依序寫入兩個 group），後寫者覆蓋先寫者。`annotate_row()` 又把 `pitches_per_pa` 當作打者 `p_per_pa` 的來源（「prefer pitches_per_pa alias」）。
- 規模（2026-09-25 本機 DB）：59 列同時有打席（`pa > 0`）與面對打者數（`bf > 0`）且有 `pitches_per_pa`。例：806823 2025 ACL Reds 存 3.878（= 投手 pitches / BF），打者實際 `pitches_seen / PA` 為 4.33，進階打擊表顯示的是投手值。多數是早年 MiLB 投手偶爾上場打擊，但真正的二刀流球員會受影響。
- 影響：打者 P/PA 顯示成投手的每打席用球數；投手端讀 `pitches_per_pa` 則可能拿到打者值（視寫入順序）。
- 建議修法：投球組改寫 `p_pitches_per_pa`（比照 `p_k_pct` / `p_babip` 的 `p_` 前綴慣例），`annotate_row()` 投手分支與樣板改讀新 key，打者分支維持讀 `pitches_per_pa`；更新 `docs/fields.md`、`docs/db_schema.md`。舊資料需重跑 `python build.py sync` 才會拆開（依 CLAUDE.md 規則 2 不寫回補代碼）。

### 51. `sync/players.py` 寫入依 API 回傳順序「後蓋前」，結果取決於請求/回傳順序

- 目前位置：`site_builder/sync/players.py::_write_player_to_db()`
- 證據（2026-09-25 端到端比對）：把 `api/stats.py` 的「MLB 一次 + `leagueListId=milb_all` 一次」換成官方 `leagueListId=mlb_milb` 一次取回，名冊 103 位球員的 API splits 逐筆相同，但寫進全新 DB 後有差異，全部來自下列依順序覆蓋的寫法：
  - `game_logs`：同一場比賽同時有 hitting 與 pitching split（投手上場打擊），`ON CONFLICT(player_mlb_id, game_id)` 讓後寫的 split 蓋掉前者，`stats_json` 只留其中一組。比對中 199 場受影響；本機 DB 5,470 筆投手逐場紀錄中有 377 筆沒有投球數據（部分可能是真的只打擊的比賽）。
  - `season_stats.stat_json.gp`：hitting / pitching 兩組都寫 `gp`，後寫者勝（例：499614 2013 Frisco 打擊 125 場、投球 1 場，換順序後存成 1）。
  - `season_stats.stat_json.pitches_per_pa`：見 #50。
  - `players.team`：最近一季有兩列同層級時，`highest_level_row()` 平手取決於列的寫入順序（例：526269 2024 AAA Iowa Cubs / Piratas de Campeche）。
- 影響：目前順序固定所以結果穩定，但數值不一定是對的那組（投手逐場顯示成打擊數據、`gp` 顯示打擊或投球場數不一定）；且任何改變請求順序的重構（例如改用 `mlb_milb` 讓請求數減半）都會改變寫入結果，因此 `api/stats.py` 目前刻意維持兩次請求。
- 建議修法：`game_logs.stats_json` 依 group 分開存（或 hitting/pitching 各一個 key）；`gp` 明確規定取投球或打擊（或分成 `gp` / `p_gp`）；`highest_level_row()` 平手時加穩定的次要排序（如出賽數、球隊名）。修完後即可安全改用 `mlb_milb`（refresh 請求約 208 → 130、完整 sync 約 1,940 → 970）。舊資料需重跑 `python build.py sync`（依 CLAUDE.md 規則 2 不寫回補代碼）。

## 附錄 A — 已確認已修 / 不再列入未修 bug

**#10** Rate stat 以字串寫入：`win_pct`、`strike_pct`、`p_avg`、`p_obp`、`p_slg`、`p_ops`、`p_sb_pct`、`sb_pct`、`cs_pct`（`sync/field_maps.py`）與 `fielding_pct`（`sync/players.py`）改用 `safe_float` 寫入，API 佔位字 `.---`/`-.--`、缺值、`null` 都存 `None`；`compute_win_pct` / `compute_strike_pct` / `compute_sb_pct` / `annotate_opponent_slash` 改回傳 float，`stats/core/formatting.py::fmt_avg` 已刪除。實測原本描述的「阻擋重算」在當時 DB 中為 0 列（`""` 的列連計數也缺、`.---` 分母為零，重算同樣無值），實際影響是顯示：修正前網站上有 84 格 `.---`、10 格 `-.--`（逐場 ERA）直接顯示，且同表混用 `.250` 與 `0.250`（23,751 對 10,594 格）。樣板改以 `floatformat(3)`（逐場 ERA 為 `floatformat(2)`）統一顯示成 `0.250`、缺值 `-`；`floatformat` 也接受舊字串與 Jinja `Undefined`，所以舊 DB 列不重跑 sync 也能正確顯示，重跑 `python build.py sync` 後 DB 型別才全部變成 float。

**#13** 投手/打者 K%、BB% 共用 `k_pct` / `bb_pct`：`annotate_row()` 的投手分支改寫 `p_k_pct` / `p_bb_pct`（分母 BF），`tab_advanced.j2` 與 `m_advanced.j2` 的投手分支同步改讀新欄位；打者維持 `k_pct` / `bb_pct`（分母 PA）。修正前 DB 中有 52 列投手季度同時有打擊紀錄，進階表顯示的是打擊三振率（例：王建民 2006 MLB 顯示 75.0%，實際投手 K% 8.4%）。

**#15** Bio 本季合計缺 advanced derived fields：`compute_season_combined()` 已刪除，單一年度合計只由 `compute_year_groups()` 的 `summary` 產生（`aggregate_stats` → `np` → `annotate_row`，並帶 `teams_display`）；`render/pages.py` 的 `season_combined` 直接取當年那一組的 `summary`，bio 卡與成績表年度列是同一個物件。`teams_display` 字串改由 `career.py::_teams_display()` 單一產生（`compute_career` 共用）。改前改後全站 build 輸出（扣除時間戳）逐檔比對無差異。

**#30** 首頁/退役頁頭像仍缺原生 lazy：`index.j2`/`retired.j2` 的 `<img data-src=...>` 改為 `<img src=... loading="lazy">`；原本靠 `avatar-fallback.js` 手刻「先載可視內、Promise.all 等全部完成才載可視外」的批次邏輯已刪除（該邏輯會讓第二批延遲近 1 秒），改交給瀏覽器原生 lazy-loading 排程。球員頁（`player_detail.j2`/`m_hero.j2`）的 hero 大頭照相反：因為一定在首屏可見、常是 LCP 元素，`loading="lazy"` 反而會被瀏覽器降低請求優先權（實測 initialPriority Low vs Medium、請求晚發 ~130ms），故改為 `fetchpriority="high"` 維持 eager 載入。`width`/`height` 尺寸屬性防 CLS 仍未補，不在本次範圍內。

**2026-07-28 跨層級「合計」改為池化重算**（設計見 `docs/superpowers/specs/2026-07-28-statcast-level-tables-and-cross-level-totals-design.md`）。`stats/combine.py`、`stats/tables/weighted.py` 及各模組的 `combine_*()` 已整批刪除，「合計」不再是獨立演算法，而是把該年度所有層級的原始 pitches 池化後呼叫與單層級完全相同的 `compute_pitcher_statcast()` / `compute_batter_statcast()`：

- **#7** WAR / FIP / xWPCT 的 `0.0` 顯示成「—」：`fip` / `xwpct` / `war` 已改 `is not none`。`expected.xwoba` 刻意維持 truthy —— MiLB expected stats 全為 `0.0` 是 API 缺陷產生的假值，truthy 判斷正好把它們擋成「—」。
- **#8** 合計 Statcast 的加權分母錯誤：整套加權移除。`ev90` 是百分位、本來就無法由各層級百分位還原，池化重算後才首次正確（但 `compute_ev90()` 自身的 off-by-one 仍未修，見 #17）。
- **#9** 合計配球桶的 `all` bucket：`COMBINED_COUNT_USAGE_BUCKETS` 已移除、改用單一來源 `COUNT_USAGE_BUCKETS`；`_combine_usage_by_count()` 隨後整支刪除。
- **#14** 同年同層級多隊 Statcast entry 未去重：`_build_statcast_entries()` 以 `(year, resolve_tier(sport_level))` 去重。全站稽核 1,224 個 (表格, 年度) 區塊，重複層級列 0、重複 DOM id 頁面 0。
- **#43** 合計 pitch movement 的 `total_pitches` 語意混淆：`combine_pitch_movement()` 已刪除。
- **#44** 合計 Pitch Plinko 節點 pct 可能為 None：`combine_pitch_plinko()` 已刪除。
- **#37** xWPCT docstring 誤稱 Pythagenpat，且 `LEAGUE_RA9` 只有 2024 年資料：已改為純函式 `compute_xwpct(fip, lg_era)`，`lg_era` 與 FIP constant 共用同一次 `league_constant.pitching` 查詢（`compute_league_fip_constant()` 回傳 `LeagueFipConstant(fip_constant, lg_era)`、同一列快取），逐年逐層級即時算出，不再是手寫表格。同時修正比對基準：原本拿校準到 lgERA 尺度的 FIP，去除以含非自責分的 `LEAGUE_RA9`，造成系統性正偏差；現在除以同尺度的 `lg_era`，且無法解析時回傳 None 而非 fallback 到 4.5。docstring 也已改標為 fixed-exponent Pythagorean-style。
- **層級命名不匹配**（兩份文件皆未記錄，本次發現）：`game_logs.sport_level` 存現代縮寫（`A`、`A+`），`season_stats.sport_level` 對舊球季存舊制名稱（`A(Full)`、`A(Adv)`、`A(Short)`），`sync/statcast.py` 的字串相等比對永遠不成立，導致 **110 組 (球員, 年度, 層級)、57,955 顆球**的 statcast 被靜默丟棄。已改用 `resolve_tier()` 比對，重跑 statcast 後降至 0。
- **#32** 圖表 JSON 仍在桌機/手機模板各輸出一份：`pitch-usage-hand-data`、`pitch-movement-data`、`pitch-plinko-data` 三份 JSON 改成只在新的 `src/templates/partials/chart_data.j2` 渲染一次（`id="chart-data-{kind}-{year}-{index}"`），`tab_plot.j2`/`m_plot.j2` 的容器改用 `data-chart-key="{year}-{index}"` 對應查表；`pitcher-charts.js`/`pitch-plinko.js` 改用 `document.getElementById` 讀取。順帶把散落在 `pitcher-charts.js`/`pitch-plinko.js`/`m-charts.js`/`charts.js`/`util.js` 自己的 `pitchTypeInfo()` 共 5 份「讀取 JSON `<script>` by id」邏輯收斂成 `util.js` 的 `TW.readJsonScript()`。

- MiLB `yearByYear` 缺 try/except：已修到 `site_builder/api/stats.py`。
- FIP 使用棒球小數 IP：已修到 `site_builder/stats/advanced/fip.py`，使用 `ip_to_outs()`。
- Barrel% 單層級分母：已改用 `len(agg["bbe_ev"])`。
- 投手 BABIP 公式：已改用 `p_ab` 對稱公式。
- CSS `@import` 瀑布：build 時已在 `_bundle_css()` 打包。
- Chart.js 未 pin / 無 SRI：目前已 pin `chart.js@4.5.1` 且有 integrity；但第三方 CDN 依賴仍未完全消除，另列第 33 條。
- teal 半透明色硬編碼 `rgba(20,184,166,...)`：目前已改為 `rgb(var(--teal-rgb) / ...)`。
- 專案完全沒有 tests：目前已有 `tests/`。
- `tojson_safe` 的 `</script>` 提前閉合風險：目前 `_json_html_safe()` 會把 `</` 轉為 `<\/`；`BUG_REVIEW.md` 也已把此項列為「確認非 bug」。若要更嚴格，可另改 `htmlsafe_json_dumps()`，但不列入本次未修 bug。
- `parse_roster_from_file()` 位於 API client：已移至 `site_builder/roster.py`。
- Put Away% 三份重複邏輯：已抽成 `site_builder/stats/discipline/put_away.py`。
- `_pa_outcome_totals` / wOBA/AVG PA 結果迴圈重複：已抽成 `site_builder/stats/core/pa_outcomes.py`。
- `DEFAULT_SEASON_YEAR` 固定值：已改為 `site_builder/constants.py` 的自動球季推算，仍可用環境變數覆寫。
- UTC+8 timezone 重複硬編碼：已抽成 `site_builder/util/dates.py::TW_TZ`；但 `get_next_game()` 查詢起點仍用本機 date，另列於第 20 條。
- 桌機/手機 arsenal filter 互踩：已重構為 `src/static/js/filters.js` + 各平台 config。
- `sortCards()` inline JS：已抽成 `src/static/js/index-sort.js`，但模板仍有 inline `onclick` 屬性。
- 球員頁大型 inline JS：目前主要已拆到 `src/static/js/*.js`；圖表 JSON 重複/內嵌已修，見上方 #32。

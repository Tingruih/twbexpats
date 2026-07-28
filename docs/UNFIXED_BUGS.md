# Taiwan MLB Tracker — 未修復 Bug 整合清單

檢查日期：2026-07-10  
來源文件：`docs/BUG_REVIEW.md`、`docs/CODE_REVIEW_FIX_PLAN.md`、`docs/CODE_REVIEW_REPORT.md`、`docs/TODO.md`

> 說明：`site_builder` 已重構成子套件，以下位置皆以目前程式碼重新定位，不沿用舊文件行號。此文件只列「目前仍可在程式碼中確認未修」或「仍需修正/驗證的 bug」。純架構重構、一般 DRY 建議、已修復項目放在附錄。

> 跨層級「合計」相關的 #8 與 #14 已於 2026-07-28 用全庫資料實測驗證，範圍比原記錄大得多（球種表的加權錯誤先前完全未被記錄）。完整驗證數字與受影響表格清單見 **`docs/cross-level-aggregation-bugs.md`**。

## P0 / P1 — 優先修

### 1. Pitch log 仍以 `innerHTML` 注入未跳脫資料，存在 XSS 風險

- 目前位置：`src/static/js/pitch-log.js`
- 證據：`_buildPitchTable()` 直接把 `p.pitch_type`、`p.pitch_name`、`p.result`、`p.pa_event` 串進 HTML；`_renderPitchLog()` 再用 `container.innerHTML` 注入。
- 影響：若 API 或快取資料含惡意 HTML/JS，球員頁逐球展開區可能被注入。
- 建議修法：使用 `window.TW.escapeHtml()` 轉義可見文字；用 whitelist/sanitize 處理 class token（如 `pitch_type`）。

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

### 7. WAR / FIP / xWPCT 的 `0.0` 仍會顯示成「—」

- 目前位置：`src/templates/tabs/tab_advanced.j2`、`src/templates/mobile/sections/m_advanced.j2`
- 證據：模板仍用 `{% if ss_row and ss_row.fip %}`、`xwpct`、`war` 的 truthy 判斷。
- 影響：合法數值 `0.0` 被當成缺值。
- 建議修法：改成 `is not none`。

### 8. 合計 Statcast 仍用 BBE 權重合併 `ev90`、`hr_fb_pct`、`avg_la`

- 目前位置：`site_builder/stats/combine.py`
- 證據：`bbe_fields` 包含 `avg_la`、`hr_fb_pct`、`ev90`，並一律 `_wpct(f, "bbe")`。
- 影響：`ev90` 是百分位，不能由各層級百分位加權平均還原；`hr_fb_pct` 正確分母應是 FB；`avg_la` 正確權重應是有 LA 的 BBE。
- 建議修法：`ev90` 合計列設 `None`；`hr_fb_pct` 保存/合併 FB 分母；`avg_la` 保存/合併 LA 樣本數。
- **2026-07-28 更新**：實測後範圍比此條目大。除了列出的三個欄位，`barrel_pct` / `hard_hit_pct` / `avg_ev`（分母應是 `bbe_ev` 而非 `bbe`）、`swsp_pct`、`avg_extension`、`zone_pct` 也錯；`weighted.py` 的整組球種表（`pitch_arsenal` / `pitch_outcomes` / `vs_pitch_types` / `vs_pitch_groups`）另有一組**更嚴重且先前完全未記錄**的加權錯誤，最大誤差 AVG 差 .106、Whiff% 差 30.6pp、轉速差 96 rpm。詳見 `docs/cross-level-aggregation-bugs.md` §2。

### 9. 合計配球桶仍保留不存在的 `all` bucket

- 目前位置：`site_builder/constants.py`、`site_builder/stats/tables/usage_by_count.py`
- 證據：`COUNT_USAGE_BUCKETS` 沒有 `all`，但 `COMBINED_COUNT_USAGE_BUCKETS` 仍有 `("all", "All Counts", ...)`；combine 裡也仍有 `row.get("key") == "all"` 的回填分支。
- 影響：合計列的 `all` bucket 不是由 per-level 產生端輸出，容易維持空桶/死碼；也讓中英文標籤分岔。若未來產生端補出 `all`，目前回填邏輯仍可能和 top-level `pitch_types` 雙重累加。
- 建議修法：移除 combine 端 `all` bucket，或讓產生端也明確產生 `all`，兩端採單一常數來源並重寫 totals fallback。

### 10. Rate stat 缺值仍以空字串寫入，會阻擋衍生重算

- 目前位置：`site_builder/sync/field_maps.py`、`site_builder/stats/core/annotate.py`、`site_builder/stats/pitching/opponent_slash.py`
- 證據：`win_pct`、`strike_pct`、`p_avg`、`p_obp`、`p_slg`、`p_ops`、`p_sb_pct`、`sb_pct`、`cs_pct` 仍使用 `str(stat.get(..., ""))`；重算端多數仍以 `is None` 判斷是否補算。
- 影響：API 缺值時存成 `""`，後續即使可由計數欄位重算，也不會補。
- 建議修法：寫入端改 `_str_or_none()`；或重算端明確把 `None`/`""` 都視為缺值。

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

### 13. 投手/打者 K%、BB% 仍共用 `k_pct` / `bb_pct`

- 目前位置：`site_builder/stats/core/annotate.py`、`src/templates/tabs/tab_advanced.j2`、`src/templates/mobile/sections/m_advanced.j2`
- 證據：打者與投手分支都填同一組 key；模板投手分支也讀 `k_pct` / `bb_pct`。
- 影響：投打雙修球員若打者公式先填值，投手 K%/BB% 會被 None guard 擋住而顯示打擊 K%/BB%。
- 建議修法：投手改用 `p_k_pct` / `p_bb_pct`，模板同步讀新欄位。

### 14. 同年同層級多隊 Statcast entry 仍未去重

- 目前位置：`site_builder/render/pages.py`
- 證據：`statcast_by_year` 直接 append 每個 `season_stats` row 的 `statcast`，沒有 `(year, sport_level)` seen set。
- 影響：若同年同層級換隊，而 sync 寫入同一層級聚合到多個 team row，進階表會重複列，合計列也會雙倍計權。
- 建議修法：建立 `_build_statcast_entries()`，以 `(year, sport_level)` 去重。
- **2026-07-28 更新**：已確認實際發生，全庫 19 個 (球員, 年度, 層級) 組合、分布在 18 個 (球員, 年度)。已建置站台可直接驗證：張育成 2022 的合計球數是實際的 3.6 倍，`id="arsenal-2022-MLB"` 在 HTML 中出現 4 次，Statcast 概覽／Plate Discipline／擊球型態 三張表各印出 4 列一模一樣的 MLB。當該年度還有其他層級時，被重複的層級拿到 N 倍權重，所有比率也跟著偏移。完整清單見 `docs/cross-level-aggregation-bugs.md` §3。

### 15. `compute_season_combined()` 仍未補算 advanced derived fields

- 目前位置：`site_builder/stats/core/career.py`
- 證據：`compute_season_combined()` 只呼叫 `aggregate_stats()`，設定 `teams_display` / `year` 後直接 return；同檔 `compute_year_groups()` 的 summary row 則有呼叫 `annotate_row(summary)`。
- 影響：Bio 的本季合計列可能缺 `iso`、`babip`、`k_pct`、`bb_pct`、`ab_per_hr`、`p_per_pa` 等衍生欄位；與年份 summary 路徑不一致。
- 建議修法：return 前補 `annotate_row(combined)`，並設定需要的 template alias（如 `np`）。

### 16. Batted-ball trajectory / spray rate 分母仍用所有 in-play

- 目前位置：`site_builder/stats/batted_ball/__init__.py`
- 證據：`gb_pct`、`ld_pct`、`fb_pct`、`pu_pct`、`air_pct` 用 `n_ip`；`pull_pct`、`straight_pct`、`oppo_pct`、`pull_air_pct` 也用 `n_ip`。
- 影響：未知 trajectory 或無法判斷方向的擊球會稀釋比例。MiLB 缺測多時偏差更明顯。
- 建議修法：trajectory 類用 classified denominator；spray 類用 `spray_total`。
- 備註：`barrel_pct` 單層級分母已改成 `len(bbe_ev)`，該部分已修。

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

### 30. 首頁/退役頁頭像仍缺原生 lazy 與尺寸

- 目前位置：`src/templates/index.j2`、`src/templates/retired.j2`
- 證據：`<img data-src=... class="avatar-img">` 沒有 `width`、`height`、`loading="lazy"`、`decoding="async"`。
- 影響：可能造成 CLS，且 lazy loading 完全依賴自製 JS。
- 建議修法：補尺寸與原生 lazy/decoding；保留 fallback JS 也可以。

### 31. Mobile pitch-log 預載仍用 inline style 字串 selector

- 目前位置：`src/static/js/mobile/m-pitch-log.js`
- 證據：`querySelector('.m-gamelog-year[style="display: flex;"], ...')`。
- 影響：顯示邏輯若改 class 或 inline style 多一個屬性，預載會失效。
- 建議修法：用 `.is-active` class，或用 JS 判斷 `el.style.display !== "none"`。

### 32. 圖表 JSON 仍在桌機/手機模板各輸出一份

- 目前位置：`src/templates/tabs/tab_plot.j2`、`src/templates/mobile/sections/m_plot.j2`
- 證據：兩個模板都輸出 `pitch-usage-hand-data`、`pitch-movement-data`、`pitch-plinko-data` 的 `<script type="application/json">`。
- 影響：投手頁 Statcast/Plinko/Movement JSON 在同一 HTML 重複，增加傳輸與解析成本。
- 建議修法：每個 player/year/level 的圖表資料只輸出一份，桌機和手機共用；或 build 時外部化 JSON 並 lazy fetch。

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

### 37. xWPCT docstring 仍誤稱 Pythagenpat，且 RA9 仍只有少數層級/年份

- 目前位置：`site_builder/stats/advanced/xwpct.py`、`site_builder/constants.py`
- 證據：docstring 寫 `Pythagenpat, exponent 1.83`；`LEAGUE_RA9` 只列 2024 的 MLB/AAA/AA/A+/A。
- 影響：docstring 誤導；ROK/A-/WIN 或未列年份會 fallback 到 4.5。
- 建議修法：docstring 改成 fixed-exponent Pythagorean；補齊 annual RA9 或明確標註 fallback。

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

### 43. 合計 pitch movement 在缺 `total_pitches` 時仍有語意混淆

- 目前位置：`site_builder/graph/movement.py`
- 證據：`combine_pitch_movement()` 若各 level 都沒有 `total_pitches`，用抽樣前 `len(points)` 當 `total`；之後可能再 downsample 到 `COMBINE_MAX_POINTS`。
- 影響：`total_pitches`、`shown_pitches` 與 `pitch_types[*].pct` 的分母語意依資料是否有 total 而變，舊資料/缺欄位資料較難解讀。
- 建議修法：保留明確欄位，例如 `total_pitches_source` / `sampled_from_points`，或在缺 total 時只顯示 shown/sample 而不輸出 pct。

### 44. 合計 Pitch Plinko 節點 pct 仍可能因節點 pitches 缺失而變成 None

- 目前位置：`site_builder/graph/plinko.py`
- 證據：`combine_pitch_plinko()` 的節點球種 pct 使用 `ratio(type_count, node_bucket["pitches"])`；如果舊資料存在 `type_counts` 但 node `pitches=0`，pct 會是 `None`。
- 影響：舊快取或不完整資料會造成節點分子/分母不一致，顯示層可能出現空百分比。
- 建議修法：combine 時若 node pitches 缺失但 type_counts 有值，使用 `sum(type_counts)` 補分母，或略過該節點。

### 45. Workflow / 基礎設施仍有幾項未修

- 目前位置：`.github/workflows/pages.yml`、`.gitignore`、`requirements.txt`
- 未修項：
  - Google Drive secrets 仍放 job-level `env`，所有 steps 可見。
  - `curl` 仍缺 `--max-time` / `--retry`，job 也未設 `timeout-minutes`。
  - Python 仍 pin exact patch：`3.13.12`。
  - `.gitignore` 仍缺 `.env`、`.env.*`、`.venv/`、`*.sqlite3`。
  - `requirements.txt` 仍無 hash lock。
- 已修項：OAuth token 失敗時已不再 echo 完整 `TOKEN_JSON`。

## 附錄 A — 已確認已修 / 不再列入未修 bug

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
- 球員頁大型 inline JS：目前主要已拆到 `src/static/js/*.js`；圖表 JSON 重複/內嵌另列於第 32 條。

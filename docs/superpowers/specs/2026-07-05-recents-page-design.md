# /recents 近期出賽分析頁 — 設計規劃文檔

日期：2026-07-05
狀態：已實作（實作規格見 docs/superpowers/plans/2026-07-09-recents-charts-video.md，§7.3 的 canvas 方案被 matplotlib 靜態圖取代）

---

## 1. 目標

新增 `/recents/` 端點並加入選單列，顯示**過去 7 天內所有有出賽的球員**，每人一張卡片（頭像＋名字＋每場比賽簡單數據），點開後展開該球員的**詳細分析報告**。

報告的核心設計理念：**不只呈現「這場打得如何」，而是回答「這位球員最近做了哪些改變」**。所有進階指標都以「本週數值 vs 球季基準」的差異（delta）呈現，讓異動一眼可見。

以 2026-06-28 ~ 07-04 這週實測，共 14 位球員、28 場比賽，資料量完全可以整頁預先渲染。

---

## 2. 資料現況盤點

### 2.1 pitches_json 欄位使用情形（全 57 欄掃描結果）

**已被下游模組使用**（arsenal、discipline、batted_ball、graph 等）：
`start_speed`、`ivb`、`hb`、`spin_rate`、`extension`、`x0`/`z0`（放球點）、`zone`、`ev`、`la`、`hit_coord_x/y`、`hit_location`、`trajectory`、`pre_balls`/`pre_strikes`、`is_pa_final`、`pa_event`、`result_code`、`balls`/`strikes`、`bat_side`/`pitch_hand`、`pitch_type`/`pitch_name`、`is_strike`/`is_in_play`

**已抓取但完全未使用（只出現在 sync/extract.py）— 本次要活用的欄位**：

| 欄位 | 內容 | 可做什麼 |
|------|------|----------|
| `end_speed` | 到本壘板時球速 | 球速衰減量（velocity loss）；與 start_speed 差值反映球的「載重」 |
| `plate_time` | 出手到進壘時間 | 打者反應時間；搭配 effective velocity 概念 |
| `vx0/vy0/vz0`, `ax/ay/az` | 出手初速與加速度向量 | **可推算 VAA（垂直進壘角）與 HAA** — 現代投球分析的關鍵指標，目前站上完全沒有 |
| `spin_dir` | 旋轉軸方向（度） | 轉軸變化偵測（球種改造的訊號）；可換算成時鐘方位呈現 |
| `break_angle`/`break_length`/`break_y` | 傳統 break 量測 | 輔助參考（優先用 ivb/hb，此組備援） |
| `type_confidence` | 球種分類信心值 | 過濾低信心球（<0.5）避免污染 per-pitch-type 統計 |
| `strike_zone_top`/`strike_zone_bottom` | 該打者好球帶上下緣 | 正規化垂直進壘點 → 攻擊區域（attack zone）分析、edge% |
| `hit_distance` | 擊球飛行距離 | 打者報告的擊球明細；全壘打距離 |
| `hardness` | soft/medium/hard（記錄員判定） | **無 Trackman 層級（AA/A+）的擊球品質替代指標** |
| `runners` | PA 結束時跑者移動明細 | 失分歸責、得點圈處理、盜壘/牽制事件 |
| `pa_event_desc` | PA 結果文字描述 | 報告中的打席明細列 |

### 2.2 各層級追蹤資料覆蓋率（以本週實測）

| 層級 | pitch tracking（球速/位移/轉速/進壘點） | EV/LA | hit_coord / trajectory / hardness |
|------|------|------|------|
| MLB | 100% | 打進場內皆有 | 有 |
| AAA | 100% | 打進場內皆有 | 有 |
| A | 約 32%（部分球場有 Trackman） | 少量 | 有 |
| ROK | 約 13% | 極少 | 有 |
| AA / A+ | **0%** | 無 | **有**（記錄員座標與 soft/med/hard） |

→ 設計必須**分級降階（tiered degradation）**：報告依「該場資料等級」自動決定顯示哪些區塊，而不是留一堆空白。

- **Tier 1（完整追蹤）**：全部區塊。
- **Tier 2（部分追蹤）**：有追蹤的球照 Tier 1 計算並標註樣本數；其餘退到 Tier 3。
- **Tier 3（僅結果資料）**：結果型指標 — K%、BB%、strike%、whiff%（result_code 可判定揮空）、GB/LD/FB 分佈（trajectory）、落點圖（hit_coord）、hardness 品質分佈。

---

## 3. 投手詳細報告設計

「觀察改變」的五大軸線，依重要性排序：

### 3.1 球速（最敏感的改變訊號）
- 每球種：本週均速／最快球速 vs **球季均速**，差異以彩色 delta chip 呈現（▲+1.2 mph / ▼-0.8 mph）。
- **逐場球速 sparkline**：該週每場四縫線均速連線，背景畫季平均虛線 — 疲勞或機制改變一眼看出。
- 場內衰減：首局 vs 末局均速差（先發投手的續航力訊號）。
- 新增使用 `end_speed`：start−end 差值。

### 3.2 球種使用比例（Pitch Mix）
- 本週 usage% vs 季 usage%，並排橫條圖。
- **新球種偵測**：本週出現但季使用率 <2% 的球種加「NEW」徽章；反之停用的球種標「棄用」。這是「做出改變」最直接的證據。
- 分打者左右的 usage 變化（既有 `bat_side` 欄位）。

### 3.3 球質（Movement / Spin / 進壘角）
- IVB / HB per pitch type：本週 vs 季平均，重用 `graph/movement.py` 畫**疊圖**（季平均以灰色 ghost 橢圓、本週以實色點）。
- 轉速與 **轉軸方向（spin_dir，未使用欄位）**：轉軸偏移 >15° 標示「握法/轉軸調整？」。
- **VAA（新衍生指標）**：由 `vy0/ay/vz0/az` 推算至 y=17/12 ft 的垂直進壘角。四縫線 VAA 是壓制力關鍵，目前站上沒有。
- Extension 與放球點（`x0/z0`）：**放球點漂移圖** — 本週 vs 季平均散點。放球點位移是機制改變或受傷前兆的經典訊號。

### 3.4 控球與壓制
- Zone%、CSW%、Whiff%、Chase%、首球好球率（`pre_balls==0 and pre_strikes==0`）：本週 vs 季，delta chip。
- **好球帶九宮格熱區**（`zone` 1–14 已有）：本週進壘分佈 vs 季平均。
- Edge%（新）：用 `px/pz` + `strike_zone_top/bottom` 正規化後計算邊角率。

### 3.5 成果與被打品質
- 每場一列：IP / ER / K / BB / 用球數（`stats_json.summary` 現成）。
- 被打 EV、被 hard-hit 率（Tier 1）；Tier 3 用 `hardness` 分佈替代。
- `runners`（未使用欄位）：失分事件明細 — 哪個打席、什麼事件掉分。

---

## 4. 打者詳細報告設計

### 4.1 擊球品質（Tier 1）
- 每顆擊球明細：EV / LA / 距離（`hit_distance`，未使用）/ 結果。
- 本週 avg EV、max EV、hard-hit%、sweet-spot% vs 季平均 delta chip。
- **EV/LA 散點圖**：本週擊球點疊在季平均分佈上，barrel 區塊底色標示。

### 4.2 擊球品質替代版（Tier 3，AA/A+ 也能看）
- `hardness` 分佈（hard% 趨勢）＋ `trajectory` GB/LD/FB% 本週 vs 季。
- **落點圖（spray chart）**：`hit_coord_x/y` 各層級都有，重用 `stats/batted_ball/spray.py`。拉打/推打傾向變化也是打者調整的訊號。

### 4.3 選球與揮棒決策（各層級都可算，改變最常發生在這）
- Chase%（O-Swing）、Whiff%、Z-Contact%、SwStr%：本週 vs 季 delta。
- **分球種對戰**：對速球 vs 對變化球（whiff%、打擊結果），偵測「開始打得到變化球了」這類改變。
- 兩好球後的縮短揮棒表現（2-strike approach）：`pre_strikes==2` 的打席結果。
- 好球帶九宮格：挨打熱區 vs 咬中熱區。

### 4.4 打席明細與成果
- 每場一列摘要（`stats_json.summary` 現成，如 `0-4 | BB, K, R`）。
- 逐打席時間軸：局數、對方投手球種序列、結果（`pa_event_desc`）— 資料已在 pitches_json 內。
- 週彙總 slash line 與 K% / BB%。

---

## 5. 可新增的衍生指標（資料已有、尚未計算)

| 指標 | 來源欄位 | 價值 |
|------|----------|------|
| VAA / HAA 進壘角 | `vy0, ay, vz0, az, vx0, ax` | 四縫線壓制力、伸卡效率的現代指標 |
| Effective Velocity（感知球速） | `start_speed, extension` | 出手距離加成後的實際感受球速 |
| 球速衰減 | `start_speed − end_speed` | 球的乘載效率 |
| 轉軸時鐘方位 | `spin_dir` | 球種改造偵測（如 sweeper 化） |
| Edge% / Meatball% | `px, pz, strike_zone_top/bottom` | 精細控球品質 |
| Attack Zone（Heart/Shadow/Chase/Waste） | 同上 | Savant 式四區進壘分析 |
| 首球好球率 F-Strike% | `pre_balls, pre_strikes, is_strike` | 搶好球數傾向 |
| 反應時間 | `plate_time` | 輔助呈現 |
| 失分歸責明細 | `runners` | 報告敘事用 |

## 6. 目前完全沒有、需外部來源的數據（列入文檔供未來評估）

- **xwOBA / xBA 官方模型值**：API 不提供 MiLB；MLB 部分可從 Baseball Savant 取得。站內已有 xwPct 近似，可標註為自建估計。
- **Bat speed / swing length**（打者揮棒追蹤）：僅 Savant 有，且限 MLB。
- **Sprint speed、外野臂力**等守備／跑壘 Statcast：需 Savant leaderboard 抓取。
- **Spin efficiency（active spin）**：需 3D 旋轉資料，API 只有 rate 與 direction。
- **對手投手情報**（對戰投手的球探等級資訊）：可用既有 API 的 opponent probable pitcher 延伸。
- **比賽影片**：MLB Film Room 可以 playId 組 URL，MiLB 覆蓋不穩定，列為未來加值項。

---

## 7. UI / 呈現設計

### 7.1 清單頁 `/recents/`
- 標題列：日期範圍「近 7 天出賽動態（06/28 – 07/04）」。
- 分兩區：**投手** / **打者**（同現有站內慣例），各區依最近出賽日排序。
- 每人一張卡片：
  - 頭像（沿用 `headshot_cdn_urls` + `avatar-fallback.js` 機制）、中英文名、球隊＋層級徽章。
  - 卡片內每場一列：`07/03 vs BUF — 5.0 IP, 0 ER, 8 K, 0 BB`（日期、主客、對手、`stats_json.summary`）。
  - 右上角放 1–2 個「本週亮點 delta chip」（如 `FB ▲+1.4 mph`、`Chase ▼-6%`），讓清單頁就能掃出誰有異動。
- 點卡片 → 展開詳細報告（`<details>` 式展開，行動版全寬）。

### 7.2 詳細報告版面（展開後）
1. **週彙總列**：合計數據 + delta chip 群。
2. **重點摘要（規則式自動生成 2–4 條）**：如「滑球使用率 18%→31%」「四縫線均速 +1.3 mph」「chase% 由 34% 降至 25%」。規則式（threshold-based）即可，不需 LLM。
3. 視覺化區塊（依 Tier 顯示）：
   - 投手：球速 sparkline、usage 對比橫條、movement 疊圖、放球點漂移、九宮格熱區。
   - 打者：EV/LA 散點（或 hardness/trajectory 條形）、spray chart、選球 delta 表、逐打席時間軸。
4. 逐場明細表（可再展開既有 pitch log lazy-load JSON — 機制已存在，直接重用）。
5. 連結至球員完整頁面。

### 7.3 視覺化技術
全部沿用站內既有模式：後端 Python 算好輕量 JSON → 內嵌頁面 → 前端小型 canvas/SVG 腳本渲染（同 `pitcher-charts.js`、`pitch-plinko.js` 模式），不引入新圖表庫。

---

## 8. 技術架構

### 8.1 呈現方式選項

| 方案 | 說明 | 評估 |
|------|------|------|
| **A. 單頁全預渲染（推薦）** | 所有球員報告直接渲染進 `/recents/index.html`，以 `<details>` 摺疊，圖表 JSON 內嵌、canvas 延遲初始化 | 一週約 14 人，估整頁 <500KB，靜態站最簡單、SEO 佳、零額外請求 |
| B. 報告片段 lazy-load | 卡片列表輕量，展開時 fetch 每人報告 JSON（同 pitchlogs 機制） | 頁面更小，但多一套前端渲染邏輯，維護成本高 |
| C. 連回 player page 錨點 | 卡片點擊跳轉球員頁 | 最省工，但做不出「週 vs 季」客製比較，不符需求 |

推薦 **A**；若未來球員數大增再演進為 B。

### 8.2 新增模組

```
site_builder/
  stats/recent/
    __init__.py
    window.py        # 取近 7 天 game_logs、分 Tier 判定
    pitcher_report.py # 週 vs 季 delta 計算（重用 arsenal/discipline 函式）
    batter_report.py
    derived.py       # VAA、EffVelo、edge%、轉軸方位等新衍生指標
    highlights.py    # 規則式重點摘要與 delta chip 選取
  render/
    recents.py       # 組 context、寫 recents/index.html

src/templates/
  recents.j2
  partials/recent_pitcher_report.j2
  partials/recent_batter_report.j2

src/static/js/recents.js      # 展開互動 + 圖表初始化
src/static/css/recents.css
```

### 8.3 資料流
1. `build` 時從 `game_logs` 撈 `date >= build_date - 7d` 的列（roster 內球員）。
2. 每位球員：週內 pitches 合併 → 用**既有** `compute_pitch_arsenal` / discipline / batted_ball 函式算週值；季基準直接取 `season_stats.stat_json.statcast`（已算好），**不必重算全季**。
3. delta = 週值 − 季值；再算衍生指標（`derived.py` 只吃週內 pitches）。
4. 渲染進 `recents/index.html`；`base.j2` 選單加入第三項；sitemap 加 URL。

### 8.4 其他整合點
- `base.j2` menu-dropdown 加：`近期出賽`（desc：`近 7 天出賽球員分析報告`），`nav_active == 'recents'`。
- 首頁球員卡可加小徽章「本週 N 場」連到 /recents（可選，Phase 2）。
- 無出賽球員的空狀態頁（休季期）：顯示「近 7 天無出賽紀錄」。

---

## 9. 分階段實作建議

- **Phase 1（骨架）**：window.py + recents.j2 清單頁（卡片＋每場 summary）＋選單項＋空狀態。
- **Phase 2（報告核心)**：週 vs 季 delta 引擎、投手/打者報告模板、delta chips、規則式重點摘要、Tier 降階。
- **Phase 3（視覺化）**：球速 sparkline、movement 疊圖、放球點漂移、spray chart、EV/LA 散點、九宮格。
- **Phase 4（新衍生指標）**：VAA、EffVelo、edge%、attack zone、轉軸方位 — 同步回饋到球員頁 arsenal 表。

## 10. 開放問題（待決定）

1. 「一週」定義：滾動 7 天（建置日往回推）或固定週一–週日？**建議滾動 7 天**，配合每日 refresh。
2. 週 vs 季比較的「季基準」是否排除本週（season-to-date minus this week）？樣本大時差異小，**建議先不排除**，實作簡單。
3. delta chip 的顯著性門檻（如球速 ±0.5 mph、usage ±5%、chase ±3%）需在實作時用真實資料調校。
4. 首頁是否同步加「本週出賽」徽章（Phase 2 可選項）。

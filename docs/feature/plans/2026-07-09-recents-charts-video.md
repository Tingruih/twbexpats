# /recents 近期出賽分析頁 ＋ matplotlib 出賽圖表 ＋ 逐球影片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `/recents/` 近 7 天出賽分析頁（投手＋打者週報告、週 vs 季 delta、matplotlib 出賽圖表含本壘板視角），並在球員頁逐球表格加入逐球影片（MLB 限定），全部帶完整分級 fallback。

**Architecture:** 三個子系統依序落地，每個 Phase 結束都是可部署的網站：(1) `site_builder/charts/` 新增 matplotlib 深色主題圖表引擎（build 時輸出 PNG 到 `dist/static/charts/`）；(2) `site_builder/stats/recent/` 計算近 7 天視窗、資料分級（Tier）、衍生指標（VAA/EffVelo/attack zone…）與週 vs 季 delta，由 `render/recents.py` 組頁；(3) 逐球影片：sync 階段抓 `game/{pk}/content` 精華 mp4 存新表 `play_videos`，render 時寫進 pitch log JSON，前端 `pitch-log.js` 加播放鈕（精華球站內 `<video>`、一般 MLB 球 Savant iframe fallback）。

**Tech Stack:** Python 3.13、matplotlib（Agg，新依賴）、Jinja2、SQLite、原生 JS（無新前端庫）、pytest。

**參考文件:** `docs/superpowers/specs/2026-07-05-recents-page-design.md`（recents 規格）、`docs/pitch_video_embedding.md`（影片可行性調查）。本 plan 的 §0 呈現規格已把兩份文件的開放問題全部定案，執行時以本 plan 為準。

## Global Constraints

- Python 3.13；新依賴僅 `matplotlib`（連同其傳遞依賴由 pip 解析）。禁止引入其他新套件與任何前端圖表庫。
- `matplotlib.use("Agg")` 必須在任何 `pyplot` import 之前執行（唯一位置：`site_builder/charts/style.py` 模組頂部）。
- **圖表內文字一律英文與數字**（CI runner 無 CJK 字型，中文會變豆腐字）；中文說明一律放在 HTML 模板的圖說（figcaption）。
- 圖表輸出 PNG，`dpi=180`，表面色 `#18181b`（網站 `--card-surface`）。網站為深色單一主題，不做亮色版。
- 色彩使用 §0.5 的已驗證色票，不得自行挑色。散點圖一律以「標記形狀」作 CVD 第二編碼，並附圖例。
- 層級規則（CLAUDE.md）：`util/` → `levels.py`/`roster.py`/`constants.py` → `api/` → `stats/` → `db/`/`graph/`/**`charts/`（新，與 graph 同層）** → `sync/`/`render/`。`charts/` 只准 import `stats/`、`constants`、`util/`；`stats/recent/` 不做任何檔案 IO（圖檔由 `render/recents.py` 生成）。
- 命名慣例：純計算函式 `compute_*`；圖表寫檔函式 `render_*`，回傳 `bool`（False = 資料不足未產圖，caller 據此觸發 fallback）。
- 每個 Task 結束跑 `python -m pytest tests/` 全綠後 commit；commit 訊息用 `feat:`/`test:`/`docs:` 前綴。
- 資料庫變更只准走 `db/schema.py::init_db` 的冪等 `CREATE TABLE IF NOT EXISTS` / try-ALTER 模式。
- 所有新頁面文案為繁體中文；數據縮寫（EV、LA、CSW%…）保留英文。

---

## 0. 呈現規格（資料呈現方式、數據定義、fallback）

此節是規格總表，Task 依此實作。執行者遇到細節疑義以此節為準。

### 0.1 已定案的開放問題（spec §10）

| 問題 | 決定 |
|---|---|
| 「一週」定義 | 滾動 7 天：`date >= build_date(UTC+8) - 7d` |
| 季基準是否排除本週 | 不排除，直接用 `season_stats.stat_json.statcast`（已算好） |
| delta 顯著門檻 | 見 §0.6 表 |
| 首頁徽章 | 不做（YAGNI，列未來項） |
| spec §7.3「不引入新圖表庫、用 canvas」 | **被使用者需求覆蓋**：報告圖表全部改用 matplotlib 靜態 PNG；既有球員頁 canvas 圖表不動 |

### 0.2 資料分級（Tier）

以「單場」為單位判定（`stats/recent/window.py::game_tier`）：

```
tracked = px/pz 與 start_speed 皆非 None 的球數
ratio = tracked / 總球數
ratio >= 0.8  → Tier 1（完整追蹤：MLB、AAA）
ratio > 0.1   → Tier 2（部分追蹤：部分 A 級/ROK 球場）
其餘（含 0 球）→ Tier 3（僅結果資料：AA、A+、多數 ROK）
```

Tier 2 的處理原則：有追蹤的球照 Tier 1 計算並在圖說標註 `N/M 球有追蹤資料`；速度/位置類統計只用 tracked 子集。

### 0.3 各區塊 × Tier fallback 矩陣（含固定文案）

「─」= 該區塊照常顯示；「✗」= 整塊不渲染。fallback 文案原樣使用：

| 區塊 | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|
| 每場摘要列（stats_json） | ─ | ─ | ─（所有層級都有 box score） |
| 本壘板視角逐球位置圖 | ─ | ─（只畫 tracked 球＋標註） | ✗，改渲染「逐球結果條」（§0.4.6）＋文案 `此層級（AA/A+）無進壘點追蹤資料，以下改以結果序列呈現` |
| 球速序列圖 | ─ | ─（只畫 tracked） | ✗，文案 `此層級無球速追蹤資料` |
| 位移疊圖（HB/IVB） | ─ | ─ | ✗（不顯示文案，直接省略） |
| 打者熱區圖（季héat＋本週疊點） | ─ | ─ | ✗，文案 `此層級無進壘點追蹤資料，無法繪製熱區` |
| EV/LA 散點 | ─ | ─（樣本標註） | ✗，改渲染「擊球品質替代圖」：hardness 分佈＋GB/LD/FB 長條（週 vs 季） |
| 落點圖 spray chart | ─ | ─ | ─（`hit_coord` 各層級都有；單場 0 筆擊球才省略） |
| 球種 delta 表（usage/velo/whiff…） | ─ | ─（velo 欄可能空） | 只留 usage 欄（pitch_type 缺 → 整表 ✗，文案 `此層級無球種標記資料`） |
| 選球 delta（chase/whiff/zone…） | ─ | ─ | zone/chase 需 `zone` 欄 → 缺時只顯示 whiff%、SwStr%（可由 result_code 判定），其餘格顯示 `–` 加 tooltip `需進壘點資料` |
| VAA/EffVelo/spin clock | ─ | ─（樣本≥5 才顯示） | ✗ |
| 週 vs 季 delta chips | ─ | ─（門檻同 §0.6） | 只出結果型 chips（K%、BB%、whiff%） |
| 失分事件明細（runners） | ─ | ─ | ─（runners 各層級都有） |
| 季基準缺失（該層級無 season statcast） | 顯示週值原始數字，chips 全省略，文案 `本層級樣本尚不足以建立季基準` | 同左 | 同左 |

### 0.4 報告版面與數據定義

#### 0.4.1 清單卡片（收合狀態，`<details><summary>`）

頭像（沿用 `headshot_cdn_urls` ＋ `avatar-fallback.js`）、中英文名、球隊＋層級徽章（`level_display` filter）、每場一列 `07/03 客 @BUF — 5.0 IP, 0 ER, 8 K, 0 BB`、右側最多 2 個 chips。

#### 0.4.2 投手展開報告（區塊順序）

1. **週彙總列**：合計 IP（`stats_json.inningsPitched` 以 outs 相加換算）、ER、K、BB、H、用球數；週 CSW%、Whiff%、Zone%、F-Strike%、Edge%（=shadow 區佔比）；牽制次數（`events_json` 中 `type=="pickoff"` 的計數，>0 才顯示）。旁掛全部 chips。
2. **自動重點（notes）**：規則式中文句（§0.6 規則），0 條時整塊省略。
3. **逐場明細**：每場一個小節＝摘要列＋該場圖表格（本壘板逐球位置圖、球速序列圖、位移疊圖，依 Tier fallback）。
4. **球種週 vs 季表**：每球種一列 — 週 usage%（vs 季 delta pp）、週均速（vs 季 delta）、whiff%、chase%、zone% delta、週 VAA、EffVelo、spin clock、`NEW`/`棄用` 徽章。
5. **失分事件明細**：由 `runners` 取 `is_scoring_event` — `日期 / 局 / 事件描述 / 自責與否`。
6. fallback 文案區（依 §0.3 觸發時渲染於對應區塊原位）。

#### 0.4.3 打者展開報告（區塊順序）

1. **週彙總列**：AB-H（由各場 `stats_json` 加總）、HR、RBI、BB、K、週 AVG；K%、BB%（由 `pa_final` 算）＋ chips。
2. **自動重點（notes）**。
3. **打者熱區圖**：季 per-zone AVG heatmap（9 宮格＋外側 11–14 四個 L 區）為底，疊本週 PA 終結球位置點。圖說固定：`底色＝本季各區打擊率（樣本不足處灰色顯示 n），圓點＝本週打席終結球位置`。
4. **逐場明細**：每場摘要列＋圖表格（所見球位置圖、EV/LA 散點、spray chart，依 Tier fallback；Tier 3 → 逐球結果條＋擊球品質替代圖〔每報告一張，週 vs 季〕）。
5. **選球 delta 表**：Chase%（O-Swing）、Whiff%、Z-Contact%、SwStr%、Zone%（週值、季值、delta）。
6. **分球種對戰表**：速球群/變化球群/慢速球群 — 球數、whiff%、終結球 H/AB、平均 EV。
7. **兩好球表現**：`pre_strikes==2` 的 PA 數、K、H、AVG。
8. **逐打席時間軸**：每 PA 一列 — 局數、投手左右、球種序列（縮寫 tag）、結果（`pa_event_desc`）；擊進場內的 PA 附 `EV / 飛行距離（hit_distance）`。
9. 週彙總的 EV 區塊在有 `bat_speed`（MLB withMetrics 新欄位）時顯示週平均揮棒速度。

#### 0.4.4 球種群組定義

```
FASTBALLS = {"FF","FA","SI","FT","FC"}
BREAKING  = {"SL","ST","SV","CU","KC","CS","KN","EP"}
OFFSPEED  = {"CH","FS","FO","SC"}
```

#### 0.4.5 熱區（zone）統計定義

- 使用既有 `zone` 欄（1–9 好球帶九宮格、11–14 外側四象限）。
- **每區 AVG**：分母＝該區為「PA 終結球」且 `pa_event` ∈ AB_EVENTS 的 PA 數；分子＝ ∈ HIT_EVENTS。`NON_PA_EVENTS`（constants.py）排除。
- **每區 swing% / whiff%**：對「每一球」計，分母各為該區球數 / 該區揮棒數。
- 遮罩：`ab < 5`（AVG）或 `swings < 5`（whiff%）的格子畫表面灰 `#232327`、只印 `n=N`。

#### 0.4.6 逐球結果條（Tier 3 的 HTML fallback，非圖表）

模板直接渲染：每球一個 10×10px 方塊，依 result class 上色（in-play `#3987e5`、whiff `#e66767`、called strike `#c98500`、foul `#71717a`、ball `#3f3f46`），PA 終結球加 teal 外框，hover title 顯示 `result_desc`。附靜態圖例。

### 0.5 圖表視覺規格（dataviz 已驗證）

- **表面/墨色**（對齊 `src/static/css/base.css` tokens）：surface `#18181b`、主文字 `#fafafa`、次 `#a1a1aa`、輔 `#71717a`、格線 `#27272a`、強調 `#14b8a6`。
- **類別色票**（dataviz 參考色盤 dark 欄，已驗證於 `#18181b` 表面全數 ≥3:1 對比；相鄰 CVD ΔE 10.3 屬 floor band → 一律加形狀/圖例第二編碼）：blue `#3987e5`、aqua `#199e70`、yellow `#c98500`、green `#008300`、violet `#9085e9`、red `#e66767`、magenta `#d55181`、orange `#d95926`。
- **球種→顏色固定註冊表**（色跟實體走，全站一致，不得按使用率輪派）：FF/FA→red、SI/FT→orange、FC→magenta、SL→blue、ST/SV→aqua、CU/KC/CS→violet、CH/SC→green、FS/FO→yellow、其他→中性灰 `#71717a`。
- **結果→標記形狀固定表**：in-play `D`（菱形）、whiff `X`、called strike `s`（方）、foul `^`（三角）、ball `o`（空心圓）。
- **軌跡→顏色固定表**（spray/替代圖）：GB→yellow、LD→red、FB→blue、PU→violet。
- **順序色階**（熱區 AVG 等連續量值；深色表面上「高值＝亮端」）：`#184f95 → #256abf → #3987e5 → #6da7ec → #9ec5f4 → #cde2fb`；AVG 正規化 vmin=.150 vmax=.400（夾擠）。
- 單軸原則：任何圖不得雙 y 軸。圖內每格/每點不逐一標數值——只有熱區格（本身是表格式）與長條圖頂端印值（亮格用深墨 `#09090b`、暗格用 `#fafafa`）。
- 每張圖 `<img loading="lazy">`（尺寸由 CSS `width:100%; height:auto` 控制）並包在 `overflow-x:auto` 的網格容器。

### 0.6 delta chips／notes 門檻表

chip 結構 `{"label","value_str","delta_str","cls":"up"|"down","good":bool}`；`good` 由「角色×指標方向」決定（投手 velo↑好、whiff↑好、對手 chase↑好、被打 EV↓好；打者 chase↓好、whiff↓好、Z-Contact↑好、EV↑好、hard-hit↑好）。

| 指標 | 觸發門檻 | 最小樣本（週） |
|---|---|---|
| 球種均速 | ±0.5 mph | 該球種 ≥5 球 |
| 球種 usage | ±5 pp | 週總球數 ≥30 |
| Whiff%/Chase%/Zone%/CSW% | ±3 pp | 相應分母 ≥20 |
| 平均 EV（打者/被打） | ±2.0 mph | BBE ≥5 |
| Hard-Hit% | ±8 pp | BBE ≥5 |
| F-Strike% | ±5 pp | 首球 PA ≥8 |
| `NEW` 球種徽章 | 週 usage ≥3% 且 ≥3 球，季 usage <2%（或季無此球種） | — |
| `棄用` 徽章 | 季 usage ≥5%、週 0 球 | 週總球數 ≥30 |

notes（自動重點）＝把觸發的 chips 轉成中文句，取影響最大的前 4 條，格式如：`滑球使用率 18% → 31%（▲13pp）`、`四縫線均速 ▲ +1.3 mph`、`Chase% 34% → 25%（▼9pp）`、`新球種：Sweeper（本週 12 球）`。

### 0.7 衍生指標公式（`stats/recent/derived.py`）

全部輸入為 extract.py 的 pitch dict；任何必要欄位缺 → 回傳 `None`。

| 指標 | 公式 |
|---|---|
| VAA | `vy_f = -sqrt(vy0² − 2·ay·(50 − 17/12))`；`t = (vy_f − vy0)/ay`；`vz_f = vz0 + az·t`；`VAA = −atan(vz_f/vy_f)·180/π` |
| HAA | 同上以 `vx0, ax` 換算 `vx_f`；`HAA = −atan(vx_f/vy_f)·180/π` |
| Effective Velocity | `start_speed × 54 / (60.5 − extension)`（54 = 60.5 − 聯盟平均 extension 6.5） |
| 球速衰減 | `start_speed − end_speed` |
| Spin clock | `total_min = round(((spin_dir−180) mod 360)/30 × 60 / 15)×15 mod 720`；`hh = total_min//60 or 12`；輸出 `"h:mm"`（180°→12:00、210°→1:00） |
| 正規化進壘點 | `x_norm = px/0.83`；`z_norm = (pz − (top+bot)/2)/((top−bot)/2)`；top/bot 用該球 `strike_zone_top/bottom`，缺值 fallback 3.4/1.6 |
| Attack zone | `m = max(|x_norm|,|z_norm|)`：≤0.67 heart、≤1.33 shadow、≤2.0 chase、其餘 waste（Savant 近似版，需註記） |
| Edge% | shadow 球數 / 有座標球數 |
| F-Strike% | `pre_balls==0 且 pre_strikes==0` 的球中 `is_strike or is_in_play` 佔比 |
| 轉軸均值 | 圓形平均（atan2 of Σsin/Σcos），供 spin clock 顯示與 >15° 偏移 note |

### 0.8 影片來源與分級（依 `docs/pitch_video_embedding.md`）

- **來源 A（第一階段，本 plan 實作）**：sync 時抓 `GET /api/v1/game/{gamePk}/content`，`highlights.highlights.items[].guid == play_id` 的 item 取 `playbacks[]` 中 `mp4Avc` URL（`mlb-cuts-diamond.mlb.com` 永久連結），存新表 `play_videos`。只處理 `sport_level=='MLB'` 的比賽。索引延遲對策：`videos_found=0` 且比賽日期在 14 天內的比賽每次 sync 重試。
- **來源 B（第二階段，同 plan 內實作前端）**：MLB 球有 `play_id` 但無精華 mp4 → 按鈕開 overlay `<iframe src="https://baseballsavant.mlb.com/sporty-videos?playId=...">`，overlay 內固定顯示外部連結與文案 `影片可能需要 1 天以上才會上架；若無畫面請點此前往 Baseball Savant`。**不做 iframe 內容偵測**（跨域讀不到，文案取代之——覆蓋調查文件 §7 的偵測構想）。
- **層級 gating**：非 MLB 比賽的 pitch log JSON 一律不含 `play_id`/`video` 欄 → 前端自然不出現任何影片按鈕（在資料層杜絕調查文件風險 6）。
- 法律風險（調查文件風險 1）不在本 plan 範圍：Task V3 完成後功能預設上線，正式對外前由維護者自行確認條款。

### 0.9 圖檔產量控制

matplotlib 圖**只**為近 7 天視窗生成（每週約 28 場 × ≤3 張 ＋ 每打者 1 張熱區 ≈ <100 張 PNG、<8MB）；不為歷史比賽生成。輸出至 `dist/static/charts/recents/{mlb_id}/{game_pk}-{name}.png`，每次 build 全量重建（`dist/` 本來就 rm -rf）。

---

## 檔案結構總覽

```
site_builder/
  charts/                     # 新：matplotlib 圖表引擎（與 graph/ 同層）
    __init__.py
    style.py                  # 主題、色票、result/球種註冊表、new_fig/save_chart
    plate.py                  # 本壘板視角逐球位置圖
    zones.py                  # 熱區 heatmap（季底＋週疊點）
    velocity.py               # 單場球速序列圖
    movement_game.py          # 單場位移疊圖（季 ghost）
    batted.py                 # EV/LA、spray、Tier3 擊球品質替代圖
  stats/recent/               # 新：週報告計算（純函式，無 IO）
    __init__.py
    window.py                 # 近 7 天視窗載入 + Tier 判定
    derived.py                # VAA/HAA/EffVelo/spin clock/attack zone/F-Strike
    zone_stats.py             # per-zone AVG/swing/whiff 統計
    pitcher_report.py
    batter_report.py
    highlights.py             # chips + notes 規則引擎
  api/content.py              # 新：game content 端點 + 精華影片抽取
  db/play_videos.py           # 新：play_videos / game_content_processed 查詢
  render/recents.py           # 新：組 context、產圖、寫 recents/index.html

src/templates/recents.j2
src/templates/partials/recent_pitcher_report.j2
src/templates/partials/recent_batter_report.j2
src/static/css/recents.css    # + style.css 加一行 @import
tests/recent_fixtures.py      # make_pitch() fixture helper
tests/test_recent_window.py  tests/test_recent_derived.py  tests/test_zone_stats.py
tests/test_charts.py         tests/test_recent_reports.py  tests/test_highlights.py
tests/test_content_api.py    tests/test_play_videos.py     tests/test_pitch_log_video.py
```

修改：`requirements.txt`、`site_builder/db/schema.py`、`site_builder/sync/statcast.py`、`site_builder/render/pages.py`、`site_builder/render/pitch_log.py`、`src/templates/base.j2`、`src/static/js/pitch-log.js`、`src/static/css/style.css`、`src/static/css/gamelogs.css`、`docs/`。

---

## Phase 1 — 圖表基礎

### Task 1: matplotlib 依賴 ＋ `charts/style.py` 主題模組

**Files:**
- Modify: `requirements.txt`
- Create: `site_builder/charts/__init__.py`
- Create: `site_builder/charts/style.py`
- Test: `tests/test_charts.py`

**Interfaces:**
- Produces（後續所有 charts/ Task 依賴）：`SURFACE, INK_1, INK_2, INK_3, GRID, ACCENT, NEUTRAL`（str hex）；`pitch_color(ptype: str|None) -> str`；`TRAJECTORY_COLORS: dict[str,str]`；`SEQ_CMAP, DIV_CMAP`（matplotlib colormap）；`RESULT_MARKERS: tuple[(cls, marker, label)]`；`result_class(p: dict) -> str`；`PA_EVENT_ABBREV: dict[str,str]`；`new_fig(width: float, height: float) -> (Figure, Axes)`；`style_axes(ax)`；`save_chart(fig, out_path: Path) -> None`。

- [ ] **Step 1: 加依賴並安裝**

`requirements.txt` 末尾加一行：

```
matplotlib==3.10.3
```

執行：`pip install -r requirements.txt`。預期：安裝成功（matplotlib 的傳遞依賴 numpy 等由 pip 解析，不逐一 pin——requirements 其餘行維持原樣）。

- [ ] **Step 2: 寫失敗測試**

`tests/test_charts.py`：

```python
"""charts/ 圖表引擎測試：主題常數、result 分類與各 render_* 冒煙測試。"""
from pathlib import Path

from site_builder.charts import style


def test_pitch_color_registry_is_stable():
    assert style.pitch_color("FF") == "#e66767"
    assert style.pitch_color("SL") == "#3987e5"
    assert style.pitch_color("CH") == "#008300"
    assert style.pitch_color(None) == style.NEUTRAL
    assert style.pitch_color("ZZ") == style.NEUTRAL


def test_result_class():
    assert style.result_class({"is_in_play": True, "result_code": "D"}) == "inplay"
    assert style.result_class({"result_code": "S"}) == "whiff"
    assert style.result_class({"result_code": "T"}) == "whiff"  # foul tip 屬揮空
    assert style.result_class({"result_code": "C"}) == "called"
    assert style.result_class({"result_code": "F"}) == "foul"
    assert style.result_class({"result_code": "B", "is_ball": True}) == "ball"


def test_save_chart_writes_png(tmp_path):
    fig, ax = style.new_fig(4, 3)
    ax.plot([0, 1], [0, 1], color=style.ACCENT)
    out = tmp_path / "sub" / "smoke.png"
    style.save_chart(fig, out)
    assert out.is_file() and out.stat().st_size > 1000
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `python -m pytest tests/test_charts.py -v`
Expected: FAIL（`ModuleNotFoundError: site_builder.charts`）

- [ ] **Step 4: 實作**

`site_builder/charts/__init__.py`：

```python
"""Matplotlib static-chart engine (build-time PNG output).

Depends only on stats/, constants, util/ — same layer as graph/.
"""

# 先 import style 讓 matplotlib.use("Agg") 保證在任何子模組的 pyplot
# import 之前執行（子模組經由本套件載入時，__init__ 一定先跑）。
from . import style  # noqa: F401
```

`site_builder/charts/style.py`：

```python
"""圖表主題 — 全站 matplotlib 圖表外觀的單一事實來源。

深色單一主題（網站無亮色模式）。色票取自 dataviz 參考色盤 dark 欄，
已驗證於本站表面 #18181b：全數 WCAG 對比 ≥3:1；相鄰 CVD ΔE 屬 floor
band，故散點圖一律以標記形狀作第二編碼。圖內文字一律英文
（CI 無 CJK 字型）。
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 必須在 pyplot import 之前；CI 無 display
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from ..constants import CALLED_STRIKE_CODES, WHIFF_CODES  # noqa: E402

CHART_DPI = 180

# ── 網站 tokens（src/static/css/base.css）──
SURFACE = "#18181b"
INK_1 = "#fafafa"
INK_2 = "#a1a1aa"
INK_3 = "#71717a"
GRID = "#27272a"
BASELINE = "#3f3f46"
ACCENT = "#14b8a6"
NEUTRAL = "#71717a"
MASK_FILL = "#232327"

# ── 類別色票（dataviz dark 欄，見 plan §0.5）──
SLOT_BLUE = "#3987e5"
SLOT_AQUA = "#199e70"
SLOT_YELLOW = "#c98500"
SLOT_GREEN = "#008300"
SLOT_VIOLET = "#9085e9"
SLOT_RED = "#e66767"
SLOT_MAGENTA = "#d55181"
SLOT_ORANGE = "#d95926"

# 球種→顏色固定註冊表：色跟實體走，全站一致（不按使用率輪派）。
PITCH_TYPE_COLORS = {
    "FF": SLOT_RED, "FA": SLOT_RED,
    "SI": SLOT_ORANGE, "FT": SLOT_ORANGE,
    "FC": SLOT_MAGENTA,
    "SL": SLOT_BLUE,
    "ST": SLOT_AQUA, "SV": SLOT_AQUA,
    "CU": SLOT_VIOLET, "KC": SLOT_VIOLET, "CS": SLOT_VIOLET,
    "CH": SLOT_GREEN, "SC": SLOT_GREEN,
    "FS": SLOT_YELLOW, "FO": SLOT_YELLOW,
}

TRAJECTORY_COLORS = {
    "gb": SLOT_YELLOW, "ld": SLOT_RED, "fb": SLOT_BLUE, "pu": SLOT_VIOLET,
}

# 順序色階：深色表面上高值＝亮端（plan §0.5）
SEQ_CMAP = LinearSegmentedColormap.from_list(
    "seq_dark",
    ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"],
)
DIV_CMAP = LinearSegmentedColormap.from_list(
    "div_dark", ["#3987e5", "#383835", "#e66767"]
)

# 結果→標記形狀固定表（散點圖的 CVD 第二編碼）
RESULT_MARKERS = (
    ("inplay", "D", "In play"),
    ("whiff", "X", "Whiff"),
    ("called", "s", "Called strike"),
    ("foul", "^", "Foul"),
    ("ball", "o", "Ball"),
)
FOUL_CODES = {"F", "L", "R"}

PA_EVENT_ABBREV = {
    "single": "1B", "double": "2B", "triple": "3B", "home_run": "HR",
    "strikeout": "K", "strikeout_double_play": "K",
    "walk": "BB", "intent_walk": "IBB", "hit_by_pitch": "HBP",
    "field_out": "OUT", "force_out": "OUT", "fielders_choice_out": "FC",
    "fielders_choice": "FC", "grounded_into_double_play": "GDP",
    "double_play": "DP", "sac_fly": "SF", "sac_bunt": "SAC",
    "field_error": "E",
}


def pitch_color(ptype) -> str:
    return PITCH_TYPE_COLORS.get(ptype or "", NEUTRAL)


def result_class(p: dict) -> str:
    if p.get("is_in_play"):
        return "inplay"
    code = p.get("result_code", "")
    if code in WHIFF_CODES:
        return "whiff"
    if code in CALLED_STRIKE_CODES:
        return "called"
    if code in FOUL_CODES:
        return "foul"
    return "ball"


def style_axes(ax):
    ax.set_facecolor(SURFACE)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.tick_params(colors=INK_3, labelsize=8)
    ax.xaxis.label.set_color(INK_2)
    ax.yaxis.label.set_color(INK_2)
    ax.title.set_color(INK_1)
    ax.title.set_fontsize(10)
    ax.grid(color=GRID, linewidth=0.6, alpha=0.6)


def new_fig(width: float = 6.0, height: float = 4.5):
    fig, ax = plt.subplots(figsize=(width, height), facecolor=SURFACE)
    style_axes(ax)
    return fig, ax


def styled_legend(ax, handles, loc: str, fontsize: int = 7):
    """統一圖例外觀（深色底、細框、次要墨色字）。"""
    leg = ax.legend(
        handles=handles, loc=loc, fontsize=fontsize,
        facecolor=SURFACE, edgecolor=GRID, labelcolor=INK_2,
        framealpha=0.9, borderpad=0.6,
    )
    return leg


def save_chart(fig, out_path: Path) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        out_path, dpi=CHART_DPI, facecolor=fig.get_facecolor(),
        bbox_inches="tight", pad_inches=0.2,
    )
    plt.close(fig)
```

- [ ] **Step 5: 跑測試通過**

Run: `python -m pytest tests/test_charts.py -v`
Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add requirements.txt site_builder/charts/ tests/test_charts.py
git commit -m "feat: add matplotlib chart engine theme module (charts/style.py)"
```

---

## Phase 2 — recents 資料層

### Task 2: 測試 fixture helper ＋ `stats/recent/window.py`（視窗載入與 Tier 判定）

**Files:**
- Create: `site_builder/stats/recent/__init__.py`
- Create: `site_builder/stats/recent/window.py`
- Create: `tests/recent_fixtures.py`
- Test: `tests/test_recent_window.py`

**Interfaces:**
- Produces：`game_tier(pitches: list[dict]) -> int`（1/2/3）；`load_recent_window(cur, roster_ids: set[int], *, today: date|None = None, days: int = 7) -> list[dict]`，每個元素為 player-window dict：
  ```python
  {"mlb_id": int, "name_en": str, "name_tw": str, "team": str, "level": str,
   "position": str, "is_pitcher": bool,
   "games": [{"date": date, "game_id": int, "opponent": str, "is_home": bool|None,
              "sport_level": str, "stats": dict, "pitches": list[dict],
              "events": list[dict], "tier": int}, ...]}  # games 依日期升冪
  ```
  回傳依「最近出賽日」降冪排序。
- Consumes：`util.json.loads_json_dict/loads_json_list`、`util.dates.parse_date`。
- `tests/recent_fixtures.py::make_pitch(**overrides) -> dict`：所有後續測試共用。

- [ ] **Step 1: 寫 fixture helper**

`tests/recent_fixtures.py`：

```python
"""共用 pitch dict fixture — 欄位齊全的 Tier 1 MLB 球，測試以 overrides 客製。"""


def make_pitch(**overrides) -> dict:
    base = dict(
        game_pk=776911, inning=1,
        pitch_type="FF", pitch_name="Four-Seam Fastball",
        result_code="C", result_desc="Called Strike",
        is_strike=True, is_ball=False, is_in_play=False,
        zone=5, start_speed=95.0, end_speed=87.0, extension=6.5,
        plate_time=0.40, type_confidence=0.95,
        strike_zone_top=3.4, strike_zone_bottom=1.6,
        pfx_x=-6.0, pfx_z=14.0, px=0.0, pz=2.5,
        x0=-1.5, z0=5.8, vx0=2.0, vy0=-135.0, vz0=-5.0,
        ax=-8.0, ay=25.0, az=-15.0,
        ivb=15.0, hb=8.0, spin_rate=2300, spin_dir=210.0,
        break_angle=None, break_length=None, break_y=None, break_vertical=None,
        ev=None, la=None, hit_distance=None, trajectory="", hit_location=None,
        hit_coord_x=None, hit_coord_y=None, hardness="",
        balls=0, strikes=1, pre_balls=0, pre_strikes=0, pre_outs=0, outs=0,
        batter_id=592885, pitcher_id=678906, bat_side="R", pitch_hand="R",
        is_pa_final=False, pa_event="", pa_event_desc="", runners=None,
        play_id="b339cea8-e12d-340f-adbc-a655fb63aaed", pitch_number=1,
    )
    base.update(overrides)
    return base


def make_untracked_pitch(**overrides) -> dict:
    """Tier 3（AA/A+）球：無追蹤欄位，只有結果。"""
    p = make_pitch(
        pitch_type="", pitch_name="", zone=None, start_speed=None,
        end_speed=None, extension=None, px=None, pz=None,
        x0=None, z0=None, vx0=None, vy0=None, vz0=None,
        ax=None, ay=None, az=None, ivb=None, hb=None,
        spin_rate=None, spin_dir=None,
        play_id="07821736-0016-0013-000c-f08cd117d70a",
    )
    p.update(overrides)
    return p
```

- [ ] **Step 2: 寫失敗測試**

`tests/test_recent_window.py`：

```python
import datetime
import json
import sqlite3

from site_builder.db.schema import init_db
from site_builder.stats.recent.window import game_tier, load_recent_window
from tests.recent_fixtures import make_pitch, make_untracked_pitch

TODAY = datetime.date(2026, 7, 9)


def test_game_tier():
    assert game_tier([make_pitch() for _ in range(10)]) == 1
    mixed = [make_pitch() for _ in range(3)] + [make_untracked_pitch() for _ in range(7)]
    assert game_tier(mixed) == 2
    assert game_tier([make_untracked_pitch() for _ in range(10)]) == 3
    assert game_tier([]) == 3


def _seed(conn):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO players (mlb_id, name_en, name_tw, team, level, position) "
        "VALUES (678906, 'Kai-Wei Teng', '鄧愷威', 'Sacramento River Cats', 'AAA', 'P')"
    )
    pitches = json.dumps([make_pitch(), make_pitch(result_code="S")])
    cur.execute(
        "INSERT INTO game_logs (player_mlb_id, date, game_id, opponent, is_home,"
        " stats_json, pitches_json, events_json, sport_level) VALUES"
        " (678906, '2026-07-06', 111, 'BUF', 1,"
        "  '{\"inningsPitched\": \"5.0\"}', ?, '[]', 'AAA')",
        (pitches,),
    )
    # 視窗外（8 天前）的比賽不得入選
    cur.execute(
        "INSERT INTO game_logs (player_mlb_id, date, game_id, opponent, is_home,"
        " stats_json, pitches_json, events_json, sport_level) VALUES"
        " (678906, '2026-07-01', 110, 'LV', 0, '{}', 'null', '[]', 'AAA')"
    )
    conn.commit()


def test_load_recent_window():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)
    windows = load_recent_window(conn.cursor(), {678906}, today=TODAY)
    assert len(windows) == 1
    w = windows[0]
    assert w["mlb_id"] == 678906 and w["is_pitcher"] is True
    assert [g["game_id"] for g in w["games"]] == [111]
    g = w["games"][0]
    assert g["tier"] == 1 and g["sport_level"] == "AAA"
    assert g["stats"]["inningsPitched"] == "5.0"
    assert len(g["pitches"]) == 2


def test_load_recent_window_empty_roster():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    assert load_recent_window(conn.cursor(), set(), today=TODAY) == []
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `python -m pytest tests/test_recent_window.py -v`
Expected: FAIL（module not found）

- [ ] **Step 4: 實作**

`site_builder/stats/recent/__init__.py`：

```python
"""近 7 天出賽報告的計算層（純函式；檔案 IO 一律在 render/recents.py）。"""
```

`site_builder/stats/recent/window.py`：

```python
"""近 N 天出賽視窗載入 + 單場資料分級（Tier）判定。"""

import datetime

from ...util.dates import parse_date
from ...util.json import loads_json_dict, loads_json_list

WINDOW_DAYS = 7

# Tier 門檻（plan §0.2）
_T1_RATIO = 0.8
_T2_RATIO = 0.1


def game_tier(pitches: list[dict]) -> int:
    """單場資料等級：1 完整追蹤 / 2 部分 / 3 僅結果。"""
    if not pitches:
        return 3
    tracked = sum(
        1 for p in pitches
        if p.get("px") is not None and p.get("start_speed") is not None
    )
    ratio = tracked / len(pitches)
    if ratio >= _T1_RATIO:
        return 1
    if ratio > _T2_RATIO:
        return 2
    return 3


def load_recent_window(cur, roster_ids, *, today=None, days: int = WINDOW_DAYS):
    """回傳視窗內有出賽的球員清單（結構見 tests/test_recent_window.py）。"""
    if not roster_ids:
        return []
    today = today or datetime.date.today()
    cutoff = (today - datetime.timedelta(days=days)).isoformat()
    ids = sorted(roster_ids)
    placeholders = ",".join("?" * len(ids))
    cur.execute(
        "SELECT g.player_mlb_id, g.date, g.game_id, g.opponent, g.is_home,"
        "       g.sport_level, g.stats_json, g.pitches_json, g.events_json,"
        "       p.name_en, p.name_tw, p.team, p.level, p.position "
        "FROM game_logs g JOIN players p ON p.mlb_id = g.player_mlb_id "
        f"WHERE g.date >= ? AND g.player_mlb_id IN ({placeholders}) "
        "ORDER BY g.player_mlb_id, g.date",
        [cutoff, *ids],
    )
    by_player: dict[int, dict] = {}
    for row in cur.fetchall():
        pitches = loads_json_list(row[7])
        entry = by_player.setdefault(row[0], {
            "mlb_id": row[0],
            "name_en": row[9], "name_tw": row[10],
            "team": row[11], "level": row[12],
            "position": row[13] or "",
            "is_pitcher": (row[13] or "") == "P",
            "games": [],
        })
        entry["games"].append({
            "date": parse_date(row[1]),
            "game_id": row[2],
            "opponent": row[3],
            "is_home": None if row[4] is None else bool(row[4]),
            "sport_level": row[5] or "",
            "stats": loads_json_dict(row[6]),
            "pitches": pitches,
            "events": loads_json_list(row[8]),
            "tier": game_tier(pitches),
        })
    windows = list(by_player.values())
    windows.sort(
        key=lambda w: max(
            (g["date"] for g in w["games"] if g["date"]),
            default=datetime.date.min,
        ),
        reverse=True,
    )
    return windows
```

- [ ] **Step 5: 跑測試通過**

Run: `python -m pytest tests/test_recent_window.py -v`
Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add site_builder/stats/recent/ tests/recent_fixtures.py tests/test_recent_window.py
git commit -m "feat: recent-window loader with per-game data-tier detection"
```

---

### Task 3: `stats/recent/derived.py`（衍生指標）

**Files:**
- Create: `site_builder/stats/recent/derived.py`
- Test: `tests/test_recent_derived.py`

**Interfaces:**
- Produces：`compute_vaa(p) -> float|None`、`compute_haa(p) -> float|None`、`effective_velocity(p) -> float|None`、`velocity_decay(p) -> float|None`、`spin_clock(spin_dir) -> str|None`、`circular_mean_deg(values) -> float|None`、`normalized_location(p) -> tuple[float,float]|None`、`attack_zone(p) -> str|None`（"heart"/"shadow"/"chase"/"waste"）、`attack_zone_distribution(pitches) -> dict|None`（keys: heart/shadow/chase/waste/n）、`edge_pct(pitches) -> float|None`、`f_strike_pct(pitches) -> float|None`、`derived_by_pitch_type(pitches) -> dict[str, dict]`（keys: vaa/haa/eff_velo/velo_decay/spin_dir_mean/spin_clock/n）。
- 公式與 fallback 值見 plan §0.7。

- [ ] **Step 1: 寫失敗測試**

`tests/test_recent_derived.py`：

```python
import pytest

from site_builder.stats.recent import derived
from tests.recent_fixtures import make_pitch, make_untracked_pitch


def test_vaa_haa_known_vectors():
    # 期望值以 §0.7 公式手算：vy0=-135, ay=25, vz0=-5, az=-15, vx0=2, ax=-8
    p = make_pitch()
    assert derived.compute_vaa(p) == pytest.approx(-4.817, abs=0.01)
    assert derived.compute_haa(p) == pytest.approx(-0.448, abs=0.01)
    assert derived.compute_vaa(make_untracked_pitch()) is None


def test_effective_velocity_and_decay():
    p = make_pitch(start_speed=95.0, extension=7.5, end_speed=87.5)
    assert derived.effective_velocity(p) == pytest.approx(96.79, abs=0.01)
    assert derived.velocity_decay(p) == pytest.approx(7.5)
    assert derived.effective_velocity(make_pitch(extension=None)) is None


def test_spin_clock():
    assert derived.spin_clock(180) == "12:00"
    assert derived.spin_clock(210) == "1:00"
    assert derived.spin_clock(270) == "3:00"
    assert derived.spin_clock(90) == "9:00"
    assert derived.spin_clock(195) == "12:30"
    assert derived.spin_clock(179) == "12:00"  # 719' 進位回 12:00
    assert derived.spin_clock(None) is None


def test_circular_mean_deg():
    assert derived.circular_mean_deg([350, 10]) == pytest.approx(0.0, abs=0.1)
    assert derived.circular_mean_deg([90, 90]) == pytest.approx(90.0)
    assert derived.circular_mean_deg([]) is None


def test_attack_zone():
    assert derived.attack_zone(make_pitch(px=0.0, pz=2.5)) == "heart"
    assert derived.attack_zone(make_pitch(px=0.9, pz=2.5)) == "shadow"
    assert derived.attack_zone(make_pitch(px=1.5, pz=2.5)) == "chase"
    assert derived.attack_zone(make_pitch(px=2.5, pz=2.5)) == "waste"
    assert derived.attack_zone(make_untracked_pitch()) is None


def test_attack_zone_distribution_and_edge():
    pitches = [make_pitch(px=0.0), make_pitch(px=0.9), make_pitch(px=0.9),
               make_pitch(px=2.5), make_untracked_pitch()]
    dist = derived.attack_zone_distribution(pitches)
    assert dist["n"] == 4
    assert dist["shadow"] == pytest.approx(0.5)
    assert derived.edge_pct(pitches) == pytest.approx(0.5)
    assert derived.attack_zone_distribution([make_untracked_pitch()]) is None


def test_f_strike_pct():
    pitches = [
        make_pitch(pre_balls=0, pre_strikes=0, is_strike=True),
        make_pitch(pre_balls=0, pre_strikes=0, is_strike=False, is_in_play=True),
        make_pitch(pre_balls=0, pre_strikes=0, is_strike=False, is_ball=True),
        make_pitch(pre_balls=1, pre_strikes=0),  # 非首球，不入分母
    ]
    assert derived.f_strike_pct(pitches) == pytest.approx(2 / 3, abs=1e-6)
    assert derived.f_strike_pct([]) is None


def test_derived_by_pitch_type():
    pitches = [make_pitch(), make_pitch(), make_pitch(pitch_type="SL", spin_dir=45.0)]
    out = derived.derived_by_pitch_type(pitches)
    assert set(out) == {"FF", "SL"}
    assert out["FF"]["n"] == 2
    assert out["FF"]["spin_clock"] == "1:00"
    assert out["FF"]["vaa"] == pytest.approx(-4.8, abs=0.05)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_recent_derived.py -v`
Expected: FAIL（module not found）

- [ ] **Step 3: 實作**

`site_builder/stats/recent/derived.py`：

```python
"""週報告的衍生指標（VAA/HAA、感知球速、轉軸時鐘、attack zone…）。

公式見 docs/superpowers/plans/2026-07-09-recents-charts-video.md §0.7。
所有函式對缺欄位回傳 None（best-effort，不 raise）。
"""

import math

from ...util.numbers import float_or_none, mean_round, ratio
from ..core.pitches import filter_known_pitch_events

PLATE_Y_FT = 17 / 12          # 本壘板前緣
RELEASE_MEASURE_Y_FT = 50.0   # MLB 座標系向量的量測點
PLATE_HALF_WIDTH_FT = 0.83    # 半板寬 + 球半徑
DEFAULT_SZ_TOP = 3.4
DEFAULT_SZ_BOT = 1.6
LEAGUE_AVG_EXTENSION = 6.5


def _plate_velocity(p):
    """回傳 (t, vy_f)：到本壘板前緣的剩餘飛行參數；缺資料回 None。"""
    vy0 = float_or_none(p.get("vy0"))
    ay = float_or_none(p.get("ay"))
    if vy0 is None or ay is None or ay == 0:
        return None
    disc = vy0 * vy0 - 2 * ay * (RELEASE_MEASURE_Y_FT - PLATE_Y_FT)
    if disc <= 0:
        return None
    vy_f = -math.sqrt(disc)
    return (vy_f - vy0) / ay, vy_f


def compute_vaa(p: dict):
    base = _plate_velocity(p)
    vz0 = float_or_none(p.get("vz0"))
    az = float_or_none(p.get("az"))
    if base is None or vz0 is None or az is None:
        return None
    t, vy_f = base
    vz_f = vz0 + az * t
    return round(-math.degrees(math.atan(vz_f / vy_f)), 2)


def compute_haa(p: dict):
    base = _plate_velocity(p)
    vx0 = float_or_none(p.get("vx0"))
    ax = float_or_none(p.get("ax"))
    if base is None or vx0 is None or ax is None:
        return None
    t, vy_f = base
    vx_f = vx0 + ax * t
    return round(-math.degrees(math.atan(vx_f / vy_f)), 2)


def effective_velocity(p: dict):
    velo = float_or_none(p.get("start_speed"))
    ext = float_or_none(p.get("extension"))
    if velo is None or ext is None or ext >= 60.5:
        return None
    return round(velo * (60.5 - LEAGUE_AVG_EXTENSION) / (60.5 - ext), 2)


def velocity_decay(p: dict):
    start = float_or_none(p.get("start_speed"))
    end = float_or_none(p.get("end_speed"))
    if start is None or end is None:
        return None
    return round(start - end, 2)


def spin_clock(spin_dir):
    sd = float_or_none(spin_dir)
    if sd is None:
        return None
    total_min = round((((sd - 180) % 360) / 30) * 60 / 15) * 15 % 720
    hh = total_min // 60 or 12
    return f"{int(hh)}:{int(total_min % 60):02d}"


def circular_mean_deg(values):
    vs = [v for v in (float_or_none(v) for v in values) if v is not None]
    if not vs:
        return None
    x = sum(math.cos(math.radians(v)) for v in vs)
    y = sum(math.sin(math.radians(v)) for v in vs)
    if x == 0 and y == 0:
        return None
    return round(math.degrees(math.atan2(y, x)) % 360, 1)


def normalized_location(p: dict):
    px = float_or_none(p.get("px"))
    pz = float_or_none(p.get("pz"))
    if px is None or pz is None:
        return None
    top = float_or_none(p.get("strike_zone_top")) or DEFAULT_SZ_TOP
    bot = float_or_none(p.get("strike_zone_bottom")) or DEFAULT_SZ_BOT
    if top <= bot:
        return None
    x_norm = px / PLATE_HALF_WIDTH_FT
    z_norm = (pz - (top + bot) / 2) / ((top - bot) / 2)
    return x_norm, z_norm


def attack_zone(p: dict):
    loc = normalized_location(p)
    if loc is None:
        return None
    m = max(abs(loc[0]), abs(loc[1]))
    if m <= 0.67:
        return "heart"
    if m <= 1.33:
        return "shadow"
    if m <= 2.0:
        return "chase"
    return "waste"


def attack_zone_distribution(pitches: list[dict]):
    counts = {"heart": 0, "shadow": 0, "chase": 0, "waste": 0}
    n = 0
    for p in pitches:
        z = attack_zone(p)
        if z:
            counts[z] += 1
            n += 1
    if not n:
        return None
    out = {k: ratio(v, n) for k, v in counts.items()}
    out["n"] = n
    return out


def edge_pct(pitches: list[dict]):
    dist = attack_zone_distribution(pitches)
    return dist["shadow"] if dist else None


def f_strike_pct(pitches: list[dict]):
    first = [
        p for p in pitches
        if p.get("pre_balls") == 0 and p.get("pre_strikes") == 0
    ]
    if not first:
        return None
    strikes = sum(1 for p in first if p.get("is_strike") or p.get("is_in_play"))
    return ratio(strikes, len(first), digits=6)


def derived_by_pitch_type(pitches: list[dict]) -> dict:
    by_type: dict[str, list[dict]] = {}
    for p in filter_known_pitch_events(pitches):
        by_type.setdefault(p.get("pitch_type") or "UN", []).append(p)
    out = {}
    for ptype, ps in by_type.items():
        spin_mean = circular_mean_deg([p.get("spin_dir") for p in ps])
        out[ptype] = {
            "n": len(ps),
            "vaa": mean_round([compute_vaa(p) for p in ps], 1),
            "haa": mean_round([compute_haa(p) for p in ps], 1),
            "eff_velo": mean_round([effective_velocity(p) for p in ps], 1),
            "velo_decay": mean_round([velocity_decay(p) for p in ps], 1),
            "spin_dir_mean": spin_mean,
            "spin_clock": spin_clock(spin_mean),
        }
    return out
```

- [ ] **Step 4: 跑測試通過**

Run: `python -m pytest tests/test_recent_derived.py -v`
Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add site_builder/stats/recent/derived.py tests/test_recent_derived.py
git commit -m "feat: derived pitch metrics (VAA/HAA, eff-velo, spin clock, attack zones)"
```

---

### Task 4: `stats/recent/zone_stats.py`（per-zone 熱區統計）

**Files:**
- Create: `site_builder/stats/recent/zone_stats.py`
- Test: `tests/test_zone_stats.py`

**Interfaces:**
- Produces：`compute_zone_stats(pitches: list[dict]) -> dict[int, dict]` — key 為 zone（1–9、11–14），value：`{"n": int, "swings": int, "whiffs": int, "swing_pct": float|None, "whiff_pct": float|None, "ab": int, "hits": int, "avg": float|None}`。只含 n>0 的 zone。
- Produces：`HIT_EVENTS: frozenset[str]`、`AB_EVENTS: frozenset[str]`（Task 10 的打者分組表也用）。
- 定義見 plan §0.4.5：AVG 以「PA 終結球」歸區；swing/whiff 對每球計；`NON_PA_EVENTS` 排除。

- [ ] **Step 1: 寫失敗測試**

`tests/test_zone_stats.py`：

```python
import pytest

from site_builder.stats.recent.zone_stats import compute_zone_stats
from tests.recent_fixtures import make_pitch, make_untracked_pitch


def _final(zone, event, code="D"):
    return make_pitch(zone=zone, is_pa_final=True, pa_event=event,
                      result_code=code, is_in_play=code in ("D", "E", "X"))


def test_zone_avg_counts_final_pitch_only():
    pitches = [
        make_pitch(zone=5, result_code="S"),               # 揮空，非終結
        _final(5, "single"),
        _final(5, "field_out", code="X"),
        _final(5, "walk", code="B"),                        # 非 AB，不入 AVG
        _final(2, "home_run", code="E"),
        _final(5, "caught_stealing_2b", code="B"),          # NON_PA_EVENT 排除
    ]
    zs = compute_zone_stats(pitches)
    assert zs[5]["ab"] == 2 and zs[5]["hits"] == 1
    assert zs[5]["avg"] == pytest.approx(0.5)
    assert zs[2]["ab"] == 1 and zs[2]["avg"] == pytest.approx(1.0)


def test_zone_swing_whiff_per_pitch():
    pitches = [
        make_pitch(zone=13, result_code="S"),   # swing + whiff
        make_pitch(zone=13, result_code="F"),   # swing
        make_pitch(zone=13, result_code="B", is_strike=False, is_ball=True),
    ]
    zs = compute_zone_stats(pitches)
    assert zs[13]["n"] == 3 and zs[13]["swings"] == 2 and zs[13]["whiffs"] == 1
    assert zs[13]["swing_pct"] == pytest.approx(2 / 3, abs=1e-6)
    assert zs[13]["whiff_pct"] == pytest.approx(0.5)


def test_zone_stats_skips_zoneless():
    assert compute_zone_stats([make_untracked_pitch()]) == {}
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_zone_stats.py -v` → FAIL（module not found）

- [ ] **Step 3: 實作**

`site_builder/stats/recent/zone_stats.py`：

```python
"""好球帶 per-zone 統計（zone 1–9 九宮格、11–14 外側象限）。

AVG 以 PA 終結球的 zone 歸區（Savant 熱區同法）；swing/whiff 對每球計。
"""

from ...constants import NON_PA_EVENTS
from ...util.numbers import ratio
from ..core.pitches import is_swing, is_whiff

HIT_EVENTS = frozenset({"single", "double", "triple", "home_run"})

# 計入打數（AB）的 PA 結果（安打 + 出局型 + 失誤/野選）；BB/HBP/犧牲不入。
AB_EVENTS = HIT_EVENTS | frozenset({
    "strikeout", "strikeout_double_play",
    "field_out", "force_out", "grounded_into_double_play",
    "double_play", "triple_play",
    "field_error", "fielders_choice", "fielders_choice_out",
    "batter_interference",
})

VALID_ZONES = tuple(range(1, 10)) + (11, 12, 13, 14)


def compute_zone_stats(pitches: list[dict]) -> dict[int, dict]:
    acc: dict[int, dict] = {}
    for p in pitches:
        zone = p.get("zone")
        if zone not in VALID_ZONES:
            continue
        cell = acc.setdefault(zone, {
            "n": 0, "swings": 0, "whiffs": 0, "ab": 0, "hits": 0,
        })
        cell["n"] += 1
        if is_swing(p):
            cell["swings"] += 1
        if is_whiff(p):
            cell["whiffs"] += 1
        event = p.get("pa_event") or ""
        if p.get("is_pa_final") and event and event not in NON_PA_EVENTS:
            if event in AB_EVENTS:
                cell["ab"] += 1
                if event in HIT_EVENTS:
                    cell["hits"] += 1
    for cell in acc.values():
        cell["swing_pct"] = ratio(cell["swings"], cell["n"], digits=6)
        cell["whiff_pct"] = ratio(cell["whiffs"], cell["swings"], digits=6)
        cell["avg"] = ratio(cell["hits"], cell["ab"], digits=3)
    return acc
```

- [ ] **Step 4: 跑測試通過**

Run: `python -m pytest tests/test_zone_stats.py -v` → 3 PASS

- [ ] **Step 5: Commit**

```bash
git add site_builder/stats/recent/zone_stats.py tests/test_zone_stats.py
git commit -m "feat: per-zone hot-zone statistics (avg/swing/whiff by strike-zone cell)"
```

---

## Phase 3 — 圖表渲染器（每個 render_* 回傳 bool；False = 資料不足未產圖）

### Task 5: `charts/plate.py`（本壘板視角逐球位置圖）

**Files:**
- Create: `site_builder/charts/plate.py`
- Test: `tests/test_charts.py`（追加）

**Interfaces:**
- Produces：`render_game_pitch_map(pitches: list[dict], out_path: Path, *, title: str = "") -> bool`。投手、打者共用（打者場合傳入其所見球）。
- Consumes：`charts.style` 全部；`stats.recent.derived.DEFAULT_SZ_TOP/DEFAULT_SZ_BOT/PLATE_HALF_WIDTH_FT`。
- 視覺規格：x=`px`（捕手視角，原生座標即捕手方向）、y=`pz`；好球帶框＋三等分細線＋本壘板五邊形定向；色=球種、形=result class；PA 終結且 in-play 的球旁標 `PA_EVENT_ABBREV`；雙圖例（球種含球數、結果形狀）。

- [ ] **Step 1: 寫失敗測試（追加到 `tests/test_charts.py`）**

```python
from site_builder.charts.plate import render_game_pitch_map
from tests.recent_fixtures import make_pitch, make_untracked_pitch


def _game_pitches():
    return [
        make_pitch(px=-0.5, pz=2.8),
        make_pitch(px=0.3, pz=2.1, result_code="S"),
        make_pitch(px=0.9, pz=1.5, pitch_type="SL", result_code="F"),
        make_pitch(px=-1.2, pz=3.6, pitch_type="CH", result_code="B",
                   is_strike=False, is_ball=True),
        make_pitch(px=0.1, pz=2.4, result_code="E", is_in_play=True,
                   is_pa_final=True, pa_event="home_run", ev=105.0, la=28.0,
                   trajectory="fly_ball", hit_coord_x=140.0, hit_coord_y=60.0,
                   hit_distance=410, hardness="hard"),
    ]


def test_render_game_pitch_map(tmp_path):
    out = tmp_path / "pitchmap.png"
    assert render_game_pitch_map(_game_pitches(), out, title="07/06 vs BUF") is True
    assert out.is_file() and out.stat().st_size > 5000


def test_render_game_pitch_map_untracked_returns_false(tmp_path):
    out = tmp_path / "no.png"
    assert render_game_pitch_map([make_untracked_pitch()], out) is False
    assert not out.exists()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_charts.py -v` → 新增 2 案 FAIL（import error）

- [ ] **Step 3: 實作**

`site_builder/charts/plate.py`：

```python
"""本壘板視角（捕手方向）逐球位置圖。"""

from collections import Counter
from pathlib import Path

from matplotlib.lines import Line2D
from matplotlib.patches import Polygon, Rectangle

from ..stats.recent.derived import (
    DEFAULT_SZ_BOT,
    DEFAULT_SZ_TOP,
    PLATE_HALF_WIDTH_FT,
)
from ..util.numbers import float_or_none, mean
from .style import (
    GRID,
    INK_2,
    INK_3,
    PA_EVENT_ABBREV,
    RESULT_MARKERS,
    SURFACE,
    new_fig,
    pitch_color,
    result_class,
    save_chart,
    styled_legend,
)


def _zone_bounds(pitches):
    top = mean([float_or_none(p.get("strike_zone_top")) for p in pitches])
    bot = mean([float_or_none(p.get("strike_zone_bottom")) for p in pitches])
    return top or DEFAULT_SZ_TOP, bot or DEFAULT_SZ_BOT


def draw_strike_zone(ax, top: float, bot: float):
    half = PLATE_HALF_WIDTH_FT
    ax.add_patch(Rectangle((-half, bot), 2 * half, top - bot,
                           fill=False, edgecolor=INK_2, linewidth=1.4, zorder=2))
    for frac in (1 / 3, 2 / 3):
        x = -half + frac * 2 * half
        ax.plot([x, x], [bot, top], color=GRID, lw=0.8, zorder=1)
        y = bot + frac * (top - bot)
        ax.plot([-half, half], [y, y], color=GRID, lw=0.8, zorder=1)
    # 本壘板五邊形（尖端朝下＝朝捕手，定向用）
    plate = [(-half, 0.42), (half, 0.42), (half, 0.28), (0.0, 0.1), (-half, 0.28)]
    ax.add_patch(Polygon(plate, closed=True, facecolor=GRID,
                         edgecolor=INK_3, linewidth=0.8, zorder=1))


def render_game_pitch_map(pitches, out_path: Path, *, title: str = "") -> bool:
    pts = [
        p for p in pitches
        if float_or_none(p.get("px")) is not None
        and float_or_none(p.get("pz")) is not None
    ]
    if not pts:
        return False
    top, bot = _zone_bounds(pts)

    fig, ax = new_fig(5.4, 6.0)
    ax.grid(False)
    draw_strike_zone(ax, top, bot)

    type_counts = Counter(p.get("pitch_type") or "UN" for p in pts)
    for p in pts:
        color = pitch_color(p.get("pitch_type"))
        cls = result_class(p)
        marker = next(m for c, m, _ in RESULT_MARKERS if c == cls)
        if cls == "ball":
            ax.scatter(p["px"], p["pz"], marker=marker, s=52,
                       facecolors="none", edgecolors=color,
                       linewidths=1.2, zorder=3)
        else:
            ax.scatter(p["px"], p["pz"], marker=marker, s=58,
                       color=color, edgecolors=SURFACE,
                       linewidths=0.7, zorder=3)
        if p.get("is_pa_final") and p.get("is_in_play"):
            label = PA_EVENT_ABBREV.get(p.get("pa_event") or "", "")
            if label:
                ax.annotate(label, (p["px"], p["pz"]),
                            xytext=(5, 5), textcoords="offset points",
                            fontsize=7, color=INK_2, zorder=4)

    if len(pts) < len(pitches):
        ax.text(0.02, 0.02, f"{len(pts)}/{len(pitches)} pitches tracked",
                transform=ax.transAxes, fontsize=7, color=INK_3)

    type_handles = [
        Line2D([], [], marker="o", linestyle="", color=pitch_color(t),
               label=f"{t} ({n})")
        for t, n in type_counts.most_common()
    ]
    result_handles = [
        Line2D([], [], marker=m, linestyle="", color=INK_2, label=lab)
        for _, m, lab in RESULT_MARKERS
    ]
    leg1 = styled_legend(ax, type_handles, "upper left")
    ax.add_artist(leg1)
    styled_legend(ax, result_handles, "upper right")

    ax.set_xlim(-2.2, 2.2)
    ax.set_ylim(0.0, 4.8)
    ax.set_aspect("equal")
    ax.set_xlabel("Horizontal (ft, catcher's view)")
    ax.set_ylabel("Height (ft)")
    if title:
        ax.set_title(title)
    save_chart(fig, out_path)
    return True
```

- [ ] **Step 4: 跑測試通過**

Run: `python -m pytest tests/test_charts.py -v` → 全 PASS

- [ ] **Step 5: Commit**

```bash
git add site_builder/charts/plate.py tests/test_charts.py
git commit -m "feat: catcher-view per-game pitch location chart"
```

---

### Task 6: `charts/zones.py`（熱區 heatmap：季底＋週疊點）

**Files:**
- Create: `site_builder/charts/zones.py`
- Test: `tests/test_charts.py`（追加）

**Interfaces:**
- Produces：`render_hot_zone(zone_stats: dict[int,dict], out_path: Path, *, metric: str = "avg", min_n: int = 5, vmin: float = 0.15, vmax: float = 0.40, overlay_points: list[tuple[float,float]]|None = None, title: str = "") -> bool`；`overlay_points_from_pitches(pitches: list[dict]) -> list[tuple[float,float]]`（px/pz → 格座標，0–3 為帶內）。
- Consumes：Task 4 `compute_zone_stats` 輸出、`charts.style`、`stats.recent.derived.normalized_location`。
- 遮罩規則見 §0.4.5；`metric="avg"` 分母鍵 `ab`、`"whiff_pct"` 用 `swings`、`"swing_pct"` 用 `n`。

- [ ] **Step 1: 寫失敗測試（追加到 `tests/test_charts.py`）**

```python
from site_builder.charts.zones import overlay_points_from_pitches, render_hot_zone


def _zone_stats():
    zs = {}
    for z in range(1, 10):
        zs[z] = {"n": 30, "swings": 15, "whiffs": 4, "ab": 10, "hits": 3,
                 "avg": 0.300, "swing_pct": 0.5, "whiff_pct": 0.267}
    zs[11] = {"n": 12, "swings": 4, "whiffs": 2, "ab": 2, "hits": 0,
              "avg": 0.0, "swing_pct": 0.333, "whiff_pct": 0.5}  # ab<5 → 遮罩
    return zs


def test_render_hot_zone(tmp_path):
    out = tmp_path / "zones.png"
    overlay = overlay_points_from_pitches([make_pitch(px=0.0, pz=2.5)])
    assert render_hot_zone(_zone_stats(), out, overlay_points=overlay,
                           title="Season AVG by zone") is True
    assert out.is_file() and out.stat().st_size > 5000
    assert len(overlay) == 1
    x, y = overlay[0]
    assert 1.0 < x < 2.0 and 1.0 < y < 2.0  # 正中＝中央格


def test_render_hot_zone_empty(tmp_path):
    assert render_hot_zone({}, tmp_path / "z.png") is False
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL（import error）

- [ ] **Step 3: 實作**

`site_builder/charts/zones.py`：

```python
"""好球帶熱區 heatmap（9 宮格 + 外側 11–14 L 形區）。

格座標系：帶內 3×3 佔 (0..3)×(0..3)，外側區延伸到 -1..4。
y 軸向上（zone 1 = 高內側在左上）。
"""

from pathlib import Path

from matplotlib.colors import Normalize
from matplotlib.patches import Polygon, Rectangle

from ..stats.recent.derived import normalized_location
from .style import (
    ACCENT,
    GRID,
    INK_1,
    INK_3,
    MASK_FILL,
    SEQ_CMAP,
    SURFACE,
    new_fig,
    save_chart,
)

# zone → (col, row)；row 0 在下（zone 7-8-9 為低位）
ZONE_CELLS = {
    1: (0, 2), 2: (1, 2), 3: (2, 2),
    4: (0, 1), 5: (1, 1), 6: (2, 1),
    7: (0, 0), 8: (1, 0), 9: (2, 0),
}
OUTER_POLYGONS = {
    11: [(-1, 4), (1.5, 4), (1.5, 3), (0, 3), (0, 1.5), (-1, 1.5)],
    12: [(4, 4), (1.5, 4), (1.5, 3), (3, 3), (3, 1.5), (4, 1.5)],
    13: [(-1, -1), (1.5, -1), (1.5, 0), (0, 0), (0, 1.5), (-1, 1.5)],
    14: [(4, -1), (1.5, -1), (1.5, 0), (3, 0), (3, 1.5), (4, 1.5)],
}
OUTER_LABEL_POS = {
    11: (-0.5, 3.5), 12: (3.5, 3.5), 13: (-0.5, -0.5), 14: (3.5, -0.5),
}
_DEN_KEY = {"avg": "ab", "whiff_pct": "swings", "swing_pct": "n"}


def _cell_ink(rgba) -> str:
    r, g, b = rgba[0], rgba[1], rgba[2]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#09090b" if lum > 0.5 else INK_1


def _fmt(metric: str, value: float) -> str:
    if metric == "avg":
        return f"{value:.3f}".lstrip("0")
    return f"{value * 100:.0f}%"


def overlay_points_from_pitches(pitches) -> list[tuple[float, float]]:
    pts = []
    for p in pitches:
        loc = normalized_location(p)
        if loc is None:
            continue
        # x_norm/z_norm ∈ [-1,1] 為帶內 → 映到 0..3；外側夾在 -0.95..3.95
        x = min(max((loc[0] + 1) * 1.5, -0.95), 3.95)
        y = min(max((loc[1] + 1) * 1.5, -0.95), 3.95)
        pts.append((x, y))
    return pts


def render_hot_zone(zone_stats, out_path: Path, *, metric: str = "avg",
                    min_n: int = 5, vmin: float = 0.15, vmax: float = 0.40,
                    overlay_points=None, title: str = "") -> bool:
    if not zone_stats:
        return False
    den_key = _DEN_KEY[metric]
    norm = Normalize(vmin=vmin, vmax=vmax, clip=True)

    fig, ax = new_fig(5.0, 5.4)
    ax.grid(False)

    def paint(zone, patch_xy_label):
        cell = zone_stats.get(zone)
        value = cell and cell.get(metric)
        den = (cell or {}).get(den_key, 0)
        if cell is None or value is None or den < min_n:
            face, text, ink = MASK_FILL, f"n={den}" if cell else "-", INK_3
        else:
            rgba = SEQ_CMAP(norm(value))
            face, text, ink = rgba, _fmt(metric, value), _cell_ink(rgba)
        patch_xy_label(face, text, ink)

    for zone, (col, row) in ZONE_CELLS.items():
        def _p(face, text, ink, col=col, row=row):
            ax.add_patch(Rectangle((col, row), 1, 1, facecolor=face,
                                   edgecolor=SURFACE, linewidth=2, zorder=2))
            ax.text(col + 0.5, row + 0.5, text, ha="center", va="center",
                    fontsize=9, color=ink, zorder=3)
        paint(zone, _p)

    for zone, poly in OUTER_POLYGONS.items():
        def _p(face, text, ink, poly=poly, zone=zone):
            ax.add_patch(Polygon(poly, closed=True, facecolor=face,
                                 edgecolor=SURFACE, linewidth=2, zorder=1))
            lx, ly = OUTER_LABEL_POS[zone]
            ax.text(lx, ly, text, ha="center", va="center",
                    fontsize=8, color=ink, zorder=3)
        paint(zone, _p)

    for x, y in overlay_points or []:
        ax.scatter(x, y, s=46, facecolors=ACCENT, edgecolors=SURFACE,
                   linewidths=1.0, zorder=4)

    ax.add_patch(Rectangle((0, 0), 3, 3, fill=False, edgecolor=GRID,
                           linewidth=1.2, zorder=3))
    ax.set_xlim(-1.05, 4.05)
    ax.set_ylim(-1.05, 4.05)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.text(1.5, -1.02, "Catcher's view", ha="center", va="top",
            fontsize=7, color=INK_3)
    if title:
        ax.set_title(title)
    save_chart(fig, out_path)
    return True
```

- [ ] **Step 4: 跑測試通過** → `python -m pytest tests/test_charts.py -v` 全 PASS

- [ ] **Step 5: Commit**

```bash
git add site_builder/charts/zones.py tests/test_charts.py
git commit -m "feat: strike-zone hot-zone heatmap with masking and overlay points"
```

---

### Task 7: `charts/velocity.py`（單場球速序列圖）

**Files:**
- Create: `site_builder/charts/velocity.py`
- Test: `tests/test_charts.py`（追加）

**Interfaces:**
- Produces：`render_velocity_sequence(pitches: list[dict], out_path: Path, *, season_arsenal: list[dict]|None = None, title: str = "") -> bool`。`season_arsenal` 為季 statcast 的 `pitch_arsenal`（元素含 `type`/`velo`）。
- 視覺：x=該場第幾球、y=`start_speed`；每球種折線＋散點（球種色）；換局處灰直線＋局號；季均速虛線（同球種色、alpha 0.6、右端標 `FF avg`，最多 4 條、只畫本場出現的球種）。tracked <3 球回傳 False。

- [ ] **Step 1: 寫失敗測試（追加）**

```python
from site_builder.charts.velocity import render_velocity_sequence


def test_render_velocity_sequence(tmp_path):
    pitches = (
        [make_pitch(start_speed=94 + i * 0.2, inning=1) for i in range(6)]
        + [make_pitch(pitch_type="SL", start_speed=85.0, inning=2) for _ in range(4)]
    )
    arsenal = [{"type": "FF", "velo": 94.8}, {"type": "SL", "velo": 84.9},
               {"type": "CH", "velo": 88.0}]  # CH 本場沒投 → 不畫線
    out = tmp_path / "velo.png"
    assert render_velocity_sequence(pitches, out, season_arsenal=arsenal) is True
    assert out.stat().st_size > 5000


def test_render_velocity_sequence_untracked(tmp_path):
    assert render_velocity_sequence(
        [make_untracked_pitch() for _ in range(10)], tmp_path / "v.png") is False
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

`site_builder/charts/velocity.py`：

```python
"""單場球速序列圖（逐球 start_speed，疊季均速基準線）。"""

from pathlib import Path

from matplotlib.lines import Line2D

from ..util.numbers import float_or_none
from .style import (
    BASELINE,
    INK_3,
    SURFACE,
    new_fig,
    pitch_color,
    save_chart,
    styled_legend,
)

MIN_TRACKED = 3


def render_velocity_sequence(pitches, out_path: Path, *,
                             season_arsenal=None, title: str = "") -> bool:
    seq = [
        (i + 1, p) for i, p in enumerate(pitches)
        if float_or_none(p.get("start_speed")) is not None
    ]
    if len(seq) < MIN_TRACKED:
        return False

    fig, ax = new_fig(6.6, 3.8)

    # 換局分隔線
    last_inning = None
    for i, p in enumerate(pitches, start=1):
        inning = p.get("inning")
        if inning is not None and inning != last_inning:
            if last_inning is not None:
                ax.axvline(i - 0.5, color=BASELINE, lw=0.8, zorder=1)
            ax.text(i, 1.015, f"INN {inning}", transform=ax.get_xaxis_transform(),
                    fontsize=6.5, color=INK_3, ha="left")
            last_inning = inning

    by_type: dict[str, list[tuple[int, float]]] = {}
    for n, p in seq:
        t = p.get("pitch_type") or "UN"
        by_type.setdefault(t, []).append((n, p["start_speed"]))

    handles = []
    for ptype, items in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        xs, ys = zip(*items)
        color = pitch_color(ptype)
        ax.plot(xs, ys, color=color, lw=1.1, alpha=0.5, zorder=2)
        ax.scatter(xs, ys, s=20, color=color, edgecolors=SURFACE,
                   linewidths=0.5, zorder=3)
        handles.append(Line2D([], [], marker="o", linestyle="-",
                              color=color, label=f"{ptype} ({len(items)})"))

    shown = 0
    for row in season_arsenal or []:
        ptype, velo = row.get("type"), float_or_none(row.get("velo"))
        if ptype not in by_type or velo is None or shown >= 4:
            continue
        ax.axhline(velo, color=pitch_color(ptype), ls="--", lw=1.0,
                   alpha=0.6, zorder=1)
        ax.annotate(f"{ptype} avg", xy=(1.0, velo), xycoords=("axes fraction", "data"),
                    xytext=(4, 0), textcoords="offset points",
                    fontsize=6.5, color=pitch_color(ptype), va="center")
        shown += 1

    if len(seq) < len(pitches):
        ax.text(0.02, 0.03, f"{len(seq)}/{len(pitches)} pitches tracked",
                transform=ax.transAxes, fontsize=7, color=INK_3)

    styled_legend(ax, handles, "lower left")
    ax.set_xlabel("Pitch # in game")
    ax.set_ylabel("Velocity (mph)")
    ax.set_xlim(0.5, len(pitches) + 0.5)
    if title:
        ax.set_title(title)
    save_chart(fig, out_path)
    return True
```

- [ ] **Step 4: 跑測試通過** → 全 PASS

- [ ] **Step 5: Commit**

```bash
git add site_builder/charts/velocity.py tests/test_charts.py
git commit -m "feat: per-game velocity sequence chart with season baselines"
```

---

### Task 8: `charts/movement_game.py`（單場位移疊圖，季 ghost）

**Files:**
- Create: `site_builder/charts/movement_game.py`
- Test: `tests/test_charts.py`（追加）

**Interfaces:**
- Produces：`render_game_movement(game_pitches: list[dict], season_pitches: list[dict], out_path: Path, *, title: str = "") -> bool`。
- 視覺：x=HB、y=IVB（inches）；季資料＝灰小點（alpha 0.3）＋每球種 2σ 虛線橢圓（球種色、需 ≥5 球）；本場＝實色點；0 軸十字線。本場無 hb/ivb 回傳 False。

- [ ] **Step 1: 寫失敗測試（追加）**

```python
from site_builder.charts.movement_game import render_game_movement


def test_render_game_movement(tmp_path):
    game = [make_pitch(hb=8 + i * 0.3, ivb=15 - i * 0.2) for i in range(5)]
    season = [make_pitch(hb=7 + (i % 7) * 0.5, ivb=14 + (i % 5) * 0.4)
              for i in range(40)]
    out = tmp_path / "move.png"
    assert render_game_movement(game, season, out) is True
    assert out.stat().st_size > 5000


def test_render_game_movement_no_data(tmp_path):
    assert render_game_movement([make_untracked_pitch()], [], tmp_path / "m.png") is False
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

`site_builder/charts/movement_game.py`：

```python
"""單場 HB/IVB 位移圖，疊本季分佈 ghost（灰點＋每球種 2σ 橢圓）。"""

import math
from pathlib import Path

from matplotlib.lines import Line2D
from matplotlib.patches import Ellipse

from ..util.numbers import float_or_none
from .style import (
    BASELINE,
    INK_3,
    SURFACE,
    new_fig,
    pitch_color,
    save_chart,
    styled_legend,
)

MIN_ELLIPSE_N = 5


def _movement_points(pitches):
    pts = []
    for p in pitches:
        hb, ivb = float_or_none(p.get("hb")), float_or_none(p.get("ivb"))
        if hb is not None and ivb is not None:
            pts.append((p.get("pitch_type") or "UN", hb, ivb))
    return pts


def _mean_std(values):
    n = len(values)
    m = sum(values) / n
    var = sum((v - m) ** 2 for v in values) / n
    return m, math.sqrt(var)


def render_game_movement(game_pitches, season_pitches, out_path: Path, *,
                         title: str = "") -> bool:
    game_pts = _movement_points(game_pitches)
    if not game_pts:
        return False
    season_pts = _movement_points(season_pitches)

    fig, ax = new_fig(5.6, 5.2)
    ax.axhline(0, color=BASELINE, lw=0.9, zorder=1)
    ax.axvline(0, color=BASELINE, lw=0.9, zorder=1)

    if season_pts:
        ax.scatter([x for _, x, _ in season_pts], [y for _, _, y in season_pts],
                   s=7, color=INK_3, alpha=0.3, linewidths=0, zorder=2)
        by_type: dict[str, list[tuple[float, float]]] = {}
        for t, x, y in season_pts:
            by_type.setdefault(t, []).append((x, y))
        for t, pts in by_type.items():
            if len(pts) < MIN_ELLIPSE_N:
                continue
            mx, sx = _mean_std([x for x, _ in pts])
            my, sy = _mean_std([y for _, y in pts])
            ax.add_patch(Ellipse((mx, my), width=4 * sx or 1.0,
                                 height=4 * sy or 1.0, fill=False,
                                 edgecolor=pitch_color(t), ls="--",
                                 lw=1.0, alpha=0.55, zorder=3))

    seen: dict[str, int] = {}
    for t, x, y in game_pts:
        ax.scatter(x, y, s=44, color=pitch_color(t), edgecolors=SURFACE,
                   linewidths=0.7, zorder=4)
        seen[t] = seen.get(t, 0) + 1

    handles = [
        Line2D([], [], marker="o", linestyle="", color=pitch_color(t),
               label=f"{t} ({n})")
        for t, n in sorted(seen.items(), key=lambda kv: -kv[1])
    ]
    if season_pts:
        handles.append(Line2D([], [], marker="o", linestyle="",
                              color=INK_3, alpha=0.5, label="Season"))
    styled_legend(ax, handles, "upper left")

    lim = max(25.0, *(abs(v) + 2 for _, x, y in game_pts for v in (x, y)))
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal")
    ax.set_xlabel("Horizontal break (in)")
    ax.set_ylabel("Induced vertical break (in)")
    if title:
        ax.set_title(title)
    save_chart(fig, out_path)
    return True
```

- [ ] **Step 4: 跑測試通過** → 全 PASS

- [ ] **Step 5: Commit**

```bash
git add site_builder/charts/movement_game.py tests/test_charts.py
git commit -m "feat: per-game movement chart with season ghost ellipses"
```

---

### Task 9: `charts/batted.py`（EV/LA、spray chart、Tier 3 替代圖）

**Files:**
- Create: `site_builder/charts/batted.py`
- Test: `tests/test_charts.py`（追加）

**Interfaces:**
- Produces：
  - `render_ev_la(game_pitches, season_pitches, out_path, *, title="") -> bool` — x=LA、y=EV；sweet-spot 帶（LA 8–32°）淡色底、hard-hit 線 EV=95 虛線；季 BBE 灰點；本場 BBE 大點（barrel 加 ACCENT 外圈，用既有 `stats.batted_ball.barrel.is_barrel` 判定——不得重複定義 barrel）。
  - `render_spray(game_pitches, season_pitches, out_path, *, title="") -> bool` — Gameday 座標轉換 `x'=hc_x−125.42, y'=198.27−hc_y`；45° 邊線＋距離弧線；色＝軌跡（`TRAJECTORY_COLORS`）；季灰點、本場實色。
  - `render_quality_fallback(week_pitches, season_pitches, out_path, *, title="") -> bool` — 1×2 面板：左 hardness 分佈%（soft/medium/hard）、右軌跡分佈%（GB/LD/FB/PU），各為「週 vs 季」成對長條（週=slot blue、季=灰框），條頂印值。
- Consumes：`constants.GAMEDAY_HOME_X/GAMEDAY_HOME_Y`、`constants.GB_TRAJECTORIES/LD_TRAJECTORIES/FB_TRAJECTORIES/PU_TRAJECTORIES`。

- [ ] **Step 1: 寫失敗測試（追加）**

```python
from site_builder.charts.batted import (
    render_ev_la,
    render_quality_fallback,
    render_spray,
)


def _bbe(ev, la, traj="fly_ball", hx=140.0, hy=60.0, hardness="hard"):
    return make_pitch(is_in_play=True, result_code="D", ev=ev, la=la,
                      trajectory=traj, hit_coord_x=hx, hit_coord_y=hy,
                      hardness=hardness, is_pa_final=True, pa_event="single")


def test_render_ev_la(tmp_path):
    game = [_bbe(103.0, 27.0), _bbe(88.0, 5.0, traj="ground_ball")]
    season = [_bbe(90 + i, 10 + i) for i in range(10)]
    out = tmp_path / "evla.png"
    assert render_ev_la(game, season, out) is True
    assert out.stat().st_size > 5000


def test_render_ev_la_no_bbe(tmp_path):
    assert render_ev_la([make_pitch()], [], tmp_path / "e.png") is False


def test_render_spray(tmp_path):
    game = [_bbe(95.0, 12.0, hx=100.0, hy=80.0)]
    out = tmp_path / "spray.png"
    assert render_spray(game, [], out) is True


def test_render_spray_tier3_hit_coords_still_work(tmp_path):
    # AA 球也有 hit_coord → spray 各層級可用
    p = make_untracked_pitch(is_in_play=True, hit_coord_x=110.0, hit_coord_y=90.0,
                             trajectory="line_drive")
    assert render_spray([p], [], tmp_path / "s.png") is True


def test_render_quality_fallback(tmp_path):
    week = [_bbe(None, None, hardness="hard"), _bbe(None, None, hardness="medium")]
    season = [_bbe(None, None, hardness="soft") for _ in range(6)]
    out = tmp_path / "quality.png"
    assert render_quality_fallback(week, season, out) is True
    assert render_quality_fallback([make_pitch()], season, tmp_path / "q2.png") is False
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

`site_builder/charts/batted.py`：

```python
"""擊球品質圖：EV/LA 散點、spray chart、Tier 3 hardness/軌跡替代圖。"""

import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from ..constants import (
    FB_TRAJECTORIES,
    GAMEDAY_HOME_X,
    GAMEDAY_HOME_Y,
    GB_TRAJECTORIES,
    LD_TRAJECTORIES,
    PU_TRAJECTORIES,
)
from ..stats.batted_ball.barrel import is_barrel
from ..util.numbers import float_or_none, ratio
from .style import (
    ACCENT,
    BASELINE,
    GRID,
    INK_1,
    INK_3,
    NEUTRAL,
    SLOT_BLUE,
    SURFACE,
    TRAJECTORY_COLORS,
    new_fig,
    save_chart,
    style_axes,
    styled_legend,
)

SWEET_SPOT_LA = (8, 32)
HARD_HIT_EV = 95.0


def _bbe_points(pitches):
    return [
        p for p in pitches
        if p.get("is_in_play")
        and float_or_none(p.get("ev")) is not None
        and float_or_none(p.get("la")) is not None
    ]


def _traj_bucket(traj: str):
    if traj in GB_TRAJECTORIES:
        return "gb"
    if traj in LD_TRAJECTORIES:
        return "ld"
    if traj in FB_TRAJECTORIES:
        return "fb"
    if traj in PU_TRAJECTORIES:
        return "pu"
    return None


def render_ev_la(game_pitches, season_pitches, out_path: Path, *,
                 title: str = "") -> bool:
    game = _bbe_points(game_pitches)
    if not game:
        return False
    season = _bbe_points(season_pitches)

    fig, ax = new_fig(5.8, 4.4)
    ax.axvspan(*SWEET_SPOT_LA, color=GRID, alpha=0.35, zorder=1)
    ax.text(sum(SWEET_SPOT_LA) / 2, 0.02, "sweet spot",
            transform=ax.get_xaxis_transform(), fontsize=6.5,
            color=INK_3, ha="center")
    ax.axhline(HARD_HIT_EV, color=BASELINE, ls="--", lw=0.9, zorder=1)
    ax.annotate("hard-hit 95", xy=(1.0, HARD_HIT_EV),
                xycoords=("axes fraction", "data"), xytext=(4, 0),
                textcoords="offset points", fontsize=6.5, color=INK_3,
                va="center")

    if season:
        ax.scatter([p["la"] for p in season], [p["ev"] for p in season],
                   s=10, color=INK_3, alpha=0.35, linewidths=0, zorder=2)
    for p in game:
        barrel = is_barrel(p.get("ev"), p.get("la"))
        ax.scatter(p["la"], p["ev"], s=52, color=SLOT_BLUE,
                   edgecolors=ACCENT if barrel else SURFACE,
                   linewidths=1.6 if barrel else 0.7, zorder=3)

    handles = [
        Line2D([], [], marker="o", linestyle="", color=SLOT_BLUE, label="This game"),
        Line2D([], [], marker="o", linestyle="", color=SLOT_BLUE,
               markeredgecolor=ACCENT, markeredgewidth=1.6, label="Barrel"),
    ]
    if season:
        handles.append(Line2D([], [], marker="o", linestyle="", color=INK_3,
                              alpha=0.5, label="Season"))
    styled_legend(ax, handles, "lower left")
    ax.set_xlim(-40, 70)
    ax.set_ylim(40, 120)
    ax.set_xlabel("Launch angle (deg)")
    ax.set_ylabel("Exit velocity (mph)")
    if title:
        ax.set_title(title)
    save_chart(fig, out_path)
    return True


def _spray_xy(p):
    hx = float_or_none(p.get("hit_coord_x"))
    hy = float_or_none(p.get("hit_coord_y"))
    if hx is None or hy is None:
        return None
    return hx - GAMEDAY_HOME_X, GAMEDAY_HOME_Y - hy


def render_spray(game_pitches, season_pitches, out_path: Path, *,
                 title: str = "") -> bool:
    game = [(p, _spray_xy(p)) for p in game_pitches if p.get("is_in_play")]
    game = [(p, xy) for p, xy in game if xy is not None]
    if not game:
        return False
    season_xy = [
        (p, _spray_xy(p)) for p in season_pitches if p.get("is_in_play")
    ]
    season_xy = [(p, xy) for p, xy in season_xy if xy is not None]

    fig, ax = new_fig(5.4, 5.0)
    ax.grid(False)
    # 邊線（45°）與距離弧
    for sign in (-1, 1):
        ax.plot([0, sign * 160 / math.sqrt(2)], [0, 160 / math.sqrt(2)],
                color=BASELINE, lw=1.0, zorder=1)
    theta = [math.radians(d) for d in range(45, 136)]
    for r in (60, 110, 160):
        ax.plot([r * math.cos(t) for t in theta],
                [r * math.sin(t) for t in theta],
                color=GRID, lw=0.7, zorder=1)

    if season_xy:
        ax.scatter([xy[0] for _, xy in season_xy], [xy[1] for _, xy in season_xy],
                   s=9, color=INK_3, alpha=0.3, linewidths=0, zorder=2)
    seen = set()
    for p, (x, y) in game:
        bucket = _traj_bucket(p.get("trajectory", "")) or "gb"
        seen.add(bucket)
        ax.scatter(x, y, s=48, color=TRAJECTORY_COLORS[bucket],
                   edgecolors=SURFACE, linewidths=0.7, zorder=3)

    handles = [
        Line2D([], [], marker="o", linestyle="",
               color=TRAJECTORY_COLORS[b], label=b.upper())
        for b in ("gb", "ld", "fb", "pu") if b in seen
    ]
    if season_xy:
        handles.append(Line2D([], [], marker="o", linestyle="", color=INK_3,
                              alpha=0.5, label="Season"))
    styled_legend(ax, handles, "upper right")
    ax.set_xlim(-170, 170)
    ax.set_ylim(-15, 185)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    if title:
        ax.set_title(title)
    save_chart(fig, out_path)
    return True


def _dist_pcts(pitches, keys, getter):
    counts = {k: 0 for k in keys}
    total = 0
    for p in pitches:
        if not p.get("is_in_play"):
            continue
        k = getter(p)
        if k in counts:
            counts[k] += 1
            total += 1
    if not total:
        return None
    return {k: (ratio(v, total, digits=3) or 0) for k, v in counts.items()}


def render_quality_fallback(week_pitches, season_pitches, out_path: Path, *,
                            title: str = "") -> bool:
    hard_keys = ("soft", "medium", "hard")
    traj_keys = ("gb", "ld", "fb", "pu")
    week_h = _dist_pcts(week_pitches, hard_keys, lambda p: p.get("hardness"))
    week_t = _dist_pcts(week_pitches, traj_keys,
                        lambda p: _traj_bucket(p.get("trajectory", "")))
    if week_h is None and week_t is None:
        return False
    season_h = _dist_pcts(season_pitches, hard_keys, lambda p: p.get("hardness"))
    season_t = _dist_pcts(season_pitches, traj_keys,
                          lambda p: _traj_bucket(p.get("trajectory", "")))

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.4), facecolor=SURFACE)
    panels = (
        (axes[0], "Contact quality (scorer)", hard_keys, week_h, season_h),
        (axes[1], "Batted-ball type", traj_keys, week_t, season_t),
    )
    for ax, subtitle, keys, week, season in panels:
        style_axes(ax)
        ax.grid(axis="x", visible=False)
        xs = range(len(keys))
        if week:
            ax.bar([x - 0.18 for x in xs], [week[k] * 100 for k in keys],
                   width=0.36, color=SLOT_BLUE, zorder=2, label="Week")
            for x, k in zip(xs, keys):
                ax.text(x - 0.18, week[k] * 100 + 1, f"{week[k] * 100:.0f}",
                        ha="center", fontsize=7, color=INK_1)
        if season:
            ax.bar([x + 0.18 for x in xs], [season[k] * 100 for k in keys],
                   width=0.36, facecolor="none", edgecolor=NEUTRAL,
                   linewidth=1.2, zorder=2, label="Season")
            for x, k in zip(xs, keys):
                ax.text(x + 0.18, season[k] * 100 + 1, f"{season[k] * 100:.0f}",
                        ha="center", fontsize=7, color=INK_3)
        ax.set_xticks(list(xs), [k.upper() for k in keys])
        ax.set_ylim(0, 100)
        ax.set_ylabel("% of BBE")
        ax.set_title(subtitle)
        ax.legend(fontsize=7, facecolor=SURFACE, edgecolor=GRID,
                  labelcolor=INK_3)
    if title:
        fig.suptitle(title, color=INK_1, fontsize=10)
    fig.tight_layout()
    save_chart(fig, out_path)
    return True
```

- [ ] **Step 4: 跑測試通過** → `python -m pytest tests/test_charts.py -v` 全 PASS

- [ ] **Step 5: Commit**

```bash
git add site_builder/charts/batted.py tests/test_charts.py
git commit -m "feat: EV/LA scatter, spray chart, and tier-3 quality fallback charts"
```

---

## Phase 4 — 週報告計算

### Task 10: `pitcher_report.py` ＋ `batter_report.py`（週值、週 vs 季 delta）

**Files:**
- Create: `site_builder/stats/recent/pitcher_report.py`
- Create: `site_builder/stats/recent/batter_report.py`
- Test: `tests/test_recent_reports.py`

**Interfaces:**
- Produces：
  - `build_pitcher_report(games: list[dict], season: dict) -> dict`、`build_batter_report(games: list[dict], season: dict) -> dict`。
  - `games` = Task 2 player-window 的 `games`（**同一 sport_level** 的子集，呼叫端先分組）；`season` = `{"statcast": dict, "pitches": list[dict]}`（該層級季值；可空 dict/空 list）。
  - 兩者回傳 dict 的共同鍵：`tier`（視窗最佳 tier，int）、`pitch_count`、`games`（每場加上 `summary` 字串）、`week`（週指標 dict）、`season_available`（bool）、`deltas`（dict）。
  - 投手獨有：`week.arsenal`（`compute_pitch_arsenal` 輸出）、`week.derived_by_type`、`week.f_strike_pct`、`week.edge_pct`、`week.attack_zones`、`deltas.arsenal`（每球種列，鍵見下方程式碼）、`deltas.discipline`、`scoring_events`。
  - 打者獨有：`week.batting_line`（AB/H/HR/RBI/BB/K/AVG 合計）、`week.k_pct/bb_pct`、`week.ev`（avg/max/hard_hit_pct/sweet_spot_pct/barrel_pct/bbe）、`week.hardness`、`deltas.discipline`、`group_splits`（速球/變化/慢速）、`two_strike`、`pa_timeline`。
- Consumes：`aggregate_pitches`、`discipline_metrics`、`batted_ball_metrics`、`compute_pitch_arsenal`、`compute_pa_outcome_totals`、`ip_to_outs/outs_to_ip`、Task 3/4 全部。
- delta 一律 `週值 − 季值`；百分率鍵以「小數」存（模板再乘 100）。

- [ ] **Step 1: 寫失敗測試**

`tests/test_recent_reports.py`：

```python
import pytest

from site_builder.stats.recent.batter_report import build_batter_report
from site_builder.stats.recent.pitcher_report import build_pitcher_report
from tests.recent_fixtures import make_pitch, make_untracked_pitch


def _pitcher_game(game_id=111, pitches=None):
    return {
        "date": None, "game_id": game_id, "opponent": "BUF", "is_home": True,
        "sport_level": "AAA", "tier": 1, "events": [],
        "stats": {"inningsPitched": "5.1", "earnedRuns": 1, "strikeOuts": 6,
                  "baseOnBalls": 2, "hits": 4, "numberOfPitches": 82},
        "pitches": pitches if pitches is not None else _pitcher_pitches(),
    }


def _pitcher_pitches():
    ps = [make_pitch(start_speed=95.5) for _ in range(8)]
    ps += [make_pitch(pitch_type="ST", pitch_name="Sweeper", start_speed=84.0,
                      result_code="S") for _ in range(4)]
    ps.append(make_pitch(
        result_code="E", is_in_play=True, is_pa_final=True, pa_event="single",
        pa_event_desc="Single", ev=98.0, la=12.0, trajectory="line_drive",
        runners=[{"is_scoring_event": True, "earned": True, "rbi": True,
                  "event": "Single", "end_base": "score"}],
    ))
    return ps


def _season_ctx():
    return {
        "statcast": {
            "pitch_arsenal": [
                {"type": "FF", "name": "Four-Seam Fastball", "count": 400,
                 "pct": 0.55, "velo": 94.2, "whiff_pct": 0.22,
                 "chase_pct": 0.28, "zone_pct": 0.52},
                {"type": "SL", "name": "Slider", "count": 290, "pct": 0.40,
                 "velo": 86.0, "whiff_pct": 0.35, "chase_pct": 0.33,
                 "zone_pct": 0.44},
            ],
            "whiff_pct": 0.25, "o_swing_pct": 0.30, "zone_pct": 0.50,
            "csw_pct": 0.29, "swstr_pct": 0.12, "z_contact_pct": 0.85,
            "avg_ev": 89.0, "hard_hit_pct": 0.40,
        },
        "pitches": [make_pitch(start_speed=94.0) for _ in range(30)],
    }


def test_pitcher_report_week_and_deltas():
    report = build_pitcher_report([_pitcher_game()], _season_ctx())
    assert report["tier"] == 1
    assert report["pitch_count"] == 13
    assert report["week"]["ip"] == 5.1
    assert report["games"][0]["summary"] == "5.1 IP, 1 ER, 6 K, 2 BB"
    assert report["season_available"] is True
    ff = next(r for r in report["deltas"]["arsenal"] if r["type"] == "FF")
    assert ff["velo_delta"] == pytest.approx(95.5 - 94.2, abs=0.01)
    assert ff["usage_delta"] is not None
    # ST 季 usage 為 0 → NEW 徽章
    st = next(r for r in report["deltas"]["arsenal"] if r["type"] == "ST")
    assert st["is_new"] is True
    assert len(report["scoring_events"]) == 1


def test_pitcher_report_no_season_baseline():
    report = build_pitcher_report([_pitcher_game()], {"statcast": {}, "pitches": []})
    assert report["season_available"] is False
    assert report["deltas"]["arsenal"] == []


def test_pitcher_report_tier3():
    g = _pitcher_game(pitches=[make_untracked_pitch(result_code="S") for _ in range(20)])
    report = build_pitcher_report([g], {"statcast": {}, "pitches": []})
    assert report["tier"] == 3
    assert report["week"]["arsenal"] == []


def _batter_game():
    ps = [
        make_pitch(pitcher_id=1, batter_id=2, result_code="B", is_strike=False,
                   is_ball=True, zone=12),
        make_pitch(pitcher_id=1, batter_id=2, result_code="S", zone=5,
                   pre_strikes=0),
        make_pitch(pitcher_id=1, batter_id=2, pitch_type="SL", zone=5,
                   pre_strikes=2, result_code="E", is_in_play=True,
                   is_pa_final=True, pa_event="double", pa_event_desc="Double",
                   ev=101.0, la=18.0, trajectory="line_drive",
                   hit_coord_x=180.0, hit_coord_y=90.0, hardness="hard",
                   inning=2),
    ]
    return {
        "date": None, "game_id": 222, "opponent": "SUG", "is_home": False,
        "sport_level": "AAA", "tier": 1, "events": [],
        "stats": {"atBats": 4, "hits": 2, "homeRuns": 0, "rbi": 1,
                  "baseOnBalls": 0, "strikeOuts": 1,
                  "summary": "2-4 | 2B, RBI"},
        "pitches": ps,
    }


def test_batter_report():
    season = {"statcast": {"o_swing_pct": 0.32, "whiff_pct": 0.26,
                           "z_contact_pct": 0.84, "swstr_pct": 0.11,
                           "zone_pct": 0.49, "avg_ev": 88.0,
                           "hard_hit_pct": 0.38},
              "pitches": [make_pitch() for _ in range(20)]}
    report = build_batter_report([_batter_game()], season)
    assert report["week"]["batting_line"]["ab"] == 4
    assert report["week"]["batting_line"]["avg"] == pytest.approx(0.5)
    assert report["week"]["ev"]["max_ev"] == pytest.approx(101.0)
    assert report["two_strike"]["pa"] == 1 and report["two_strike"]["hits"] == 1
    groups = {g["group"] for g in report["group_splits"]}
    assert {"fastball", "breaking"} <= groups
    assert len(report["pa_timeline"]) == 1
    pa = report["pa_timeline"][0]
    assert pa["result"] == "Double" and pa["inning"] == 2
    assert [t for t, _ in pa["sequence"]] == ["FF", "FF", "SL"]
```

- [ ] **Step 2: 跑測試確認失敗** → `python -m pytest tests/test_recent_reports.py -v` FAIL

- [ ] **Step 3: 實作 `pitcher_report.py`**

```python
"""投手週報告：週值 + 週 vs 季 delta（重用既有 stats/ 函式，不重算公式）。"""

from ...util.numbers import ratio, safe_float, safe_int
from ..core.innings import ip_to_outs, outs_to_ip
from ..core.pitches import aggregate_pitches, ensure_pre_strikes
from ..batted_ball import batted_ball_metrics
from ..discipline import discipline_metrics
from ..tables.arsenal import compute_pitch_arsenal
from .derived import (
    attack_zone_distribution,
    derived_by_pitch_type,
    edge_pct,
    f_strike_pct,
)

# NEW/棄用 徽章門檻（plan §0.6）
NEW_WEEK_USAGE = 0.03
NEW_WEEK_COUNT = 3
NEW_SEASON_USAGE = 0.02
DROP_SEASON_USAGE = 0.05
DROP_MIN_WEEK_PITCHES = 30

_DISCIPLINE_DELTA_KEYS = (
    "whiff_pct", "o_swing_pct", "zone_pct", "csw_pct", "swstr_pct",
    "z_contact_pct",
)
_BATTED_DELTA_KEYS = ("avg_ev", "hard_hit_pct")


def _delta(week, season, digits=3):
    if week is None or season is None:
        return None
    return round(week - season, digits)


def pitcher_game_summary(stats: dict) -> str:
    ip = stats.get("inningsPitched") or "0.0"
    er = safe_int(stats.get("earnedRuns"), 0)
    k = safe_int(stats.get("strikeOuts"), 0)
    bb = safe_int(stats.get("baseOnBalls"), 0)
    return f"{ip} IP, {er} ER, {k} K, {bb} BB"


def _sum_ip(games) -> float | None:
    outs = sum(
        ip_to_outs(safe_float(g["stats"].get("inningsPitched")))
        for g in games
    )
    return outs_to_ip(outs)


def collect_scoring_events(games) -> list[dict]:
    out = []
    for g in games:
        for p in g["pitches"]:
            if not p.get("is_pa_final"):
                continue
            for r in p.get("runners") or []:
                if r.get("is_scoring_event"):
                    out.append({
                        "date": g["date"],
                        "inning": p.get("inning"),
                        "event": p.get("pa_event_desc") or r.get("event") or "",
                        "earned": r.get("earned"),
                    })
    return out


def build_arsenal_deltas(week_arsenal, season_arsenal, week_total: int):
    if not season_arsenal and not week_arsenal:
        return []
    if not season_arsenal:
        return []
    season_by_type = {r.get("type"): r for r in season_arsenal}
    rows = []
    for w in week_arsenal or []:
        s = season_by_type.get(w["type"]) or {}
        s_pct = safe_float(s.get("pct")) or 0.0
        w_pct = safe_float(w.get("pct")) or 0.0
        rows.append({
            "type": w["type"], "name": w.get("name") or w["type"],
            "count": w["count"],
            "week_pct": w_pct, "season_pct": s_pct or None,
            "usage_delta": round(w_pct - s_pct, 3),
            "week_velo": w.get("velo"), "season_velo": s.get("velo"),
            "velo_delta": _delta(w.get("velo"), s.get("velo"), 1),
            "whiff_delta": _delta(w.get("whiff_pct"), s.get("whiff_pct")),
            "chase_delta": _delta(w.get("chase_pct"), s.get("chase_pct")),
            "zone_delta": _delta(w.get("zone_pct"), s.get("zone_pct")),
            "is_new": (
                w_pct >= NEW_WEEK_USAGE
                and w["count"] >= NEW_WEEK_COUNT
                and s_pct < NEW_SEASON_USAGE
            ),
            "is_dropped": False,
        })
    if week_total >= DROP_MIN_WEEK_PITCHES:
        week_types = {r["type"] for r in rows}
        for s in season_arsenal:
            s_pct = safe_float(s.get("pct")) or 0.0
            if s.get("type") not in week_types and s_pct >= DROP_SEASON_USAGE:
                rows.append({
                    "type": s["type"], "name": s.get("name") or s["type"],
                    "count": 0, "week_pct": 0.0, "season_pct": s_pct,
                    "usage_delta": round(-s_pct, 3),
                    "week_velo": None, "season_velo": s.get("velo"),
                    "velo_delta": None, "whiff_delta": None,
                    "chase_delta": None, "zone_delta": None,
                    "is_new": False, "is_dropped": True,
                })
    rows.sort(key=lambda r: -(r["week_pct"] or 0))
    return rows


def _metric_deltas(week_metrics: dict, season_sc: dict, keys) -> dict:
    out = {}
    for key in keys:
        out[key] = {
            "week": week_metrics.get(key),
            "season": safe_float(season_sc.get(key)),
            "delta": _delta(week_metrics.get(key), safe_float(season_sc.get(key))),
        }
    return out


def build_pitcher_report(games: list[dict], season: dict) -> dict:
    season_sc = season.get("statcast") or {}
    week_pitches = [p for g in games for p in g["pitches"]]
    ensure_pre_strikes(week_pitches)

    for g in games:
        g["summary"] = pitcher_game_summary(g["stats"])

    week: dict = {
        "ip": _sum_ip(games),
        "er": sum(safe_int(g["stats"].get("earnedRuns"), 0) for g in games),
        "k": sum(safe_int(g["stats"].get("strikeOuts"), 0) for g in games),
        "bb": sum(safe_int(g["stats"].get("baseOnBalls"), 0) for g in games),
        "hits": sum(safe_int(g["stats"].get("hits"), 0) for g in games),
        "pickoffs": sum(
            1 for g in games for e in (g.get("events") or [])
            if e.get("type") == "pickoff"
        ),
        "arsenal": [],
        "derived_by_type": {},
    }
    metrics: dict = {}
    if week_pitches:
        agg = aggregate_pitches(week_pitches)
        metrics.update(discipline_metrics(agg))
        metrics.update(batted_ball_metrics(agg))
        week["arsenal"] = compute_pitch_arsenal(week_pitches)
        week["derived_by_type"] = derived_by_pitch_type(week_pitches)
        week["f_strike_pct"] = f_strike_pct(week_pitches)
        week["edge_pct"] = edge_pct(week_pitches)
        week["attack_zones"] = attack_zone_distribution(week_pitches)
        week.update(metrics)

    season_available = bool(season_sc)
    return {
        "tier": min((g["tier"] for g in games), default=3),
        "pitch_count": len(week_pitches),
        "games": games,
        "week": week,
        "season_available": season_available,
        "deltas": {
            "arsenal": build_arsenal_deltas(
                week["arsenal"], season_sc.get("pitch_arsenal"),
                len(week_pitches),
            ) if season_available else [],
            "discipline": _metric_deltas(
                metrics, season_sc,
                _DISCIPLINE_DELTA_KEYS + _BATTED_DELTA_KEYS,
            ) if season_available else {},
        },
        "scoring_events": collect_scoring_events(games),
    }
```

- [ ] **Step 4: 實作 `batter_report.py`**

```python
"""打者週報告：週值 + 週 vs 季 delta。"""

from ...util.numbers import mean_round, ratio, safe_int
from ..batted_ball import batted_ball_metrics
from ..batted_ball.exit_velocity import compute_ev90, compute_max_ev
from ..batted_ball.launch_angle import compute_avg_la
from ..batted_ball.sweet_spot import compute_sweet_spot_pct
from ..core.pitches import aggregate_pitches, ensure_pre_strikes, is_swing, is_whiff
from ..discipline import discipline_metrics
from .pitcher_report import _delta, _metric_deltas
from .zone_stats import AB_EVENTS, HIT_EVENTS

FASTBALLS = frozenset({"FF", "FA", "SI", "FT", "FC"})
BREAKING = frozenset({"SL", "ST", "SV", "CU", "KC", "CS", "KN", "EP"})
OFFSPEED = frozenset({"CH", "FS", "FO", "SC"})
GROUP_LABELS = (("fastball", "速球"), ("breaking", "變化球"), ("offspeed", "慢速球"))

_DISCIPLINE_DELTA_KEYS = (
    "o_swing_pct", "whiff_pct", "z_contact_pct", "swstr_pct", "zone_pct",
)
_QUALITY_DELTA_KEYS = ("avg_ev", "hard_hit_pct")


def pitch_group(ptype) -> str | None:
    if ptype in FASTBALLS:
        return "fastball"
    if ptype in BREAKING:
        return "breaking"
    if ptype in OFFSPEED:
        return "offspeed"
    return None


def _batting_line(games) -> dict:
    line = {key: 0 for key in ("ab", "hits", "hr", "rbi", "bb", "k")}
    src = (("ab", "atBats"), ("hits", "hits"), ("hr", "homeRuns"),
           ("rbi", "rbi"), ("bb", "baseOnBalls"), ("k", "strikeOuts"))
    for g in games:
        for dst_key, stat_key in src:
            line[dst_key] += safe_int(g["stats"].get(stat_key), 0)
    line["avg"] = ratio(line["hits"], line["ab"])
    return line


def batter_game_summary(stats: dict) -> str:
    if stats.get("summary"):
        return stats["summary"]
    ab = safe_int(stats.get("atBats"), 0)
    hits = safe_int(stats.get("hits"), 0)
    return f"{hits}-{ab}"


def group_splits(pitches) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for p in pitches:
        grp = pitch_group(p.get("pitch_type"))
        if grp:
            buckets.setdefault(grp, []).append(p)
    out = []
    for grp, _label in GROUP_LABELS:
        ps = buckets.get(grp)
        if not ps:
            continue
        swings = [p for p in ps if is_swing(p)]
        finals = [p for p in ps if p.get("is_pa_final")]
        ab = sum(1 for p in finals if (p.get("pa_event") or "") in AB_EVENTS)
        hits = sum(1 for p in finals if (p.get("pa_event") or "") in HIT_EVENTS)
        out.append({
            "group": grp,
            "n": len(ps),
            "whiff_pct": ratio(sum(1 for p in swings if is_whiff(p)),
                               len(swings), digits=6),
            "ab": ab, "hits": hits, "avg": ratio(hits, ab),
            "avg_ev": mean_round(
                [p.get("ev") for p in ps if p.get("is_in_play")], 1),
        })
    return out


def two_strike_summary(pitches) -> dict:
    finals = [
        p for p in pitches
        if p.get("is_pa_final") and p.get("pre_strikes") == 2
        and (p.get("pa_event") or "") not in ("",)
    ]
    ab = [p for p in finals if p["pa_event"] in AB_EVENTS]
    hits = [p for p in ab if p["pa_event"] in HIT_EVENTS]
    return {
        "pa": len(finals),
        "k": sum(1 for p in finals
                 if p["pa_event"] in ("strikeout", "strikeout_double_play")),
        "hits": len(hits),
        "avg": ratio(len(hits), len(ab)),
    }


def hardness_distribution(pitches) -> dict | None:
    counts = {"soft": 0, "medium": 0, "hard": 0}
    total = 0
    for p in pitches:
        h = p.get("hardness")
        if p.get("is_in_play") and h in counts:
            counts[h] += 1
            total += 1
    if not total:
        return None
    out = {k: ratio(v, total, digits=3) for k, v in counts.items()}
    out["n"] = total
    return out


def pa_timeline(games) -> list[dict]:
    out = []
    for g in games:
        seq: list[tuple[str, str]] = []
        for p in g["pitches"]:
            seq.append((p.get("pitch_type") or "?", p.get("result_code") or ""))
            if p.get("is_pa_final"):
                entry = {
                    "date": g["date"],
                    "opponent": g["opponent"],
                    "inning": p.get("inning"),
                    "pitch_hand": p.get("pitch_hand") or "",
                    "sequence": seq,
                    "result": p.get("pa_event_desc") or p.get("pa_event") or "",
                    "hit": None,
                }
                if p.get("is_in_play"):
                    entry["hit"] = {"ev": p.get("ev"), "la": p.get("la"),
                                    "distance": p.get("hit_distance")}
                out.append(entry)
                seq = []
    return out


def build_batter_report(games: list[dict], season: dict) -> dict:
    season_sc = season.get("statcast") or {}
    week_pitches = [p for g in games for p in g["pitches"]]
    ensure_pre_strikes(week_pitches)

    for g in games:
        g["summary"] = batter_game_summary(g["stats"])

    line = _batting_line(games)
    week: dict = {"batting_line": line}
    metrics: dict = {}
    if week_pitches:
        agg = aggregate_pitches(week_pitches)
        metrics.update(discipline_metrics(agg))
        metrics.update(batted_ball_metrics(agg))
        week.update(metrics)
        finals = agg["pa_final"]
        pa = len(finals) or None
        week["k_pct"] = ratio(line["k"], pa) if pa else None
        week["bb_pct"] = ratio(line["bb"], pa) if pa else None
        la_values = [p["la"] for p in agg["in_play"] if p.get("la") is not None]
        week["ev"] = {
            "avg_ev": metrics.get("avg_ev"),
            "max_ev": compute_max_ev(agg["bbe_ev"]),
            "ev90": compute_ev90(agg["bbe_ev"]),
            "avg_la": compute_avg_la(la_values),
            "sweet_spot_pct": compute_sweet_spot_pct(la_values),
            "hard_hit_pct": metrics.get("hard_hit_pct"),
            "barrel_pct": metrics.get("barrel_pct"),
            "bbe": metrics.get("bbe"),
            # MLB withMetrics 新欄位；MiLB 無資料時為 None
            "bat_speed": mean_round(
                [p.get("bat_speed") for p in week_pitches], 1),
        }
        week["hardness"] = hardness_distribution(week_pitches)

    season_available = bool(season_sc)
    return {
        "tier": min((g["tier"] for g in games), default=3),
        "pitch_count": len(week_pitches),
        "games": games,
        "week": week,
        "season_available": season_available,
        "deltas": {
            "discipline": _metric_deltas(
                metrics, season_sc,
                _DISCIPLINE_DELTA_KEYS + _QUALITY_DELTA_KEYS,
            ) if season_available else {},
        },
        "group_splits": group_splits(week_pitches),
        "two_strike": two_strike_summary(week_pitches),
        "pa_timeline": pa_timeline(games),
    }
```

- [ ] **Step 5: 跑測試通過** → `python -m pytest tests/test_recent_reports.py -v` 5 PASS

- [ ] **Step 6: Commit**

```bash
git add site_builder/stats/recent/pitcher_report.py site_builder/stats/recent/batter_report.py tests/test_recent_reports.py
git commit -m "feat: weekly pitcher/batter reports with week-vs-season deltas"
```

---

### Task 11: `highlights.py`（delta chips ＋ 規則式重點摘要）

**Files:**
- Create: `site_builder/stats/recent/highlights.py`
- Test: `tests/test_highlights.py`

**Interfaces:**
- Produces：`build_chips(report: dict, role: str) -> list[dict]`（role ∈ "pitcher"/"batter"；chip 結構 `{"label": str, "value_str": str, "delta_str": str, "cls": "up"|"down", "good": bool}`，依 |delta|/門檻比排序）；`build_notes(report: dict, role: str) -> list[str]`（最多 4 條中文句）。
- 門檻常數即 plan §0.6 表，全部定義在本模組頂部。

- [ ] **Step 1: 寫失敗測試**

`tests/test_highlights.py`：

```python
from site_builder.stats.recent.highlights import build_chips, build_notes


def _pitcher_report():
    return {
        "pitch_count": 80,
        "week": {"whiff_pct": 0.30, "o_swing_pct": 0.33, "zone_pct": 0.50,
                 "csw_pct": 0.33, "swstr_pct": 0.13, "z_contact_pct": 0.82,
                 "avg_ev": 86.0, "hard_hit_pct": 0.30, "bbe": 12,
                 "f_strike_pct": 0.70,
                 "swings": None},
        "season_available": True,
        "deltas": {
            "arsenal": [
                {"type": "FF", "name": "Four-Seam Fastball", "count": 40,
                 "week_pct": 0.5, "season_pct": 0.55, "usage_delta": -0.05,
                 "week_velo": 95.6, "season_velo": 94.2, "velo_delta": 1.4,
                 "whiff_delta": 0.02, "chase_delta": None, "zone_delta": None,
                 "is_new": False, "is_dropped": False},
                {"type": "ST", "name": "Sweeper", "count": 12,
                 "week_pct": 0.15, "season_pct": None, "usage_delta": 0.15,
                 "week_velo": 84.0, "season_velo": None, "velo_delta": None,
                 "whiff_delta": None, "chase_delta": None, "zone_delta": None,
                 "is_new": True, "is_dropped": False},
            ],
            "discipline": {
                "whiff_pct": {"week": 0.30, "season": 0.25, "delta": 0.05},
                "o_swing_pct": {"week": 0.33, "season": 0.30, "delta": 0.03},
                "zone_pct": {"week": 0.50, "season": 0.50, "delta": 0.0},
                "csw_pct": {"week": 0.33, "season": 0.29, "delta": 0.04},
                "swstr_pct": {"week": 0.13, "season": 0.12, "delta": 0.01},
                "z_contact_pct": {"week": 0.82, "season": 0.85, "delta": -0.03},
                "avg_ev": {"week": 86.0, "season": 89.0, "delta": -3.0},
                "hard_hit_pct": {"week": 0.30, "season": 0.40, "delta": -0.10},
            },
        },
    }


def test_pitcher_chips_and_notes():
    report = _pitcher_report()
    chips = build_chips(report, "pitcher")
    labels = [c["label"] for c in chips]
    assert "FF 均速" in labels
    velo_chip = chips[labels.index("FF 均速")]
    assert velo_chip["cls"] == "up" and velo_chip["good"] is True
    assert velo_chip["delta_str"] == "+1.4 mph"
    # 被打 EV 下降對投手是好事
    ev_chip = next(c for c in chips if c["label"] == "被打 EV")
    assert ev_chip["cls"] == "down" and ev_chip["good"] is True

    notes = build_notes(report, "pitcher")
    assert 1 <= len(notes) <= 4
    assert any("新球種" in n and "Sweeper" in n for n in notes)


def test_small_sample_suppresses_chips():
    report = _pitcher_report()
    report["pitch_count"] = 10  # < usage 門檻 30
    report["deltas"]["arsenal"][0]["count"] = 3  # < velo 門檻 5
    chips = build_chips(report, "pitcher")
    assert all(c["label"] != "FF 均速" for c in chips)


def test_batter_direction_sense():
    report = {
        "pitch_count": 60,
        "week": {"bbe": 8},
        "season_available": True,
        "deltas": {"discipline": {
            "o_swing_pct": {"week": 0.25, "season": 0.32, "delta": -0.07},
            "whiff_pct": {"week": 0.20, "season": 0.26, "delta": -0.06},
            "z_contact_pct": {"week": 0.90, "season": 0.84, "delta": 0.06},
            "swstr_pct": {"week": 0.08, "season": 0.11, "delta": -0.03},
            "zone_pct": {"week": 0.49, "season": 0.49, "delta": 0.0},
            "avg_ev": {"week": 91.0, "season": 88.0, "delta": 3.0},
            "hard_hit_pct": {"week": 0.50, "season": 0.38, "delta": 0.12},
        }},
    }
    chips = build_chips(report, "batter")
    chase = next(c for c in chips if c["label"] == "Chase%")
    assert chase["cls"] == "down" and chase["good"] is True
    ev = next(c for c in chips if c["label"] == "平均 EV")
    assert ev["cls"] == "up" and ev["good"] is True


def test_no_baseline_no_chips():
    assert build_chips({"season_available": False, "deltas": {}}, "pitcher") == []
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

`site_builder/stats/recent/highlights.py`：

```python
"""規則式 delta chips 與中文重點摘要（門檻見 plan §0.6）。"""

# ── 門檻 ──
VELO_THRESHOLD = 0.5          # mph
VELO_MIN_COUNT = 5            # 該球種週球數
USAGE_THRESHOLD = 0.05        # 5pp
USAGE_MIN_PITCHES = 30        # 週總球數
RATE_THRESHOLD = 0.03         # whiff/chase/zone/csw 3pp
RATE_MIN_DEN = 20
EV_THRESHOLD = 2.0            # mph
EV_MIN_BBE = 5
HARD_HIT_THRESHOLD = 0.08
FSTRIKE_THRESHOLD = 0.05
MAX_NOTES = 4

# (delta 鍵, 中文標籤, 單位, 門檻, 投手方向好?, 打者方向好?)
# 方向好? = delta 為「正」時是否為好事；None = 中性。
_RATE_SPECS = (
    ("whiff_pct", "Whiff%", "pp", RATE_THRESHOLD, True, False),
    ("o_swing_pct", "Chase%", "pp", RATE_THRESHOLD, True, False),
    ("zone_pct", "Zone%", "pp", RATE_THRESHOLD, None, None),
    ("csw_pct", "CSW%", "pp", RATE_THRESHOLD, True, None),
    ("swstr_pct", "SwStr%", "pp", RATE_THRESHOLD, True, False),
    ("z_contact_pct", "Z-Contact%", "pp", RATE_THRESHOLD, False, True),
    ("avg_ev", None, "mph", EV_THRESHOLD, False, True),
    ("hard_hit_pct", None, "pp", HARD_HIT_THRESHOLD, False, True),
)
_EV_LABELS = {"pitcher": "被打 EV", "batter": "平均 EV"}
_HH_LABELS = {"pitcher": "被 Hard-Hit%", "batter": "Hard-Hit%"}


def _fmt_delta(delta: float, unit: str) -> str:
    if unit == "pp":
        return f"{delta * 100:+.0f}pp"
    return f"{delta:+.1f} {unit}"


def _fmt_value(value, unit: str) -> str:
    if value is None:
        return "-"
    if unit == "pp":
        return f"{value * 100:.0f}%"
    return f"{value:.1f}"


def _chip(label, week_value, delta, unit, positive_is_good):
    good = None if positive_is_good is None else (
        (delta > 0) == positive_is_good
    )
    return {
        "label": label,
        "value_str": _fmt_value(week_value, unit),
        "delta_str": _fmt_delta(delta, unit),
        "cls": "up" if delta > 0 else "down",
        "good": bool(good) if good is not None else True,
        "_score": abs(delta),
    }


def build_chips(report: dict, role: str) -> list[dict]:
    if not report.get("season_available"):
        return []
    deltas = report.get("deltas") or {}
    week = report.get("week") or {}
    pitch_count = report.get("pitch_count") or 0
    chips: list[dict] = []

    # 球種 velo / usage（投手才有 arsenal deltas）
    for row in deltas.get("arsenal") or []:
        vd = row.get("velo_delta")
        if vd is not None and abs(vd) >= VELO_THRESHOLD \
                and row.get("count", 0) >= VELO_MIN_COUNT:
            chips.append(_chip(f"{row['type']} 均速", row.get("week_velo"),
                               vd, "mph", True))
        ud = row.get("usage_delta")
        if ud is not None and abs(ud) >= USAGE_THRESHOLD \
                and pitch_count >= USAGE_MIN_PITCHES:
            chips.append(_chip(f"{row['type']} 使用率", row.get("week_pct"),
                               ud, "pp", None))

    # 率值
    bbe = week.get("bbe") or 0
    for key, label, unit, threshold, p_good, b_good in _RATE_SPECS:
        entry = (deltas.get("discipline") or {}).get(key)
        if not entry or entry.get("delta") is None:
            continue
        delta = entry["delta"]
        if abs(delta) < threshold:
            continue
        if key in ("avg_ev", "hard_hit_pct"):
            if bbe < EV_MIN_BBE:
                continue
            label = (_EV_LABELS if key == "avg_ev" else _HH_LABELS)[role]
        elif pitch_count < RATE_MIN_DEN:
            continue
        positive_is_good = p_good if role == "pitcher" else b_good
        chips.append(_chip(label, entry.get("week"), delta, unit,
                           positive_is_good))

    chips.sort(key=lambda c: -c["_score"])
    for c in chips:
        c.pop("_score", None)
    return chips


def build_notes(report: dict, role: str) -> list[str]:
    notes: list[str] = []
    deltas = report.get("deltas") or {}
    for row in deltas.get("arsenal") or []:
        if row.get("is_new"):
            notes.append(f"新球種：{row['name']}（本週 {row['count']} 球）")
        elif row.get("is_dropped"):
            season_pct = (row.get("season_pct") or 0) * 100
            notes.append(f"棄用球種：{row['name']}（季使用率 {season_pct:.0f}%，本週 0 球）")
        elif row.get("usage_delta") is not None \
                and abs(row["usage_delta"]) >= USAGE_THRESHOLD \
                and row.get("season_pct"):
            notes.append(
                f"{row['name']} 使用率 {row['season_pct'] * 100:.0f}% → "
                f"{row['week_pct'] * 100:.0f}%"
            )
    for chip in build_chips(report, role):
        if len(notes) >= MAX_NOTES:
            break
        line = f"{chip['label']} {chip['value_str']}（{chip['delta_str']}）"
        if line not in notes:
            notes.append(line)
    return notes[:MAX_NOTES]
```

- [ ] **Step 4: 跑測試通過** → `python -m pytest tests/test_highlights.py -v` 5 PASS

- [ ] **Step 5: Commit**

```bash
git add site_builder/stats/recent/highlights.py tests/test_highlights.py
git commit -m "feat: rule-based delta chips and Chinese summary notes"
```

---

## Phase 5 — /recents 頁面

### Task 12: `render/recents.py` ＋ 模板 ＋ CSS（整合測試）

**Files:**
- Create: `site_builder/render/recents.py`
- Create: `src/templates/recents.j2`
- Create: `src/templates/macros/recents.j2`
- Create: `src/templates/partials/recent_pitcher_report.j2`
- Create: `src/templates/partials/recent_batter_report.j2`
- Create: `src/static/css/recents.css`
- Modify: `src/static/css/style.css`（`@import "charts.css";` 之後加一行 `@import "recents.css";`）
- Test: `tests/test_recents_render.py`

**Interfaces:**
- Produces：`build_recents_page(env, conn, out_dir: Path, year: int, roster_ids: set[int], *, today: date|None = None) -> dict` — 寫出 `recents/index.html` 與 `static/charts/recents/{mlb_id}/*.png`，回傳 sitemap entry `{"loc": str, "lastmod": str}`。
- Consumes：Task 2/10/11 全部、Task 5–9 的 `render_*`、`db.game_logs.load_all_pitches_for_player`、`env.globals["base_url"]/["absolute_url"]`。
- 報告 dict 由本模組再補上：`player`（window dict 去掉 games）、`level`、`chips`、`notes`、`game_charts: dict[game_id, dict[str, url]]`、打者另有 `zone_chart: str|None`、`quality_chart: str|None`、`zone_chart_missing_reason: str|None`。

- [ ] **Step 1: 寫失敗測試**

`tests/test_recents_render.py`：

```python
import datetime
import json
import sqlite3
from pathlib import Path

from site_builder.db.schema import init_db
from site_builder.render.env import create_jinja_env
from site_builder.render.recents import build_recents_page
from tests.recent_fixtures import make_pitch, make_untracked_pitch

TODAY = datetime.date(2026, 7, 9)


def _env():
    env = create_jinja_env(base_url="/")
    env.globals["build_time"] = "2026-07-09 00:00"
    return env


def _seed(conn):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO players (mlb_id, name_en, name_tw, team, level, position)"
        " VALUES (678906, 'Kai-Wei Teng', '鄧愷威', 'Sacramento River Cats', 'AAA', 'P')"
    )
    cur.execute(
        "INSERT INTO players (mlb_id, name_en, name_tw, team, level, position)"
        " VALUES (800018, 'Chung-Ao Chuang', '莊陳仲敖', 'Somerset Patriots', 'AA', 'C')"
    )
    pitcher_pitches = [make_pitch(start_speed=95.0) for _ in range(15)]
    pitcher_pitches.append(make_pitch(
        result_code="E", is_in_play=True, is_pa_final=True, pa_event="single",
        pa_event_desc="Single", ev=98.0, la=10.0, trajectory="line_drive"))
    cur.execute(
        "INSERT INTO game_logs (player_mlb_id, date, game_id, opponent, is_home,"
        " stats_json, pitches_json, events_json, sport_level) VALUES"
        " (678906, '2026-07-06', 111, 'BUF', 1,"
        "  '{\"inningsPitched\":\"5.0\",\"earnedRuns\":1,\"strikeOuts\":6,"
        "\"baseOnBalls\":2,\"hits\":4}', ?, '[]', 'AAA')",
        (json.dumps(pitcher_pitches),),
    )
    # AA 打者（Tier 3）＋ 一顆有落點的擊球
    batter_pitches = [make_untracked_pitch() for _ in range(8)]
    batter_pitches.append(make_untracked_pitch(
        is_in_play=True, result_code="E", is_pa_final=True, pa_event="double",
        pa_event_desc="Double", hit_coord_x=180.0, hit_coord_y=90.0,
        trajectory="line_drive", hardness="hard"))
    cur.execute(
        "INSERT INTO game_logs (player_mlb_id, date, game_id, opponent, is_home,"
        " stats_json, pitches_json, events_json, sport_level) VALUES"
        " (800018, '2026-07-07', 222, 'HFD', 0,"
        "  '{\"atBats\":4,\"hits\":2,\"summary\":\"2-4 | 2B\"}', ?, '[]', 'AA')",
        (json.dumps(batter_pitches),),
    )
    cur.execute(
        "INSERT INTO season_stats (player_mlb_id, year, team_name, sport_level,"
        " league_name, stat_json) VALUES (678906, 2026, 'Sacramento River Cats',"
        " 'AAA', 'PCL', ?)",
        (json.dumps({"statcast": {
            "pitch_arsenal": [{"type": "FF", "name": "Four-Seam Fastball",
                               "count": 300, "pct": 0.6, "velo": 94.0,
                               "whiff_pct": 0.2, "chase_pct": 0.3,
                               "zone_pct": 0.5}],
            "whiff_pct": 0.24, "o_swing_pct": 0.29, "zone_pct": 0.5,
            "csw_pct": 0.28, "swstr_pct": 0.11, "z_contact_pct": 0.86,
            "avg_ev": 88.0, "hard_hit_pct": 0.4,
        }}),),
    )
    conn.commit()


def test_build_recents_page(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)
    out = tmp_path / "dist"
    entry = build_recents_page(_env(), conn, out, 2026, {678906, 800018},
                               today=TODAY)
    html = (out / "recents" / "index.html").read_text(encoding="utf-8")
    assert "鄧愷威" in html and "莊陳仲敖" in html
    assert "5.0 IP, 1 ER, 6 K, 2 BB" in html
    assert "近 7 天無出賽紀錄" not in html
    # Tier 3 fallback 文案 + 結果條
    assert "無進壘點追蹤資料" in html
    assert "result-strip" in html
    # 投手圖有產出且被引用
    charts = list((out / "static" / "charts" / "recents" / "678906").glob("*.png"))
    assert charts
    assert "/static/charts/recents/678906/111-pitchmap.png" in html
    assert entry["loc"].endswith("recents/")


def test_build_recents_page_empty(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    out = tmp_path / "dist"
    build_recents_page(_env(), conn, out, 2026, {678906}, today=TODAY)
    html = (out / "recents" / "index.html").read_text(encoding="utf-8")
    assert "近 7 天無出賽紀錄" in html
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作 `site_builder/render/recents.py`**

```python
"""/recents 近期出賽分析頁：載視窗 → 組報告 → 產圖 → 渲染 HTML。"""

import datetime
from pathlib import Path

from ..charts.batted import render_ev_la, render_quality_fallback, render_spray
from ..charts.movement_game import render_game_movement
from ..charts.plate import render_game_pitch_map
from ..charts.velocity import render_velocity_sequence
from ..charts.zones import overlay_points_from_pitches, render_hot_zone
from ..db.game_logs import load_all_pitches_for_player
from ..stats.recent.batter_report import build_batter_report
from ..stats.recent.highlights import build_chips, build_notes
from ..stats.recent.pitcher_report import build_pitcher_report
from ..stats.recent.window import WINDOW_DAYS, load_recent_window
from ..stats.recent.zone_stats import compute_zone_stats
from ..util.json import loads_json_dict

RECENTS_SEO_TITLE = "近期出賽分析 | TwbExpats"
RECENTS_SEO_DESCRIPTION = (
    "台灣旅美棒球員近 7 天出賽週報告：球速、球種使用率、選球與擊球品質"
    "的本週 vs 球季變化，附本壘板視角逐球圖表。"
)


def _load_season_statcast(cur, mlb_id: int, year: int, level: str) -> dict:
    cur.execute(
        "SELECT stat_json FROM season_stats "
        "WHERE player_mlb_id = ? AND year = ? AND sport_level = ?",
        (mlb_id, year, level),
    )
    for row in cur.fetchall():
        sc = loads_json_dict(row[0]).get("statcast")
        if sc:
            return sc
    return {}


def _game_title(game, suffix: str) -> str:
    date_s = game["date"].strftime("%m/%d") if game["date"] else ""
    side = "vs" if game["is_home"] else "@"
    return f"{date_s} {side} {game['opponent']} - {suffix}"


def _pitcher_game_charts(game, season_pitches, season_arsenal, chart_dir, url_for):
    charts = {}
    gid = game["game_id"]
    if game["tier"] <= 2:
        name = f"{gid}-pitchmap.png"
        if render_game_pitch_map(game["pitches"], chart_dir / name,
                                 title=_game_title(game, "Pitch locations")):
            charts["pitch_map"] = url_for(name)
        name = f"{gid}-velocity.png"
        if render_velocity_sequence(game["pitches"], chart_dir / name,
                                    season_arsenal=season_arsenal,
                                    title=_game_title(game, "Velocity")):
            charts["velocity"] = url_for(name)
        name = f"{gid}-movement.png"
        if render_game_movement(game["pitches"], season_pitches,
                                chart_dir / name,
                                title=_game_title(game, "Movement")):
            charts["movement"] = url_for(name)
    return charts


def _batter_game_charts(game, season_pitches, chart_dir, url_for):
    charts = {}
    gid = game["game_id"]
    if game["tier"] <= 2:
        name = f"{gid}-pitchmap.png"
        if render_game_pitch_map(game["pitches"], chart_dir / name,
                                 title=_game_title(game, "Pitches seen")):
            charts["pitch_map"] = url_for(name)
        name = f"{gid}-evla.png"
        if render_ev_la(game["pitches"], season_pitches, chart_dir / name,
                        title=_game_title(game, "EV / LA")):
            charts["ev_la"] = url_for(name)
    # spray：hit_coord 各層級都有，Tier 3 也畫
    name = f"{gid}-spray.png"
    if render_spray(game["pitches"], season_pitches, chart_dir / name,
                    title=_game_title(game, "Spray chart")):
        charts["spray"] = url_for(name)
    return charts


def _build_report(cur, window, level, games, year, out_dir, base_url):
    mlb_id = window["mlb_id"]
    is_pitcher = window["is_pitcher"]
    season_pitches = load_all_pitches_for_player(cur, mlb_id).get(
        (year, level), [])
    season = {
        "statcast": _load_season_statcast(cur, mlb_id, year, level),
        "pitches": season_pitches,
    }
    role = "pitcher" if is_pitcher else "batter"
    if is_pitcher:
        report = build_pitcher_report(games, season)
    else:
        report = build_batter_report(games, season)
    report["player"] = {k: v for k, v in window.items() if k != "games"}
    report["level"] = level
    report["chips"] = build_chips(report, role)
    report["notes"] = build_notes(report, role)

    chart_dir = out_dir / "static" / "charts" / "recents" / str(mlb_id)

    def url_for(name: str) -> str:
        return f"{base_url}static/charts/recents/{mlb_id}/{name}"

    season_arsenal = (season["statcast"] or {}).get("pitch_arsenal")
    game_charts = {}
    for g in games:
        if is_pitcher:
            game_charts[g["game_id"]] = _pitcher_game_charts(
                g, season_pitches, season_arsenal, chart_dir, url_for)
        else:
            game_charts[g["game_id"]] = _batter_game_charts(
                g, season_pitches, chart_dir, url_for)
    report["game_charts"] = game_charts

    if not is_pitcher:
        report["zone_chart"] = None
        report["zone_chart_missing_reason"] = None
        zone_stats = compute_zone_stats(season_pitches)
        if zone_stats:
            week_finals = [p for g in games for p in g["pitches"]
                           if p.get("is_pa_final")]
            name = "season-zones.png"
            if render_hot_zone(
                    zone_stats, chart_dir / name,
                    overlay_points=overlay_points_from_pitches(week_finals),
                    title=f"{year} Season AVG by zone"):
                report["zone_chart"] = url_for(name)
        if report["zone_chart"] is None:
            report["zone_chart_missing_reason"] = (
                "此層級無進壘點追蹤資料，無法繪製熱區"
            )
        report["quality_chart"] = None
        if any(g["tier"] == 3 for g in games):
            week_pitches = [p for g in games for p in g["pitches"]]
            name = "week-quality.png"
            if render_quality_fallback(week_pitches, season_pitches,
                                       chart_dir / name,
                                       title="Contact quality - week vs season"):
                report["quality_chart"] = url_for(name)
    return report


def build_recents_page(env, conn, out_dir: Path, year: int,
                       roster_ids: set, *, today=None) -> dict:
    today = today or datetime.date.today()
    base_url = env.globals["base_url"]
    absolute_url = env.globals["absolute_url"]
    cur = conn.cursor()
    windows = load_recent_window(cur, roster_ids, today=today)

    pitcher_reports, batter_reports = [], []
    for window in windows:
        by_level: dict[str, list] = {}
        for g in window["games"]:
            by_level.setdefault(g["sport_level"], []).append(g)
        for level, games in by_level.items():
            report = _build_report(cur, window, level, games, year,
                                   out_dir, base_url)
            (pitcher_reports if window["is_pitcher"]
             else batter_reports).append(report)

    template = env.get_template("recents.j2")
    html = template.render(
        pitcher_reports=pitcher_reports,
        batter_reports=batter_reports,
        date_range={"start": today - datetime.timedelta(days=WINDOW_DAYS),
                    "end": today},
        season_year=year,
        nav_active="recents",
        seo_title=RECENTS_SEO_TITLE,
        seo_description=RECENTS_SEO_DESCRIPTION,
        canonical_url=absolute_url("recents/"),
        og_type="website",
    )
    recents_dir = out_dir / "recents"
    recents_dir.mkdir(parents=True, exist_ok=True)
    (recents_dir / "index.html").write_text(html, encoding="utf-8")
    return {"loc": absolute_url("recents/"), "lastmod": today.isoformat()}
```

- [ ] **Step 4: 實作模板**

`src/templates/macros/recents.j2`：

```jinja
{% import "macros/tags.j2" as tags %}

{% macro pp(v) %}{% if v is none %}-{% else %}{{ '%+.0f'|format(v * 100) }}pp{% endif %}{% endmacro %}
{% macro mph(v) %}{% if v is none %}-{% else %}{{ '%+.1f'|format(v) }}{% endif %}{% endmacro %}
{% macro pct(v) %}{% if v is none %}-{% else %}{{ (v * 100)|round(0)|int }}%{% endif %}{% endmacro %}

{% macro chips(chip_list, limit=None) %}
{% if chip_list %}
<div class="chip-row">
    {% for c in (chip_list[:limit] if limit else chip_list) %}
    <span class="delta-chip {{ 'chip-good' if c.good else 'chip-bad' }}">
        {{ c.label }} {{ '▲' if c.cls == 'up' else '▼' }} {{ c.delta_str }}
    </span>
    {% endfor %}
</div>
{% endif %}
{% endmacro %}

{% macro notes(note_list) %}
{% if note_list %}
<ul class="recent-notes">
    {% for n in note_list %}<li>{{ n }}</li>{% endfor %}
</ul>
{% endif %}
{% endmacro %}

{% macro card_header(r, season_year) %}
<div class="recent-card-summary">
    <div class="avatar">
        {% set cdn_primary, cdn_secondary = headshot_cdn_urls(r.player.mlb_id, r.level == 'MLB') %}
        <img data-src="{{ cdn_primary }}" data-cdn-src="{{ cdn_secondary }}"
             alt="{{ r.player.name_tw or r.player.name_en }}" class="avatar-img">
        <div class="avatar-initials avatar-fallback" aria-hidden="true">{{ r.player.name_en[:1] }}</div>
    </div>
    <div class="recent-card-info">
        <h3>{{ r.player.name_tw or r.player.name_en }}
            <span class="recent-name-en">{{ r.player.name_en }}</span>
            {{ tags.level_tag(r.level, season_year) }}</h3>
        <div class="recent-card-team">{{ r.player.team }}</div>
        <ul class="recent-card-games">
            {% for g in r.games %}
            <li>{{ g.date.strftime('%m/%d') if g.date else '' }}
                {{ '主' if g.is_home else '客' }} {{ g.opponent }} — {{ g.summary }}</li>
            {% endfor %}
        </ul>
    </div>
    <div class="recent-card-chips">{{ chips(r.chips, limit=2) }}</div>
</div>
{% endmacro %}

{% macro chart_grid(charts_map, captions) %}
{% if charts_map %}
<div class="recent-chart-grid">
    {% for key, url in charts_map.items() %}
    <figure class="recent-chart">
        <img src="{{ url }}" alt="{{ captions.get(key, key) }}" loading="lazy">
        <figcaption>{{ captions.get(key, key) }}</figcaption>
    </figure>
    {% endfor %}
</div>
{% endif %}
{% endmacro %}

{% macro result_strip(pitches) %}
<div class="result-strip" role="img" aria-label="逐球結果序列">
    {% for p in pitches %}
    {% set code = p.result_code or '' %}
    {% set cls = 'inplay' if p.is_in_play
        else ('whiff' if code in ('S', 'W', 'T', 'M', 'O', 'Q')
        else ('called' if code == 'C'
        else ('foul' if code in ('F', 'L', 'R') else 'ball'))) %}
    <span class="strip strip-{{ cls }}{% if p.pa_event %} strip-final{% endif %}"
          title="{{ p.result_desc or code }}"></span>
    {% endfor %}
</div>
<div class="strip-legend">
    <span><span class="strip strip-inplay"></span> 擊入場內</span>
    <span><span class="strip strip-whiff"></span> 揮空</span>
    <span><span class="strip strip-called"></span> 好球(看)</span>
    <span><span class="strip strip-foul"></span> 界外</span>
    <span><span class="strip strip-ball"></span> 壞球</span>
    <span><span class="strip strip-ball strip-final"></span> 打席終結球(外框)</span>
</div>
{% endmacro %}

{% macro fallback(text) %}<p class="fallback-note">{{ text }}</p>{% endmacro %}
```

`src/templates/recents.j2`：

```jinja
{% extends 'base.j2' %}

{% block content %}
<div class="recents-header glass-panel">
    <h2>近 7 天出賽動態（{{ date_range.start.strftime('%m/%d') }} – {{ date_range.end.strftime('%m/%d') }}）</h2>
    <p class="recents-subtitle">
        進階指標以「本週 vs 球季基準」的差異呈現；圖表與指標依各層級追蹤資料等級自動降階。
    </p>
</div>

{% if not pitcher_reports and not batter_reports %}
<div class="glass-panel empty-season-msg">近 7 天無出賽紀錄</div>
{% endif %}

{% if pitcher_reports %}
<h3 class="recents-section-title">投手</h3>
{% for r in pitcher_reports %}
{% include 'partials/recent_pitcher_report.j2' %}
{% endfor %}
{% endif %}

{% if batter_reports %}
<h3 class="recents-section-title">打者</h3>
{% for r in batter_reports %}
{% include 'partials/recent_batter_report.j2' %}
{% endfor %}
{% endif %}
{% endblock %}
```

`src/templates/partials/recent_pitcher_report.j2`：

```jinja
{% import "macros/recents.j2" as rc %}
<details class="recent-card glass-panel">
    <summary>{{ rc.card_header(r, season_year) }}</summary>
    <div class="recent-body">

        <div class="recent-week-line">
            <span class="week-stat">{{ r.week.ip if r.week.ip is not none else '-' }} IP</span>
            <span class="week-stat">{{ r.week.er }} ER</span>
            <span class="week-stat">{{ r.week.k }} K</span>
            <span class="week-stat">{{ r.week.bb }} BB</span>
            {% if r.week.csw_pct is not none %}<span class="week-stat">CSW% {{ rc.pct(r.week.csw_pct) }}</span>{% endif %}
            {% if r.week.whiff_pct is not none %}<span class="week-stat">Whiff% {{ rc.pct(r.week.whiff_pct) }}</span>{% endif %}
            {% if r.week.f_strike_pct is not none %}<span class="week-stat">F-Strike% {{ rc.pct(r.week.f_strike_pct) }}</span>{% endif %}
            {% if r.week.edge_pct is not none %}<span class="week-stat">Edge% {{ rc.pct(r.week.edge_pct) }}</span>{% endif %}
            {% if r.week.pickoffs %}<span class="week-stat">牽制 {{ r.week.pickoffs }}</span>{% endif %}
        </div>
        {{ rc.chips(r.chips) }}
        {{ rc.notes(r.notes) }}
        {% if not r.season_available %}{{ rc.fallback('本層級樣本尚不足以建立季基準') }}{% endif %}

        {% for g in r.games %}
        <div class="recent-game">
            <h4>{{ g.date.strftime('%m/%d') if g.date else '' }}
                {{ '主' if g.is_home else '客' }} {{ g.opponent }} — {{ g.summary }}</h4>
            {{ rc.chart_grid(r.game_charts.get(g.game_id, {}), {
                'pitch_map': '本壘板視角逐球位置（捕手方向）',
                'velocity': '球速序列（虛線＝球季均速）',
                'movement': '位移分佈（灰點＝球季）'}) }}
            {% if g.tier == 3 %}
            {{ rc.fallback('此層級（AA/A+）無進壘點追蹤資料，以下改以結果序列呈現') }}
            {{ rc.result_strip(g.pitches) }}
            {% elif g.tier == 2 %}
            {{ rc.fallback('此場僅部分球有追蹤資料，圖表以有追蹤的球計算') }}
            {% endif %}
        </div>
        {% endfor %}

        {% if r.deltas.arsenal %}
        <div class="table-scroll">
        <table class="data-table recent-arsenal-table">
            <thead><tr>
                <th>球種</th><th>週球數</th><th>Usage</th><th>Δ</th>
                <th>均速</th><th>Δ</th><th>Whiff Δ</th><th>Chase Δ</th><th>Zone Δ</th>
                <th>VAA</th><th>EffVelo</th><th>轉軸</th>
            </tr></thead>
            <tbody>
            {% for row in r.deltas.arsenal %}
            {% set d = r.week.derived_by_type.get(row.type, {}) %}
            <tr>
                <td>{{ row.name }}
                    {% if row.is_new %}<span class="badge-new">NEW</span>{% endif %}
                    {% if row.is_dropped %}<span class="badge-drop">棄用</span>{% endif %}</td>
                <td class="num">{{ row.count }}</td>
                <td class="num">{{ rc.pct(row.week_pct) }}</td>
                <td class="num">{{ rc.pp(row.usage_delta) }}</td>
                <td class="num">{{ row.week_velo if row.week_velo is not none else '-' }}</td>
                <td class="num">{{ rc.mph(row.velo_delta) }}</td>
                <td class="num">{{ rc.pp(row.whiff_delta) }}</td>
                <td class="num">{{ rc.pp(row.chase_delta) }}</td>
                <td class="num">{{ rc.pp(row.zone_delta) }}</td>
                <td class="num">{{ d.vaa if d.vaa is not none else '-' }}</td>
                <td class="num">{{ d.eff_velo if d.eff_velo is not none else '-' }}</td>
                <td class="num">{{ d.spin_clock or '-' }}</td>
            </tr>
            {% endfor %}
            </tbody>
        </table>
        </div>
        {% elif r.week.arsenal %}
        {# 無季基準：只列週值原始數字（§0.3 fallback） #}
        <div class="table-scroll">
        <table class="data-table recent-arsenal-table">
            <thead><tr>
                <th>球種</th><th>週球數</th><th>Usage</th><th>均速</th>
                <th>Whiff%</th><th>VAA</th><th>EffVelo</th><th>轉軸</th>
            </tr></thead>
            <tbody>
            {% for row in r.week.arsenal %}
            {% set d = r.week.derived_by_type.get(row.type, {}) %}
            <tr>
                <td>{{ row.name }}</td>
                <td class="num">{{ row.count }}</td>
                <td class="num">{{ rc.pct(row.pct) }}</td>
                <td class="num">{{ row.velo if row.velo is not none else '-' }}</td>
                <td class="num">{{ rc.pct(row.whiff_pct) }}</td>
                <td class="num">{{ d.vaa if d.vaa is not none else '-' }}</td>
                <td class="num">{{ d.eff_velo if d.eff_velo is not none else '-' }}</td>
                <td class="num">{{ d.spin_clock or '-' }}</td>
            </tr>
            {% endfor %}
            </tbody>
        </table>
        </div>
        {% elif r.tier == 3 %}
        {{ rc.fallback('此層級無球種標記資料') }}
        {% endif %}

        {% if r.scoring_events %}
        <div class="recent-scoring">
            <h4>失分事件</h4>
            <ul>
                {% for e in r.scoring_events %}
                <li>{{ e.date.strftime('%m/%d') if e.date else '' }} 第 {{ e.inning }} 局 —
                    {{ e.event }}{% if e.earned is sameas false %}（非自責）{% endif %}</li>
                {% endfor %}
            </ul>
        </div>
        {% endif %}

        <a class="recent-player-link" href="{{ player_url(r.player.mlb_id) }}">前往球員完整頁面 →</a>
    </div>
</details>
```

`src/templates/partials/recent_batter_report.j2`：

```jinja
{% import "macros/recents.j2" as rc %}
<details class="recent-card glass-panel">
    <summary>{{ rc.card_header(r, season_year) }}</summary>
    <div class="recent-body">

        {% set line = r.week.batting_line %}
        <div class="recent-week-line">
            <span class="week-stat">{{ line.hits }}-{{ line.ab }}</span>
            {% if line.avg is not none %}<span class="week-stat">AVG {{ '%.3f'|format(line.avg) }}</span>{% endif %}
            <span class="week-stat">{{ line.hr }} HR</span>
            <span class="week-stat">{{ line.rbi }} RBI</span>
            <span class="week-stat">{{ line.bb }} BB / {{ line.k }} K</span>
            {% if r.week.k_pct is not none %}<span class="week-stat">K% {{ rc.pct(r.week.k_pct) }}</span>{% endif %}
            {% if r.week.bb_pct is not none %}<span class="week-stat">BB% {{ rc.pct(r.week.bb_pct) }}</span>{% endif %}
            {% if r.week.ev and r.week.ev.avg_ev is not none %}<span class="week-stat">EV {{ r.week.ev.avg_ev }}</span>{% endif %}
            {% if r.week.ev and r.week.ev.bat_speed is not none %}<span class="week-stat">Bat Speed {{ r.week.ev.bat_speed }} mph</span>{% endif %}
        </div>
        {{ rc.chips(r.chips) }}
        {{ rc.notes(r.notes) }}
        {% if not r.season_available %}{{ rc.fallback('本層級樣本尚不足以建立季基準') }}{% endif %}

        {% if r.zone_chart %}
        <figure class="recent-chart recent-chart-solo">
            <img src="{{ r.zone_chart }}" alt="打者熱區" loading="lazy">
            <figcaption>底色＝本季各區打擊率（樣本不足處灰色顯示 n），圓點＝本週打席終結球位置</figcaption>
        </figure>
        {% elif r.zone_chart_missing_reason %}
        {{ rc.fallback(r.zone_chart_missing_reason) }}
        {% endif %}

        {% for g in r.games %}
        <div class="recent-game">
            <h4>{{ g.date.strftime('%m/%d') if g.date else '' }}
                {{ '主' if g.is_home else '客' }} {{ g.opponent }} — {{ g.summary }}</h4>
            {{ rc.chart_grid(r.game_charts.get(g.game_id, {}), {
                'pitch_map': '本場所見球位置（捕手方向）',
                'ev_la': 'EV / LA（灰點＝球季、teal 外框＝Barrel）',
                'spray': '落點圖（灰點＝球季）'}) }}
            {% if g.tier == 3 %}
            {{ rc.fallback('此層級（AA/A+）無進壘點追蹤資料，以下改以結果序列呈現') }}
            {{ rc.result_strip(g.pitches) }}
            {% elif g.tier == 2 %}
            {{ rc.fallback('此場僅部分球有追蹤資料，圖表以有追蹤的球計算') }}
            {% endif %}
        </div>
        {% endfor %}

        {% if r.quality_chart %}
        <figure class="recent-chart recent-chart-solo">
            <img src="{{ r.quality_chart }}" alt="擊球品質（週 vs 季）" loading="lazy">
            <figcaption>無 EV 追蹤層級的替代指標：記錄員擊球品質與擊球型態分佈（週 vs 季）</figcaption>
        </figure>
        {% endif %}

        {% if r.deltas.discipline %}
        <div class="table-scroll">
        <table class="data-table recent-discipline-table">
            <thead><tr><th>指標</th><th>本週</th><th>球季</th><th>Δ</th></tr></thead>
            <tbody>
            {% for key, label in [('o_swing_pct', 'Chase%'), ('whiff_pct', 'Whiff%'),
                                  ('z_contact_pct', 'Z-Contact%'), ('swstr_pct', 'SwStr%'),
                                  ('zone_pct', 'Zone%')] %}
            {% set e = r.deltas.discipline.get(key) %}
            {% if e %}
            <tr>
                <td>{{ label }}</td>
                <td class="num">{{ rc.pct(e.week) }}</td>
                <td class="num">{{ rc.pct(e.season) }}</td>
                <td class="num">{{ rc.pp(e.delta) }}</td>
            </tr>
            {% endif %}
            {% endfor %}
            </tbody>
        </table>
        </div>
        {% endif %}

        {% if r.group_splits %}
        <div class="table-scroll">
        <table class="data-table recent-groups-table">
            <thead><tr><th>球種群</th><th>球數</th><th>Whiff%</th><th>H/AB</th><th>AVG</th><th>平均 EV</th></tr></thead>
            <tbody>
            {% for gsp in r.group_splits %}
            <tr>
                <td>{{ {'fastball': '速球', 'breaking': '變化球', 'offspeed': '慢速球'}[gsp.group] }}</td>
                <td class="num">{{ gsp.n }}</td>
                <td class="num">{{ rc.pct(gsp.whiff_pct) }}</td>
                <td class="num">{{ gsp.hits }}/{{ gsp.ab }}</td>
                <td class="num">{{ '%.3f'|format(gsp.avg) if gsp.avg is not none else '-' }}</td>
                <td class="num">{{ gsp.avg_ev if gsp.avg_ev is not none else '-' }}</td>
            </tr>
            {% endfor %}
            </tbody>
        </table>
        </div>
        {% endif %}

        {% if r.two_strike.pa %}
        <p class="recent-two-strike">兩好球後：{{ r.two_strike.pa }} PA、{{ r.two_strike.k }} K、
            {{ r.two_strike.hits }} H{% if r.two_strike.avg is not none %}（AVG {{ '%.3f'|format(r.two_strike.avg) }}）{% endif %}</p>
        {% endif %}

        {% if r.pa_timeline %}
        <div class="recent-pa-timeline">
            <h4>逐打席</h4>
            <ul>
                {% for pa in r.pa_timeline %}
                <li>
                    <span class="pa-meta">{{ pa.date.strftime('%m/%d') if pa.date else '' }}
                        第 {{ pa.inning }} 局 vs {{ 'LHP' if pa.pitch_hand == 'L' else 'RHP' }}</span>
                    <span class="pa-seq">{% for t, code in pa.sequence %}<span class="pitch-tag pitch-{{ t|lower }}">{{ t }}</span>{% endfor %}</span>
                    <span class="pa-result">{{ pa.result }}</span>
                    {% if pa.hit and pa.hit.ev is not none %}
                    <span class="pa-hit">EV {{ pa.hit.ev }}{% if pa.hit.distance %} / {{ pa.hit.distance }} ft{% endif %}</span>
                    {% endif %}
                </li>
                {% endfor %}
            </ul>
        </div>
        {% endif %}

        <a class="recent-player-link" href="{{ player_url(r.player.mlb_id) }}">前往球員完整頁面 →</a>
    </div>
</details>
```

- [ ] **Step 5: 實作 CSS**

`src/static/css/style.css` 在 `@import "charts.css";` 後加：

```css
@import "recents.css";
```

`src/static/css/recents.css`：

```css
/* ═══ /recents 近期出賽分析頁 ═══ */

.recents-header { padding: 16px 20px; margin-bottom: 16px; }
.recents-header h2 { margin: 0 0 4px; font-size: 1.15rem; }
.recents-subtitle { margin: 0; color: var(--text-2); font-size: 0.85rem; }
.recents-section-title { margin: 20px 4px 10px; font-size: 1rem; color: var(--text-1); }

/* ── 卡片 ── */
.recent-card { margin-bottom: 12px; padding: 0; overflow: hidden; }
.recent-card > summary { list-style: none; cursor: pointer; padding: 14px 16px; }
.recent-card > summary::-webkit-details-marker { display: none; }
.recent-card[open] > summary { border-bottom: 1px solid var(--border); }
.recent-card-summary { display: flex; gap: 14px; align-items: flex-start; }
.recent-card-info { flex: 1; min-width: 0; }
.recent-card-info h3 { margin: 0 0 2px; font-size: 1rem; }
.recent-name-en { color: var(--text-3); font-size: 0.8rem; font-weight: 400; }
.recent-card-team { color: var(--text-2); font-size: 0.82rem; margin-bottom: 6px; }
.recent-card-games { list-style: none; margin: 0; padding: 0; color: var(--text-2); font-size: 0.82rem; }
.recent-card-games li { padding: 1px 0; }
.recent-card-chips { flex-shrink: 0; }
.recent-body { padding: 14px 16px 18px; }

/* ── 週彙總與 chips ── */
.recent-week-line { display: flex; flex-wrap: wrap; gap: 8px 14px; margin-bottom: 10px; }
.week-stat { background: var(--card-surface); border: 1px solid var(--border);
             border-radius: 6px; padding: 3px 8px; font-size: 0.82rem; }
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
.delta-chip { border-radius: 999px; padding: 2px 10px; font-size: 0.78rem; border: 1px solid; }
.chip-good { color: var(--teal); border-color: rgb(var(--teal-rgb) / 0.45);
             background: rgb(var(--teal-rgb) / 0.12); }
.chip-bad { color: var(--red); border-color: rgb(var(--red-rgb) / 0.45);
            background: rgb(var(--red-rgb) / 0.12); }
.recent-notes { margin: 8px 0; padding-left: 18px; color: var(--text-1); font-size: 0.86rem; }
.recent-notes li { margin: 2px 0; }
.fallback-note { color: var(--text-3); font-style: italic; font-size: 0.8rem; margin: 6px 0; }

/* ── 逐場與圖表 ── */
.recent-game { margin-top: 14px; }
.recent-game h4 { margin: 0 0 8px; font-size: 0.9rem; color: var(--text-1); }
.recent-chart-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                     gap: 12px; overflow-x: auto; }
.recent-chart { margin: 0; }
.recent-chart img { width: 100%; height: auto; border-radius: var(--radius);
                    border: 1px solid var(--border); }
.recent-chart figcaption { color: var(--text-3); font-size: 0.75rem; margin-top: 4px; }
.recent-chart-solo { max-width: 480px; margin: 12px 0; }

/* ── Tier 3 逐球結果條 ── */
.result-strip { display: flex; flex-wrap: wrap; gap: 3px; margin: 6px 0; }
.strip { width: 11px; height: 11px; border-radius: 2px; display: inline-block; }
.strip-inplay { background: #3987e5; }
.strip-whiff { background: #e66767; }
.strip-called { background: #c98500; }
.strip-foul { background: #71717a; }
.strip-ball { background: #3f3f46; }
.strip-final { outline: 1.5px solid var(--teal); outline-offset: 1px; }
.strip-legend { display: flex; flex-wrap: wrap; gap: 10px; color: var(--text-3);
                font-size: 0.72rem; margin-bottom: 8px; align-items: center; }
.strip-legend .strip { margin-right: 3px; vertical-align: -1px; }

/* ── 表格徽章與其他 ── */
.badge-new, .badge-drop { border-radius: 4px; font-size: 0.68rem; padding: 1px 5px; margin-left: 4px; }
.badge-new { background: rgb(var(--teal-rgb) / 0.18); color: var(--teal); }
.badge-drop { background: rgb(var(--red-rgb) / 0.18); color: var(--red); }
.recent-scoring ul, .recent-pa-timeline ul { list-style: none; margin: 4px 0; padding: 0;
                                             font-size: 0.84rem; color: var(--text-2); }
.recent-scoring li, .recent-pa-timeline li { padding: 3px 0; }
.recent-pa-timeline .pa-meta { color: var(--text-3); margin-right: 8px; }
.recent-pa-timeline .pa-seq { margin-right: 8px; }
.recent-pa-timeline .pa-result { color: var(--text-1); }
.recent-pa-timeline .pa-hit { color: var(--text-3); margin-left: 8px; }
.recent-two-strike { font-size: 0.86rem; color: var(--text-2); }
.recent-player-link { display: inline-block; margin-top: 14px; color: var(--teal);
                      text-decoration: none; font-size: 0.86rem; }
.recent-player-link:hover { text-decoration: underline; }

@media (max-width: 640px) {
    .recent-card-summary { flex-wrap: wrap; }
    .recent-card-chips { width: 100%; }
    .recent-chart-grid { grid-template-columns: 1fr; }
}
```

- [ ] **Step 6: 跑測試通過**

Run: `python -m pytest tests/test_recents_render.py -v` → 2 PASS
Run: `python -m pytest tests/` → 全綠

- [ ] **Step 7: Commit**

```bash
git add site_builder/render/recents.py src/templates/recents.j2 src/templates/macros/recents.j2 src/templates/partials/ src/static/css/recents.css src/static/css/style.css tests/test_recents_render.py
git commit -m "feat: /recents page renderer with per-game matplotlib charts and tiered fallbacks"
```

---

### Task 13: 接上 build pipeline（pages.py、選單、sitemap）

**Files:**
- Modify: `site_builder/render/pages.py`
- Modify: `src/templates/base.j2`

**Interfaces:**
- Consumes：Task 12 `build_recents_page`。
- `build_static_site` 於「── 404 page ──」段落之前呼叫；sitemap 加入 recents entry；`base.j2` 選單加第三項（`nav_active == 'recents'`）。

- [ ] **Step 1: pages.py 匯入與呼叫**

`site_builder/render/pages.py` 頂部 import 區加：

```python
from .recents import build_recents_page
```

在 `# ── 404 page ──` 註解那行之前插入：

```python
    # ── /recents 近期出賽分析頁 ──
    recents_sitemap_entry = build_recents_page(
        env, conn, out_dir, year, roster_ids
    )
```

sitemap 清單（`sitemap_urls = [...]` 定義之後、`for player, _, logs in bundles:` 迴圈之前）加：

```python
    sitemap_urls.append(recents_sitemap_entry)
```

- [ ] **Step 2: base.j2 選單加第三項**

在「已離美職體系」`</a>` 之後（`menu-dropdown` div 內）加：

```jinja
                        <a href="{{ base_url }}recents/" role="menuitem"
                           class="menu-item{% if nav_active == 'recents' %} menu-item--active{% endif %}">
                            <span class="menu-item-label">近期出賽</span>
                            <span class="menu-item-desc">近 7 天出賽球員分析報告</span>
                        </a>
```

- [ ] **Step 3: 全站建置驗證**

```bash
python -m pytest tests/            # 全綠
python build.py build              # 用本地 data/tracker.sqlite3
```

Expected: build 輸出 `Built N player pages + index to .../dist`，且：

```bash
ls dist/recents/index.html                       # 存在
ls dist/static/charts/recents/ 2>/dev/null       # 視窗內有出賽才有圖
grep -c "recents/" dist/sitemap.xml              # ≥1
grep "近期出賽" dist/index.html                   # 選單項出現在首頁
```

再以 `python -m http.server 8000 --directory dist` 目視檢查 `/recents/`：卡片展開、圖片載入、Tier 3 球員顯示結果條與 fallback 文案、圖表在窄視窗不橫向溢出。

- [ ] **Step 4: Commit**

```bash
git add site_builder/render/pages.py src/templates/base.j2
git commit -m "feat: wire /recents page into build pipeline, nav menu, and sitemap"
```

---

## Phase 6 — 逐球影片（MLB 限定）

### Task 14: `api/content.py` ＋ `db/play_videos.py` ＋ schema

**Files:**
- Create: `site_builder/api/content.py`
- Modify: `site_builder/api/__init__.py`（加 re-export）
- Modify: `site_builder/db/schema.py`（新增兩張表）
- Create: `site_builder/db/play_videos.py`
- Test: `tests/test_content_api.py`、`tests/test_play_videos.py`

**Interfaces:**
- Produces：
  - `get_game_content(game_pk: int) -> dict`（best-effort，失敗回 `{}`）。
  - `extract_play_videos(content: dict) -> list[dict]` — `[{"play_id": str, "title": str, "mp4_url": str}]`，只收 `guid` 非空且有 mp4 playback 的 item。
  - `save_play_videos(cur, game_pk, videos, now_iso)`、`mark_content_processed(cur, game_pk, videos_found: int, now_iso)`、`content_fetch_candidates(cur, roster_ids, retry_cutoff_date: str) -> list[int]`、`load_video_map(cur) -> dict[int, dict[str, str]]`（`{game_pk: {play_id: mp4_url}}`）。
- 新表：

```sql
CREATE TABLE IF NOT EXISTS play_videos (
    game_pk INTEGER NOT NULL,
    play_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    mp4_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    UNIQUE(game_pk, play_id)
);
CREATE TABLE IF NOT EXISTS game_content_processed (
    game_pk INTEGER PRIMARY KEY,
    processed_at TEXT NOT NULL,
    videos_found INTEGER NOT NULL DEFAULT 0
);
```

- [ ] **Step 1: 寫失敗測試**

`tests/test_content_api.py`：

```python
from site_builder.api.content import extract_play_videos

CONTENT_FIXTURE = {
    "highlights": {"highlights": {"items": [
        {   # 單一 play 精華：guid == play_id
            "guid": "a00d2214-3658-347f-98fc-24c89abb9d0e",
            "title": "Machado's 21st homer",
            "playbacks": [
                {"name": "hlsCloud", "url": "https://x/master.m3u8"},
                {"name": "mp4Avc", "url": "https://mlb-cuts-diamond.mlb.com/x.mp4"},
            ],
        },
        {   # 合輯類：guid 為 null → 略過
            "guid": None,
            "title": "Recap",
            "playbacks": [{"name": "mp4Avc", "url": "https://x/recap.mp4"}],
        },
        {   # 有 guid 但無 mp4 → 略過
            "guid": "ffffffff-0000-0000-0000-000000000000",
            "title": "HLS only",
            "playbacks": [{"name": "hlsCloud", "url": "https://x/only.m3u8"}],
        },
    ]}}
}


def test_extract_play_videos():
    videos = extract_play_videos(CONTENT_FIXTURE)
    assert videos == [{
        "play_id": "a00d2214-3658-347f-98fc-24c89abb9d0e",
        "title": "Machado's 21st homer",
        "mp4_url": "https://mlb-cuts-diamond.mlb.com/x.mp4",
    }]


def test_extract_play_videos_empty():
    assert extract_play_videos({}) == []
    assert extract_play_videos({"highlights": None}) == []
```

`tests/test_play_videos.py`：

```python
import sqlite3

from site_builder.db.play_videos import (
    content_fetch_candidates,
    load_video_map,
    mark_content_processed,
    save_play_videos,
)
from site_builder.db.schema import init_db

NOW = "2026-07-09T00:00:00+00:00"


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    cur = conn.cursor()
    # MLB 近期比賽 / MLB 舊比賽 / AAA 比賽
    rows = [
        (678906, "2026-07-06", 776911, "NYM", "MLB"),
        (678906, "2025-08-02", 700001, "SF", "MLB"),
        (678906, "2026-07-05", 779812, "LV", "AAA"),
    ]
    for mlb_id, date, gpk, opp, lvl in rows:
        cur.execute(
            "INSERT INTO game_logs (player_mlb_id, date, game_id, opponent,"
            " stats_json, pitches_json, sport_level) VALUES (?,?,?,?,'{}','[]',?)",
            (mlb_id, date, gpk, opp, lvl),
        )
    conn.commit()
    return conn


def test_candidates_only_mlb_and_unprocessed():
    conn = _conn()
    cur = conn.cursor()
    got = sorted(content_fetch_candidates(cur, [678906], "2026-06-25"))
    assert got == [700001, 776911]  # AAA 排除


def test_retry_window():
    conn = _conn()
    cur = conn.cursor()
    # 兩場都處理過但 0 部影片：只有 retry window 內的比賽重試
    mark_content_processed(cur, 776911, 0, NOW)
    mark_content_processed(cur, 700001, 0, NOW)
    got = content_fetch_candidates(cur, [678906], "2026-06-25")
    assert got == [776911]
    # 找到影片後不再是 candidate
    mark_content_processed(cur, 776911, 3, NOW)
    assert content_fetch_candidates(cur, [678906], "2026-06-25") == []


def test_save_and_load_video_map():
    conn = _conn()
    cur = conn.cursor()
    save_play_videos(cur, 776911, [
        {"play_id": "abc", "title": "t", "mp4_url": "https://x/a.mp4"},
    ], NOW)
    save_play_videos(cur, 776911, [
        {"play_id": "abc", "title": "t", "mp4_url": "https://x/a.mp4"},
    ], NOW)  # REPLACE，不重複
    vm = load_video_map(cur)
    assert vm == {776911: {"abc": "https://x/a.mp4"}}
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

`site_builder/db/schema.py`：在 events_json forward-migration 之後、`conn.commit()` 之前加：

```python
    # 逐球精華影片（statsapi /content 的 per-play mp4，MLB 限定）與
    # content 抓取進度（videos_found=0 且比賽仍在重試窗內者會再抓）。
    conn.execute("""
        CREATE TABLE IF NOT EXISTS play_videos (
            game_pk INTEGER NOT NULL,
            play_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            mp4_url TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            UNIQUE(game_pk, play_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS game_content_processed (
            game_pk INTEGER PRIMARY KEY,
            processed_at TEXT NOT NULL,
            videos_found INTEGER NOT NULL DEFAULT 0
        )
    """)
```

`site_builder/api/content.py`：

```python
"""Game content endpoint — per-play highlight video URLs (MLB only in practice)."""

import logging

from .client import BASE_URL, get_json

logger = logging.getLogger(__name__)


def get_game_content(game_pk: int) -> dict:
    """Fetch /game/{pk}/content. Best-effort: returns {} on failure."""
    url = f"{BASE_URL}/game/{game_pk}/content"
    try:
        return get_json(url)
    except Exception as e:
        logger.warning("game content failed for game_pk=%s: %s", game_pk, e)
        return {}


def extract_play_videos(content: dict) -> list[dict]:
    """Highlight items whose guid == a play's playId, with a direct mp4 URL.

    guid 為 null 的合輯（賽事濃縮/訪談）與只有 HLS 的 item 一律略過。
    """
    items = (
        ((content or {}).get("highlights") or {}).get("highlights") or {}
    ).get("items") or []
    out = []
    for item in items:
        guid = item.get("guid")
        if not guid:
            continue
        mp4 = None
        playbacks = item.get("playbacks") or []
        for pb in playbacks:
            name = pb.get("name") or ""
            url = pb.get("url") or ""
            if name.startswith("mp4Avc") and url.endswith(".mp4"):
                mp4 = url
                break
        if not mp4:
            for pb in playbacks:
                url = pb.get("url") or ""
                if url.endswith(".mp4"):
                    mp4 = url
                    break
        if mp4:
            out.append({
                "play_id": guid,
                "title": item.get("title") or "",
                "mp4_url": mp4,
            })
    return out
```

`site_builder/api/__init__.py`：在既有 re-export 區加：

```python
from .content import extract_play_videos, get_game_content
```

`site_builder/db/play_videos.py`：

```python
"""play_videos / game_content_processed 查詢（逐球精華影片快取）。"""


def save_play_videos(cur, game_pk: int, videos: list[dict], now_iso: str):
    for v in videos:
        cur.execute(
            "INSERT OR REPLACE INTO play_videos "
            "(game_pk, play_id, title, mp4_url, fetched_at) VALUES (?,?,?,?,?)",
            (game_pk, v["play_id"], v.get("title", ""), v["mp4_url"], now_iso),
        )


def mark_content_processed(cur, game_pk: int, videos_found: int, now_iso: str):
    cur.execute(
        "INSERT OR REPLACE INTO game_content_processed "
        "(game_pk, processed_at, videos_found) VALUES (?,?,?)",
        (game_pk, now_iso, videos_found),
    )


def content_fetch_candidates(cur, roster_ids, retry_cutoff_date: str) -> list[int]:
    """要抓 /content 的 MLB game_pk：從未處理過的，加上「處理過但 0 部影片
    且比賽日期仍在重試窗內」的（Savant/statsapi 精華索引有 1 天以上延遲）。"""
    if not roster_ids:
        return []
    ids = sorted(set(roster_ids))
    placeholders = ",".join("?" * len(ids))
    cur.execute(
        "SELECT DISTINCT g.game_id FROM game_logs g "
        "LEFT JOIN game_content_processed c ON c.game_pk = g.game_id "
        f"WHERE g.sport_level = 'MLB' AND g.player_mlb_id IN ({placeholders}) "
        "AND (c.game_pk IS NULL "
        "     OR (c.videos_found = 0 AND g.date >= ?))",
        [*ids, retry_cutoff_date],
    )
    return [row[0] for row in cur.fetchall() if row[0] is not None]


def load_video_map(cur) -> dict[int, dict[str, str]]:
    cur.execute("SELECT game_pk, play_id, mp4_url FROM play_videos")
    out: dict[int, dict[str, str]] = {}
    for game_pk, play_id, mp4_url in cur.fetchall():
        out.setdefault(game_pk, {})[play_id] = mp4_url
    return out
```

- [ ] **Step 4: 跑測試通過** → `python -m pytest tests/test_content_api.py tests/test_play_videos.py -v` 5 PASS

- [ ] **Step 5: Commit**

```bash
git add site_builder/api/content.py site_builder/api/__init__.py site_builder/db/schema.py site_builder/db/play_videos.py tests/test_content_api.py tests/test_play_videos.py
git commit -m "feat: play-video storage and game-content highlight extraction"
```

---

### Task 15: sync 整合（statcast pipeline 加 Phase 5）

**Files:**
- Modify: `site_builder/constants.py`（§1 加 `CONTENT_RETRY_DAYS = 14`）
- Modify: `site_builder/sync/statcast.py`
- Test: `tests/test_play_videos.py`（追加）

**Interfaces:**
- Produces：`fetch_highlight_videos(conn, roster_ids, *, now_iso: str|None = None) -> int`（回傳本次寫入影片數；`sync_statcast` 尾端呼叫）。
- Consumes：Task 14 全部、`GAME_FETCH_WORKERS`。

- [ ] **Step 1: 寫失敗測試（追加到 `tests/test_play_videos.py`）**

```python
def test_fetch_highlight_videos(monkeypatch):
    from site_builder.sync import statcast as sync_statcast_mod

    conn = _conn()

    def fake_content(game_pk):
        if game_pk == 776911:
            return {"highlights": {"highlights": {"items": [{
                "guid": "abc", "title": "K",
                "playbacks": [{"name": "mp4Avc", "url": "https://x/k.mp4"}],
            }]}}}
        return {}

    monkeypatch.setattr(sync_statcast_mod, "get_game_content", fake_content)
    written = sync_statcast_mod.fetch_highlight_videos(conn, [678906], now_iso=NOW)
    assert written == 1
    cur = conn.cursor()
    assert load_video_map(cur) == {776911: {"abc": "https://x/k.mp4"}}
    # 700001 標記為 0 部；776911 找到影片 → 不再是 candidate
    cur.execute("SELECT videos_found FROM game_content_processed WHERE game_pk=776911")
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT videos_found FROM game_content_processed WHERE game_pk=700001")
    assert cur.fetchone()[0] == 0
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL（`fetch_highlight_videos` 不存在）

- [ ] **Step 3: 實作**

`site_builder/constants.py` §1（`GAME_FETCH_WORKERS` 之後）加：

```python
# 逐球精華影片：/content 精華索引有 1 天以上延遲，videos_found=0 的比賽在
# 賽後 N 天內每次 sync 重試。
CONTENT_RETRY_DAYS = 14
```

`site_builder/sync/statcast.py`：

import 區調整——`from ..api import (...)` 加 `get_game_content`；`from ..constants import GAME_FETCH_WORKERS` 改為 `from ..constants import CONTENT_RETRY_DAYS, GAME_FETCH_WORKERS`；並加：

```python
from ..api.content import extract_play_videos
from ..db.play_videos import (
    content_fetch_candidates,
    mark_content_processed,
    save_play_videos,
)
```

（注意：`get_game_content` 走 `from ..api import ...` 匯入，讓測試能以
`monkeypatch.setattr(sync_statcast_mod, "get_game_content", ...)` 換掉。）

模組層新增函式（放在 `sync_statcast` 之前）：

```python
def fetch_highlight_videos(conn, roster_ids, *, now_iso=None) -> int:
    """Phase 5：為 MLB 比賽抓 /content 逐球精華 mp4（來源 A，永久連結）。"""
    now_iso = now_iso or datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = conn.cursor()
    retry_cutoff = (
        datetime.date.today() - datetime.timedelta(days=CONTENT_RETRY_DAYS)
    ).isoformat()
    candidates = content_fetch_candidates(cur, roster_ids, retry_cutoff)
    if not candidates:
        return 0
    print(f"Statcast: fetching highlight content for {len(candidates)} MLB game(s) ...")
    contents: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=GAME_FETCH_WORKERS) as executor:
        future_to_gpk = {
            executor.submit(get_game_content, gpk): gpk for gpk in candidates
        }
        for future in as_completed(future_to_gpk):
            gpk = future_to_gpk[future]
            try:
                contents[gpk] = future.result()
            except Exception as e:
                logger.warning("content fetch failed for game_pk=%s: %s", gpk, e)
                contents[gpk] = {}
    written = 0
    for gpk, content in contents.items():
        videos = extract_play_videos(content)
        save_play_videos(cur, gpk, videos, now_iso)
        mark_content_processed(cur, gpk, len(videos), now_iso)
        written += len(videos)
    conn.commit()
    print(f"  saved {written} play video(s) across {len(candidates)} game(s)")
    return written
```

`sync_statcast()` 尾端、`conn.close()` 之前加：

```python
    # ── Phase 5: highlight videos (MLB games only) ──
    fetch_highlight_videos(conn, list(roster_map.keys()))
```

- [ ] **Step 4: 跑測試通過** → `python -m pytest tests/test_play_videos.py -v` 全 PASS；`python -m pytest tests/` 全綠（確認 statcast 既有測試沒被 import 變更弄壞）

- [ ] **Step 5: Commit**

```bash
git add site_builder/constants.py site_builder/sync/statcast.py tests/test_play_videos.py
git commit -m "feat: fetch per-play highlight videos during statcast sync"
```

---

### Task 16: render ＋ 前端播放（pitch log 加影片欄）

**Files:**
- Modify: `site_builder/render/pitch_log.py`
- Modify: `site_builder/render/pages.py`
- Modify: `src/static/js/pitch-log.js`
- Modify: `src/static/css/gamelogs.css`（尾端追加樣式）
- Test: `tests/test_pitch_log_video.py`

**Interfaces:**
- `summarize_pitch_for_display(p, video_map: dict|None = None, include_video: bool = False) -> dict` — `include_video=True`（MLB 場）時輸出 `play_id`，且 `video_map` 命中時輸出 `video`（mp4 URL）；非 MLB 場兩鍵皆不出現（層級 gating 在資料層完成）。
- `write_pitch_log_files(logs_by_year, out_dir, normalized_base_url, mlb_id, videos_by_game: dict|None = None)`。
- 前端：pitch log 表格尾欄「▶」；`p.video` → overlay `<video>`；`p.play_id`（無 mp4）→ overlay Savant iframe ＋ 固定文案與外部連結（plan §0.8）。

- [ ] **Step 1: 寫失敗測試**

`tests/test_pitch_log_video.py`：

```python
import json

from site_builder.render.pitch_log import (
    summarize_pitch_for_display,
    write_pitch_log_files,
)
from site_builder.util.obj import Obj
from tests.recent_fixtures import make_pitch

PID = "b339cea8-e12d-340f-adbc-a655fb63aaed"


def test_summarize_video_gating():
    p = make_pitch()
    plain = summarize_pitch_for_display(p)
    assert "play_id" not in plain and "video" not in plain

    mlb = summarize_pitch_for_display(p, {PID: "https://x/a.mp4"},
                                      include_video=True)
    assert mlb["play_id"] == PID and mlb["video"] == "https://x/a.mp4"

    no_hit = summarize_pitch_for_display(p, {}, include_video=True)
    assert no_hit["play_id"] == PID and "video" not in no_hit


def _log(game_id, level):
    log = Obj()
    log.game_id = game_id
    log.sport_level = level
    log.pitches_json = [make_pitch()]
    return log


def test_write_pitch_log_files_gating(tmp_path):
    mlb_log = _log(776911, "MLB")
    aaa_log = _log(779812, "AAA")
    write_pitch_log_files({2026: [mlb_log, aaa_log]}, tmp_path, "/", 678906,
                          videos_by_game={776911: {PID: "https://x/a.mp4"}})
    mlb_json = json.loads(
        (tmp_path / "data/pitchlogs/678906/776911.json").read_text())
    aaa_json = json.loads(
        (tmp_path / "data/pitchlogs/678906/779812.json").read_text())
    assert mlb_json[0]["video"] == "https://x/a.mp4"
    assert "play_id" not in aaa_json[0] and "video" not in aaa_json[0]
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL（unexpected keyword argument）

- [ ] **Step 3: 實作 `render/pitch_log.py`**

`summarize_pitch_for_display` 改為：

```python
def summarize_pitch_for_display(p: dict, video_map: dict | None = None,
                                include_video: bool = False) -> dict:
    """Thin projection of a pitch dict for use in the per-game expandable row.

    ``include_video``（僅 MLB 場為 True）時附 ``play_id``，供前端組
    Savant 連結；``video_map`` 命中時再附站內可播的精華 ``video`` URL。
    非 MLB 場兩鍵一律不輸出 —— 層級 gating 在資料層完成，前端不需判斷層級。
    """
    d = {
        "inning": p.get("inning"),
        "pitch_type": p.get("pitch_type", ""),
        "pitch_name": p.get("pitch_name", ""),
        "speed": p.get("start_speed"),
        "zone": p.get("zone"),
        "result": p.get("result_desc") or p.get("result_code", ""),
        "ev": p.get("ev"),
        "la": p.get("la"),
        "ivb": p.get("ivb"),
        "hb": p.get("hb"),
        "spin": p.get("spin_rate"),
        "extension": p.get("extension"),
        "pa_event": p.get("pa_event_desc") if p.get("is_pa_final") else "",
        "balls": p.get("balls"),
        "strikes": p.get("strikes"),
    }
    if include_video:
        pid = p.get("play_id")
        if pid:
            d["play_id"] = pid
            url = (video_map or {}).get(pid)
            if url:
                d["video"] = url
    return d
```

`write_pitch_log_files` 簽名加 `videos_by_game=None`，迴圈內把

```python
                pitch_display = [
                    summarize_pitch_for_display(p) for p in log.pitches_json
                ]
```

改成：

```python
                is_mlb = log.sport_level == "MLB"
                video_map = (videos_by_game or {}).get(log.game_id) if is_mlb else None
                pitch_display = [
                    summarize_pitch_for_display(p, video_map, include_video=is_mlb)
                    for p in log.pitches_json
                ]
```

（注意 `db/bundles.py::load_player_bundle` 已將 `log.sport_level` 載入，無需改動。）

- [ ] **Step 4: 實作 `render/pages.py` 接線**

import 區加：

```python
from ..db.play_videos import load_video_map
```

`bundles = [load_player_bundle(cur, row) for row in rows]` 之後加：

```python
    # 逐球精華影片對照表（MLB 場的 pitch log JSON 會帶 play_id/video）
    videos_by_game = load_video_map(cur)
```

球員迴圈內的呼叫改為：

```python
        write_pitch_log_files(logs_by_year, out_dir, normalized_base_url,
                              player.mlb_id, videos_by_game=videos_by_game)
```

- [ ] **Step 5: 前端 `src/static/js/pitch-log.js`**

`_buildPitchTable` 整個函式替換為（新增「▶」欄與 `_videoCell`）：

```js
// 將逐球 JSON 數據轉成 HTML 表格字串（編號/球數/局倒/球種/車速/區帶等欄位）
function _buildPitchTable(pitches) {
    var hasVideo = pitches.some(function (p) { return p.play_id || p.video; });
    var h = '<table class="pitch-log-table"><thead><tr>' +
        '<th data-tooltip="逐球序號">#</th><th data-tooltip="投球前球數">Count</th><th data-tooltip="局數">INN</th><th data-tooltip="球種">Type</th><th data-tooltip="球速">Speed</th>' +
        '<th data-tooltip="進壘區域">Zone</th><th data-tooltip="單球結果">Result</th><th data-tooltip="擊球初速">EV</th><th data-tooltip="擊球仰角">LA</th>' +
        '<th data-tooltip="誘導垂直位移">iVB</th><th data-tooltip="水平位移">HB</th><th data-tooltip="轉速">Spin</th><th data-tooltip="出手延伸距離">Ext</th>' +
        '<th data-tooltip="打席結果">PA Event</th>' +
        (hasVideo ? '<th data-tooltip="逐球影片">▶</th>' : '') +
        '</tr></thead><tbody>';
    var prevBalls = 0, prevStrikes = 0, paEnded = true;
    for (var i = 0; i < pitches.length; i++) {
        var p = pitches[i];
        var preBalls = paEnded ? 0 : prevBalls;
        var preStrikes = paEnded ? 0 : prevStrikes;
        var countStr = (p.balls != null) ? (preBalls + '-' + preStrikes) : '-';
        paEnded = !!p.pa_event;
        if (p.balls != null) { prevBalls = p.balls; prevStrikes = p.strikes != null ? p.strikes : 0; }
        var cls = p.pa_event ? ' class="pitch-pa-final"' : '';
        var pt = (p.pitch_type || '').toLowerCase();
        var pn = p.pitch_name || p.pitch_type || '—';
        h += '<tr' + cls + '>' +
            '<td class="num">' + (i+1) + '</td>' +
            '<td class="num">' + countStr + '</td>' +
            '<td class="num">' + _fmt(p.inning) + '</td>' +
            '<td><span class="pitch-tag pitch-' + pt + '">' + pn + '</span></td>' +
            '<td class="num">' + _fmt(p.speed,1) + '</td>' +
            '<td class="num">' + _fmt(p.zone) + '</td>' +
            '<td>' + (p.result || '—') + '</td>' +
            '<td class="num">' + _fmt(p.ev,1) + '</td>' +
            '<td class="num">' + _fmt(p.la,1) + '</td>' +
            '<td class="num">' + _fmt(p.ivb,1) + '</td>' +
            '<td class="num">' + _fmt(p.hb,1) + '</td>' +
            '<td class="num">' + _fmt(p.spin) + '</td>' +
            '<td class="num">' + _fmt(p.extension,2) + '</td>' +
            '<td>' + (p.pa_event ? '<span class="pa-event-tag">' + p.pa_event + '</span>' : '') + '</td>' +
            (hasVideo ? _videoCell(p) : '') +
            '</tr>';
    }
    h += '</tbody></table>';
    return h;
}
```

檔案尾端追加：

```js
/* ── 逐球影片 ──
 * 資料層已做層級 gating：只有 MLB 場的 JSON 才帶 play_id/video。
 * p.video  → 站內 <video>（statsapi content 精華，永久 CDN 連結）
 * p.play_id（無 video）→ Baseball Savant iframe + 外部連結 fallback
 */
var SAVANT_VIDEO_URL = 'https://baseballsavant.mlb.com/sporty-videos?playId=';

function _videoCell(p) {
    if (p.video) {
        return '<td class="num"><button type="button" class="pitch-video-btn"' +
            ' data-video="' + p.video + '"' +
            ' onclick="openPitchVideo(event, this)" title="播放精華影片">▶</button></td>';
    }
    if (p.play_id) {
        return '<td class="num"><button type="button" class="pitch-video-btn pitch-video-btn--savant"' +
            ' data-play-id="' + p.play_id + '"' +
            ' onclick="openPitchVideo(event, this)" title="在 Baseball Savant 查看">SV</button></td>';
    }
    return '<td class="num">-</td>';
}

function closePitchVideo() {
    var overlay = document.getElementById('pitch-video-overlay');
    if (overlay) overlay.remove();
}

function openPitchVideo(evt, btn) {
    evt.stopPropagation();
    closePitchVideo();
    var mp4 = btn.dataset.video;
    var playId = btn.dataset.playId;
    var overlay = document.createElement('div');
    overlay.id = 'pitch-video-overlay';
    overlay.className = 'pitch-video-overlay';
    var inner = '<div class="pitch-video-box">' +
        '<button type="button" class="pitch-video-close" onclick="closePitchVideo()" aria-label="關閉">×</button>';
    if (mp4) {
        inner += '<video controls autoplay playsinline src="' + mp4 + '"></video>';
    } else {
        var url = SAVANT_VIDEO_URL + encodeURIComponent(playId);
        inner += '<iframe src="' + url + '" allowfullscreen loading="lazy"></iframe>' +
            '<p class="pitch-video-note">影片可能需要 1 天以上才會上架；若無畫面請' +
            '<a href="' + url + '" target="_blank" rel="noopener noreferrer">前往 Baseball Savant</a>。</p>';
    }
    inner += '</div>';
    overlay.innerHTML = inner;
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closePitchVideo();
    });
    document.body.appendChild(overlay);
}
```

- [ ] **Step 6: CSS（`src/static/css/gamelogs.css` 尾端追加）**

```css
/* ── 逐球影片按鈕與 overlay ── */
.pitch-video-btn { background: var(--card-surface); border: 1px solid var(--border);
    color: var(--teal); border-radius: 4px; padding: 1px 7px; cursor: pointer;
    font-size: 0.72rem; line-height: 1.4; }
.pitch-video-btn:hover { border-color: var(--teal); }
.pitch-video-btn--savant { color: var(--text-2); }
.pitch-video-overlay { position: fixed; inset: 0; background: rgb(0 0 0 / 0.75);
    display: flex; align-items: center; justify-content: center; z-index: 1000; }
.pitch-video-box { position: relative; width: min(92vw, 860px);
    background: var(--card-surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 12px; }
.pitch-video-box video, .pitch-video-box iframe { width: 100%;
    aspect-ratio: 16 / 9; border: 0; border-radius: 4px; background: #000; }
.pitch-video-close { position: absolute; top: 4px; right: 10px; background: none;
    border: none; color: var(--text-2); font-size: 1.4rem; cursor: pointer; }
.pitch-video-note { color: var(--text-3); font-size: 0.78rem; margin: 8px 0 0; }
```

- [ ] **Step 7: 跑測試 + 建置驗證**

```bash
python -m pytest tests/ -v          # 全綠
python build.py build
```

目視：開任一有 MLB 出賽的球員頁 → 逐場紀錄 → 展開 MLB 場：有精華的球顯示「▶」（站內播放）、其他球顯示「SV」（overlay iframe＋延遲文案＋外部連結）；展開 AAA/AA 場：**整欄不出現**。（本地 DB 尚未跑過 Task 15 的 sync 時，「▶」不會出現、只有「SV」——屬預期，`play_id` 來自 pitch log 本身。）

- [ ] **Step 8: Commit**

```bash
git add site_builder/render/pitch_log.py site_builder/render/pages.py src/static/js/pitch-log.js src/static/css/gamelogs.css tests/test_pitch_log_video.py
git commit -m "feat: per-pitch video playback in pitch log (MLB only, savant iframe fallback)"
```

---

## Phase 7 — 收尾

### Task 17: 文件更新 ＋ 全站驗證

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/SITE_BUILDER_FUNCTION_LIST.md`
- Modify: `docs/pitch_video_embedding.md`
- Modify: `docs/superpowers/specs/2026-07-05-recents-page-design.md`

- [ ] **Step 1: CLAUDE.md**

「Database Inspection」表清單加兩行：

```markdown
- `play_videos`: 逐球精華影片快取（statsapi /content 的 per-play mp4，MLB 限定）
- `game_content_processed`: 追蹤哪些 MLB 比賽已抓過 /content（videos_found=0 且在 14 天重試窗內者會重抓）
```

「File Organization」的 `site_builder/` 區塊加：

```
  charts/               # matplotlib 靜態圖表引擎（深色主題；/recents 的 PNG 產出）
  stats/recent/         # 近 7 天週報告計算（視窗、Tier、衍生指標、delta、chips）
```

「Architecture > Data Flow」第 5 點句尾補：`recents.py` renders the `/recents/` weekly-report page（charts via `site_builder/charts/`）。

- [ ] **Step 2: docs/SITE_BUILDER_FUNCTION_LIST.md**

依該文件既有格式，為 `charts/`、`stats/recent/`、`api/content.py`、`db/play_videos.py`、`render/recents.py` 各加一節函式清單（函式名與一句話職責，照本 plan 的 Interfaces 區塊抄錄即可），並在模組依賴圖把 `charts/` 放在與 `graph/` 同層。

- [ ] **Step 3: docs/pitch_video_embedding.md**

文件開頭第 5 行的「**本文件只記錄調查結果與建議方案，尚未實作。**」改為：

```markdown
> **狀態更新（2026-07）**：第一階段（方案 a，精華球站內播放）與一般球的
> Savant iframe fallback（方案 d 的簡化版：不做查無影片偵測，以固定文案＋
> 外部連結取代）皆已實作 — 見 `site_builder/api/content.py`、
> `site_builder/db/play_videos.py`、`sync/statcast.py::fetch_highlight_videos`、
> `src/static/js/pitch-log.js`。法律面確認（風險 1）仍待人工處理。
```

- [ ] **Step 4: recents spec 文件**

`2026-07-05-recents-page-design.md` 狀態行改為 `狀態：已實作（實作規格見 docs/superpowers/plans/2026-07-09-recents-charts-video.md，§7.3 的 canvas 方案被 matplotlib 靜態圖取代）`。

- [ ] **Step 5: 最終驗證**

```bash
python -m pytest tests/ -v                        # 全綠
python build.py build                             # 成功
python -m http.server 8000 --directory dist       # 手動目視 / /recents/ /player/<id>
```

檢查清單：
1. `/recents/` 卡片、chips、notes、圖表、Tier 3 fallback 文案與結果條。
2. 打者熱區圖遮罩格顯示 `n=N`、AVG 格印 `.xxx`。
3. 球員頁 MLB 場逐球表有影片欄；MiLB 場沒有。
4. `dist/sitemap.xml` 含 `recents/`。
5. 行動版（縮窗）圖表單欄、無橫向捲動溢出。

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md docs/
git commit -m "docs: document recents page, chart engine, and pitch video pipeline"
```

---

## 執行順序與里程碑

| 里程碑 | Tasks | 完成後網站狀態 |
|---|---|---|
| M1 圖表引擎 | 1 | 無 UI 變化（純新增模組＋依賴） |
| M2 資料層 | 2–4 | 無 UI 變化 |
| M3 圖表 | 5–9 | 無 UI 變化 |
| M4 /recents 上線 | 10–13 | 新頁面＋選單＋sitemap，完整可部署 |
| M5 逐球影片 | 14–16 | 球員頁影片欄，完整可部署 |
| M6 收尾 | 17 | 文件同步 |

M4 與 M5 相互獨立：若需要，可先只出 M4（或調換順序）。

## 有意延後的項目（本 plan 不實作，避免範圍膨脹）

以下在來源 spec 或新抓欄位中出現、但刻意不納入本輪，留待後續：

1. **放球點漂移圖**（spec §3.3，`x0/z0` 週 vs 季散點）— 位移疊圖已覆蓋主要「機制改變」訊號。
2. **投手九宮格 usage 熱區**（spec §3.4 週 vs 季進壘分佈）— 單場 pitch map 已呈現位置；`render_hot_zone` 已支援 `swing_pct`/`whiff_pct` metric，後續接上即可。
3. **`type_confidence` < 0.5 過濾**（spec §2.1）— 會同時影響既有球員頁季統計，需獨立評估後全站一致套用。
4. **VAA/EffVelo 回饋到球員頁 arsenal 表**（spec Phase 4 後半）。
5. **WPA / leverage_index 高壓打席敘事**、`hit_probability`、`pitch_speed_pct` 等 contextMetrics 欄位。
6. **`plate_time` 反應時間**、`sz_edge_distance` 精細 edge 計算（目前用 attack-zone 近似）。
7. spec §6 的外部資料項（官方 xwOBA、sprint speed、spin efficiency…）。
8. 首頁「本週 N 場」徽章連到 /recents。

## 風險備忘（執行者須知）

1. **matplotlib 版本**：若 `matplotlib==3.10.3` 在 pip 上不存在（版本下架），改 pin 當下最新的 3.10.x 或 3.11.x 並重跑 `tests/test_charts.py`。
2. **CI build 時間**：圖表只為 7 天視窗生成（<100 張），預估 build 增加 <60s；若超過，優先檢查是否誤為歷史比賽產圖。
3. **影片法律面**：Task 14–16 完成即上線；對外公開前的條款確認（`docs/pitch_video_embedding.md` 風險 1）是人工決策，不在本 plan 內。
4. **`pitches_json` 為 `"null"` 字串**：`loads_json_list` 已容錯（回 `[]`），視窗載入不需特判。
5. **同名球員多層級**：同一球員同週跨層級（升降）會產生多張卡片（每層級一張），是刻意設計。






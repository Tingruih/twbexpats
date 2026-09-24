# TwbExpats

這是一個維護所有台灣旅美棒球員的數據網站，透過github action , db on google drive 每天更新網站

## MUST / NEVER
1. 每次若有在 `site_builder` 內新增、刪除函式或改變函式簽名，**確保更新 `docs/functions_list.md`**
2. 每次對數據有改動，需要重新回填 database 時，**不要寫特殊邏輯的回補性代碼在 `site_builder` 內**
3. 每次對 database 的資料結構有改動時，**確保更新 `docs/db_schema.md`**
4. 每次只要更改、新增與數據欄位有關的邏輯，**確保更新 `docs/fields.md`**
5. 每當對使用者的 prompt **有不確定或是有疑問時，請直接向使用者提出問題，不要猜測**
6. **單一事實來源**：新增函式前先查 `docs/functions_list.md`／搜尋現有程式碼，確認沒有功能重複或相似的 function 已存在；`site_builder/levels.py`（賽事層級）、`site_builder/roster.py`（名冊狀態）、`site_builder/positions.py`（守位 → 投手/打者角色）是唯一權威表，**不要**在其他檔案裡重新定義或複製一份同樣的對照表
7. **撰寫或修改與數據公式相關的程式碼前，先查證各大數據網站（FanGraphs、tjstats.ca、Baseball Savant 等）對該數據的定義**，並確認公式會用到的分子分母/變數，語意上是否真的對應到我們程式裡定義的那個變數（例如 `fb` 是否已包含 popup），對不上要在程式碼註解與 `docs/fields.md` 中記錄差異與原因

## 開發命令

### 本機預覽網站

```bash
python -m http.server 8000 --directory dist
# 開啟 http://localhost:8000
```
> The http server will always launch on port 8000 while developing, **DONOT** launch another server

### 主要指令總覽

所有指令都透過 `build.py` 的子命令執行:`python build.py <command> [flags]`

| 指令 | 用途 |
|------|------|
| `sync` | 完整歷史同步:抓取「所有球員」(含已退休)「所有年份」的資料。用於第一次建置或完整回補歷史資料。 |
| `statcast` | 抓取所有尚未處理過的比賽 playByPlay,計算 Statcast 進階數據(FIP、球種變化量等)。讀取 `game_logs` 資料表。 |
| `refresh` | 每日執行的標準流程:更新當季數據 → 同步 Statcast → 建置 HTML。日常更新最快的方式。 |
| `build` | 直接用現有 SQLite 資料庫產生 HTML,不動任何資料。資料已同步時,用來快速重新產生網站。 |
| `all` | 第一次建置專用:等同 `refresh --full-history`(sync → statcast → build)。 |

### 常用 flag

- `--player <MLB_ID>`:只處理單一球員(`sync` / `statcast` / `refresh` 適用;`all --player` 只會限定 sync/statcast,build 仍會渲染整個 roster)
- `--full-history`:強制重抓過去球季的逐球員資料(game logs、seasonAdvanced、已退休球員、sabermetrics、expectedStatistics)(`statcast` / `refresh` 適用;`sync` / `all` 自動帶入)
- `--update-constants`:強制重抓過去球季的聯盟常數(MLB 投手 FIP 常數/lgERA、tjstats.ca wRC+ 常數),而非用快取值(`statcast` / `refresh` / `build` / `all` 適用)

外部逐年資料的預設規則:當季(`constants.SEASON_YEAR`)每次重抓;過去球季成功抓過一次就沿用(登記在 `season_fetches` 表),只有上面兩個 flag 會強制重抓。
- `--output <dir>` / `--base-url <url>`:輸出目錄與網站 base URL,預設 `dist` / `/`(`refresh` / `build` / `all` 適用)
- `--site-url <url>`:canonical/sitemap/JSON-LD 用的對外正式網址,預設 `constants.SITE_URL`;CI 由 `actions/configure-pages` 自動帶入(`refresh` / `build` / `all` 適用)

其餘參數(`--db`、`--roster`)平常用不到,維持預設即可。要模擬其他球季請設環境變數 `DEFAULT_SEASON_YEAR`。

### 測試

```bash
python -m pytest tests/
```

涵蓋 `site_builder/api`、`site_builder/levels.py` 以及 `sync` pipeline
(`tests/test_api.py`、`tests/test_levels.py`、`tests/test_sync.py`、`tests/test_helpers.py`)。


## 檔案架構

```
build.py              CLI 進入點(argparse,對應 sync/statcast/refresh/build/all)
site_builder/
  constants.py, levels.py, roster.py, positions.py   共用常數與單一權威表(賽事層級、名冊狀態、守位角色)
  api/                打 MLB Stats API + tjstats.ca 爬蟲,只回傳 dict
  sync/               抓資料 → 寫入 SQLite(players.py、statcast.py 等)
  stats/              純數據計算函式,一檔一個 compute_* 函式
  db/                 SQLite schema、查詢、快取
  graph/              圖表用資料(球路移動、Plinko)
  render/              讀 DB → 轉換資料 → 用 Jinja2 產出 dist/ 底下的 HTML
  util/               不依賴其他模組的工具函式
src/
  templates/          Jinja2 樣板
  static/             CSS / JS
  data/roster.json    追蹤球員名單
tests/                pytest,對應 site_builder 各模組
data/tracker.sqlite3  SQLite 資料庫(不進 git)
dist/                 build 產出的靜態網站
```

依賴方向由上往下單向:`util` → `constants/levels/roster/positions` → `api` → `stats` → `db/graph` → `sync/render`,下層不會 import 上層。

## 重要文檔
**若有以下查詢需求，確保先看文檔，不要直接用bash搜尋**

* `docs/api/api_endpoint.md` 裡可以看到所有可用的 api 端點
* `docs/functions_list.md` 包含 `site_builder/` 內所有檔案的function
* `docs/db_schema.md` 可看到資料庫的每張表以及所有數據
* `docs/fields.md` 可看到所有數據欄位與尚未被下游程式碼使用的數據
* `docs/data_sources.md` 可看到每個外部資料來源（API 端點/欄位路徑）與程式碼使用處的對照
* `docs/withmetrics_field_reference` 可看到 /withMetrics 端點的所有資料欄位與資料豐富度
* `docs/custom_domain.md` 更換網域（購買自訂網域）時的完整檢查清單；網址/頁面路徑的單一來源規則


## Code Comments Protocol
* 註解請使用繁體中文撰寫，並與現有程式碼風格保持一致。
* 註解內**禁止使用任何表情符號或圖示字元**。需要標示嚴重性或注意事項時，應使用標準文字前綴
* **數據統計檔案**（`stats/**`）：模組 docstring 的第一行格式為 `NAME — meaning: formula`。後續請註明任何與 FanGraphs / Savant 不同的分母設定、邊界情況（edge-case）或資料來源選取，並說明原因。
* **註解要解釋「為什麼」，而非「做什麼」**：說明 API 的特殊行為（quirks）、MLB 規則細節以及不同時代的差異（例如 2021 年以前的層級名稱）。不要重複描述程式碼本身已經表達的內容。
* **非區域性影響（Non-local effects）**：若某個數值寫入後在後續會被覆寫，或是依賴於其他地方的處理步驟，請在註解中明確指向該位置（例如：`# overwritten below by the level/team UPDATE`）。
* **外部資料**：在使用處指明端點（endpoint）或欄位路徑（例如：`rosterEntries[0].status.code`），以便能回溯至 `docs/data_sources.md`。
* **盡力而為的備援處理（Best-effort fallbacks）**：每個 `return None` 或預設回傳空值的地方，都必須用一行註解說明對應的情境（如：資料缺失、分母為零、API 呼叫失敗）。
* **魔術數字（Magic numbers）**：門檻值或常數皆需標註來源或使用理由。年度數值應統一放在 `constants.py` 中，而非直接寫死在程式碼內（inline）。
* **切勿**留下被註解掉的程式碼、變更紀錄（change logs），或未指明負責人與條件的 `TODO`（請改由 git history 來追蹤）。
* 修改程式邏輯或行為時，務必同步更新或刪除已過時的註解。錯誤的註解比沒有註解更糟糕。

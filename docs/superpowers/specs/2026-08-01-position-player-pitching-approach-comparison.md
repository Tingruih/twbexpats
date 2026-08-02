# 野手代投排除 — 兩個解法的比較與實測

> **這份文件的定位**：討論記錄，**尚未拍板**。
>
> 起因是對 `2026-07-31-vs-pitch-types-atypical-exclusion-design.md`（以下稱「方案 A」）
> 的三點不滿：成本太大、不好維護、沒有完整解決問題。本文件記錄重新檢視的過程、
> 一個新的替代解法（「方案 B」），以及兩者的實測對比。
>
> 文中所有數字都是對 `data/tracker.sqlite3` 全庫實測、或對 MLB Stats API 實查的結果。
> 附錄列出可重跑的查詢。
>
> **短打排除的部分不在本文件的爭議範圍**，沿用方案 A 的設計（欄位都已在庫裡，
> 規則單純，兩個方案都相容）。

---

## 0. 討論過程中改變的前提

三個前提在討論中被修正，先記下來，否則後面的比較會看不懂：

1. **球速規則（方案 A 的 R4）刪除。** 決定不使用球速當作判定依據。
2. **決策 #3「不回填」的原意被澄清**：意思是「不要寫刪除舊資料或回補資料庫的程式碼」，
   而不是「歷史資料不能有這個欄位」——資料庫會另外整個重抓一次。
   → 方案 A 的「新欄位只對之後新抓的比賽生效」這個限制**不存在**，比較必須在
   「已全量重抓」的前提下進行。
3. **決策 #2「不新增 API 呼叫 / 不新增快取表」是希望盡量維持，但不是硬性**。
   第一要求是完美解決問題。

---

## 1. 問題規模（實測修正）

方案 A 引用的「全庫 63,635 顆有球種、能進表的球」是**投手列 + 打者列的總和**。
但 `vs_pitch_types` / `vs_pitch_groups` / `usage_by_count` 這三張表只吃**打者列**。

| 量 | 數字 |
|---|---|
| 全庫 pitch 總數（所有列） | 326,990 |
| 打者列 pitch 數 | 115,499 |
| 打者列中**能進表**的球（有有效 `pitch_type`） | **14,413** |
| 這些球來自幾位投手 | **1,370** |
| (投手, 球季) 組合 | **1,739** |
| (投手, 球季, 層級) 組合 | **1,750** |
| 層級分布 | MLB 789 / AAA 617 / A 250 / ROK 94 |
| 涵蓋球季 | 2007–2026（16 季） |

**需要做「是不是野手代投」判定的對象只有 1,370 位投手 / 1,750 個組合。**
這個數字是後面所有成本論證的基礎。

---

## 2. 方案 A：boxscore 逐球欄位（原設計）

### 2.1 「不新增 API 呼叫」為何成立 — 已實查驗證

`sync/statcast.py:59` 對每場比賽已經呼叫 `get_game_play_by_play()`，打的是
`GET /api/v1/game/{pk}/withMetrics`（`api/games.py:18`）。

實查 gamePk 807678，該回應 **1.66 MB**，結構：

```
gameData   → game, datetime, status, teams, players ← 含 primaryPosition
             venue, weather, gameInfo, ruleSettings, ... (16 個節點)
liveData   → plays          ← 只有這塊被 extract.py 讀
             linescore
             boxscore       ← 含 allPositions / battingOrder / seasonStats
             decisions, leaders
```

現有程式碼只讀兩小塊：`extract.py` 讀 `liveData.plays.allPlays`，
`sync/statcast.py:65` 讀 `gameData.teams.home.sport`。
**`liveData.boxscore` 與 `gameData.players` 已經下載、已經被 `json` 解析成 dict、
已經在記憶體裡，只是沒有任何一行程式碼碰它。**

所以方案 A 的七個新欄位是「多讀已經在手上的 JSON」，網路請求數 0 增加。
這個論證正確，沒有高估。

**連 Rookie 層級都齊全**（gamePk 807678 就是 ROK）：`gameData.players` 72 人含
`primaryPosition`；`boxscore.teams[side].players[]` 有 `allPositions`、`battingOrder`、
`seasonStats.batting/pitching.gamesPlayed`；`teams[side].pitchers[0]` 也在。

### 2.2 代價轉移到哪裡

資訊是**逐場**拿到的，但要在 `stats/` 層用得到，就必須存進 `pitches_json`——
那是唯一的逐球持久化管道。於是「不新增 API 呼叫」的代價變成**每一顆球多背 8 個欄位**：

```python
"pitcher_role": {
    "is_sp": True, "game_pos": ["4","1"], "bo": "301", "dh": True,
    "s_bg": 8, "s_pg": 1, "pos": "6", "pos_asof": "2026-07-31",
}
```

實測：序列化後每球約 **126 bytes** × 326,990 顆球 = **+39 MB（+7.1%）**
（`pitches_json` 目前 551 MB，DB 檔 587 MB）。

倍率上這是把一個 per-(投手, 球季) 的事實複製 570 倍，但**絕對值 39 MB 不是災難，
不足以單獨當作否決理由**。

### 2.3 判定規則（已刪除球速 R4）

按證據強度排序，先命中先決定：

| # | 條件 | 判定 |
|---|---|---|
| R0 | `is_sp` 為真，**或** `s_pg >= 5` | 不排除 |
| R1 | `game_pos` 含 `2`–`9` 的守備位置 | 排除 |
| R2 | `dh` 且 `bo` 非空 且 `s_pg < 5` | 排除 |
| R3 | `s_bg > s_pg` 且 `s_pg < 5` | 排除 |
| R5 | `pos` 非 `1`/`Y` 且 `\|pos_asof − 比賽日\| < 1 年` | 排除（**會過期**） |
| R6 | 以上皆無 | 不排除 |

---

## 3. 方案 B：per-(投手, 球季) 球季檔案表

### 3.1 核心觀察

R0 / R2 / R3 真正在問的是**「這位投手在這個球季是投手還是野手」**——
這是 per-(投手, 球季) 的事實，不是 per-pitch 的事實。而它可以直接向 statsapi 批次查。

### 3.2 資料層

新增一張表：

```sql
CREATE TABLE pitcher_season_profile (
    player_id  INTEGER NOT NULL,
    season     INTEGER NOT NULL,
    g_pitch    INTEGER NOT NULL DEFAULT 0,   -- 該季投球出賽場次（跨層級合計）
    gs         INTEGER NOT NULL DEFAULT 0,   -- 該季先發場次
    g_bat      INTEGER NOT NULL DEFAULT 0,   -- 該季打擊出賽場次
    fetched_at TEXT NOT NULL,
    UNIQUE(player_id, season)
);
```

抓取端點（**實查可用，MLB 與 MiLB 皆通**）：

```
GET /api/v1/people
    ?personIds=<最多 100 人，逗號分隔>
    &hydrate=stats(group=[hitting,pitching],type=yearByYear,sportId=<N>)
```

一次回 100 位球員的**整個生涯逐年**投打場次。

**注意事項（實測踩到的坑）**：

- `type=yearByYear` **不指定 sportId 時只回 MLB**。Ismael Munguia（AAA 野手代投）
  在不帶 sportId 的查詢下完全沒有資料。
- `sportIds=[1,11,...]`（複數）**不支援**，實測回傳空 stats。必須每個 sportId 各查一輪。
- 因此需要跨層級各查一輪後**合併成該球季的總計**。這一步是必要的，因為存在
  「AAA 打擊 91 場、MLB 只上來代投一次」這種跨層級組合，只查單一層級會判錯。
- sportId：MLB=1, AAA=11, AA=12, A+=13, A=14, A-=15, ROK=16（見 `site_builder/levels.py`）。

**實測抓取成本**：1,370 位投手 × 7 個 sportId ÷ 100 人一批 = **98 次 API 呼叫，
63 秒跑完**。之後每天 `refresh` 只需查差集中新出現的投手（實務上每天 0–3 次）。

### 3.3 判定規則：兩條

| # | 條件 | 判定 |
|---|---|---|
| P0 | `gs > 0`（該季先發過） | 不排除 —— 真投手，含兩刀流 |
| P1 | `g_bat > 2 × g_pitch` | **排除** —— 野手代投 |
| P2 | 其他 | 不排除 |

沒有球速、沒有 `primaryPosition`、沒有會過期的欄位、沒有需要校準的絕對門檻、
沒有自我校準的球速下限、沒有稽核 log。

P0 是兩刀流的完整解（Ohtani 2025：打 158 場 / 投 14 場、**GS=14** → 一眼出局），
同時擋掉所有先發投手。P1 用**比例**而非絕對場次，因此不需要「本季已投 N 場」
這類需要校準的魔術數字（為什麼這很重要，見 §5.2）。

**P1 的 `2×` 係數尚未定案**，見 §8 未決事項。

---

## 4. 決定性實驗：9 個真實案例的對比

### 4.1 全庫掃描出的野手代投（方案 B 的判定結果）

用球季檔案跑全庫 1,750 個組合，判定分布為 `pitcher: 1730 / POSITION_PLAYER: 9`，
**查無球季檔案 0 筆**（100% 覆蓋，回溯到 2007 年）。

| 球員 | primaryPos | 球季 | G投 | GS | G打 | 可進表球數 |
|---|---|---|---|---|---|---|
| Ismael Munguia | LF | 2025 | 2 | 0 | 91 | 5 |
| Jose Rojas | 3B | 2025 | 1 | 0 | 124 | 4 |
| Christian Bethancourt | C | 2026 | 2 | 0 | 120 | 4 |
| Jace Peterson | 2B | 2018 | 1 | 0 | 193 | 4 |
| Onix Vega | C | 2026 | 2 | 0 | 10 | 3 |
| Rodolfo Castro | SS | 2025 | 1 | 0 | 133 | 3 |
| Eric Yang | C | 2025 | 8 | 0 | 34 | 3 |
| Tanner Schobel | SS | 2026 | 4 | 0 | 69 | 2 |
| J.T. Arruda | SS | 2025 | 5 | 0 | 79 | 2 |

分離度乾淨：被判為野手的 `g_bat` 是 10–193，真投手幾乎清一色 `g_bat = 0`。

### 4.2 同樣 10 場比賽，跑方案 A 的規則（已重抓、已刪球速）

實查每場的真實 boxscore，套用 R0–R6：

| 球員 | 日期 | 球數 | is_sp | game_pos | bo | dh | s_bg | s_pg | pos | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|
| Ismael Munguia | 2025-05-18 | 5 | False | `['1']` | None | True | 40 | 1 | 7 | R3 ✓ |
| Jose Rojas | 2025-05-15 | 4 | False | `['7','1']` | 500 | True | 34 | 1 | 5 | R1 ✓ |
| Christian Bethancourt | 2026-06-03 | 4 | False | `['1']` | None | True | 35 | 1 | 2 | R3 ✓ |
| Jace Peterson | 2018-09-26 | 4 | False | `['4','1']` | 201 | True | 92 | 1 | 4 | R1 ✓ |
| Onix Vega | 2026-04-25 | 3 | False | `['1']` | None | True | 7 | 2 | 2 | R3 ✓ |
| Rodolfo Castro | 2025-09-04 | 3 | False | `['1']` | None | True | 117 | 1 | 6 | R3 ✓ |
| **Eric Yang** | **2025-09-11** | **3** | False | `['1']` | None | True | 28 | **5** | 2 | **R0 ✗ 漏抓** |
| **Tanner Schobel** | **2026-03-31** | **2** | False | `['1']` | None | True | **1** | **1** | 6 | **R5 ✓（靠會過期的規則）** |
| J.T. Arruda | 2025-08-21 | 1 | False | `['1']` | None | True | 53 | 2 | 6 | R3 ✓ |
| J.T. Arruda | 2025-08-24 | 1 | False | `['10','1']` | 700 | True | 55 | 4 | 6 | R2 ✓ |

**結果：方案 A 重抓後 9/10 命中，漏 1 場；其中 1 場依賴會過期的 R5。方案 B 10/10。**

覆蓋率差距很小。**所以完整性不是真正的分歧點**，下一節才是。

---

## 5. 真正的分歧點

### 5.1 兩者處理「野手↔投手轉換」的差別

**方向 A：野手轉投手。** 資料庫裡的真實案例 **Ruben Salinas（693730）**，
`primaryPosition` 至今仍是 **CF**，但 2025 球季投 21 場、打擊 0 場——他是轉投手的外野手。
2025-07-16（gamePk 807678, ROK）對我們的打者投了 3 顆有球種的球（75.8 / 90.3 / 89.5 mph）。

實查那場的原始欄位：

| 欄位 | 值 |
|---|---|
| `primaryPosition` | **CF (code 8)** ← 會過期的那一個 |
| `allPositions` | `['1']`（當場只守投手） |
| `battingOrder` | `None` |
| `s_bg` / `s_pg` | 0 / **10** |
| `pitchers[0]` | 695256（不是他，非先發） |

- **方案 A**：R0 第二條件 `s_pg = 10 >= 5` 成立 → 不排除 ✓ **判對了**。
  但保護是條件性的：同一個人在該季**第 1–4 次登板**時 `s_pg < 5`，R0 不命中、
  R1 只守投手不命中、R2 無打序不命中、R3 `s_bg(0) > s_pg` 不成立
  → 落到 **R5：`pos`=CF 非 1/Y，`pos_asof` 距比賽日不到一年 → 排除 → 誤判**。
- **方案 B**：2025 球季 `g_pitch=21, gs=0, g_bat=0` → P1 的 `0 > 42` 不成立
  → 不排除 ✓，**與登板序無關**。

**方向 B：投手轉野手**（設計文件舉的 Rick Ankiel，`primaryPosition` 現在是 CF）。

- **方案 A**：先發場次靠 R0 第一條件保護 ✓。純後援登板且該季 `s_pg < 5` 時，
  R1–R3 全不命中 → R5 看到 `pos`=CF → **排除 → 誤判**。唯一的救援是
  `pos_asof` 距比賽日超過一年就放棄 R5。Ankiel 2000 年的比賽因為離現在夠遠而被
  **偶然**保護；一個**今年**才轉野手的投手，他去年的比賽落在一年內，就沒有保護。
- **方案 B**：該球季 `gs > 0` → P0 不排除 ✓；純後援年份 `g_bat = 0` → P1 不成立
  → 不排除 ✓。

**根本差異**：方案 A 是用「這個人**現在**是什麼」去推論「他**當時**是什麼」。
`pos_asof` 能記錄快照的觀測日期，但無法把快照換算回比賽當天——它只讓你知道推論有多舊。
一年有效期等於在「快照離比賽多遠」上下賭注，可是**轉換發生的時機跟這個距離無關**。
方向甚至是反的：一個 2025 年轉投手的人，2025 年的比賽離 2026 年的快照只差幾個月、
穩穩落在有效期內，卻正好是快照最不可信的區間。**距離越近，R5 越危險**；距離遠的
（Ankiel 2000）反而被自動放棄。**保鮮期在最需要它的地方失效。**

這個 trade-off 無解，因為 `primaryPosition` 這個欄位根本不帶時間維度。

方案 B 的時間軸天然對齊：問的就是「他**那一年**是什麼」。轉換自動被球季邊界切開——
Anthony Gose 2013 是打 52 場的外野手、2021–22 是投 6 場和 22 場的投手，同一個
`player_id` 兩組不同的列，不需要任何有效期判斷。

### 5.2 R0 的絕對門檻在 MiLB 已經失效，而且沒有安全值

**Eric Yang 那場 `s_pg = 5`，剛好觸到 R0 的門檻 → 判為「已建立的後援投手」→ 漏抓。**

門檻 5 是原設計從 2024 年 MLB 資料校準的（該年 MLB 野手代投單季最多 4 場）。
但 MiLB 的野手代投頻率明顯更高：Eric Yang 8 場、J.T. Arruda 5 場、Tanner Schobel 4 場。

**這個門檻沒有安全值**：往上調到 10，就會把全季只投 3–9 場的真後援投手踢出 R0 的保護
（庫裡有 30 位這種人，例如 Orion Kerkering 6 場、Connor Brogdon 9 場、Nick Neidert 4 場，
`g_bat` 皆為 0），讓他們去依賴 R5。兩個區間重疊：**野手代投可以投 8 場，
真後援投手可能只投 3 場。用絕對場次去切一個重疊的分布，沒有正確答案。**

方案 B 用比例（`g_bat` vs `g_pitch`）而非絕對場次，不受這個重疊影響：
Eric Yang 是 8 投 / 34 打，Orion Kerkering 是 6 投 / 0 打——兩個維度完全分開。

### 5.3 `seasonStats` 是 running total，賽季初期趨近於零資訊

§5.2 那條**可以修**：把 R0 第二條件從 `s_pg >= 5` 改成比例判斷
（`s_bg == 0 or s_pg > s_bg`），Eric Yang 就會落到 R3 被抓到。改一行。

修好之後剩下的才是本質差異——**實測證據是 Tanner Schobel**：

> 2026-03-31，開季第二天，`s_bg = 1`、`s_pg = 1`。
> R3 的 `s_bg > s_pg` → `1 > 1` 不成立，**比例判斷在這裡完全失效**，
> 於是他只能靠 **R5**（會過期的 `primaryPosition`）命中。

球季檔案看到的是 `g_bat = 69 / g_pitch = 4`，乾淨命中，不需要碰 R5。

`seasonStats` 是「當場為止的累計」，賽季前兩三週的資訊量趨近於零。而
**`refresh` 每天都在跑，賽季初期正是它最常運作的區間**。

三點串成一條線：**方案 A 的弱點全部集中在賽季初期，而那既是它資訊最少的時候，
也是 `primaryPosition` 最不可信的時候（Salinas 的風險窗口同樣落在賽季初期的前 4 次登板）。**

球季總計是**後見之明**：賽季結束後回頭看，一個打 69 場的人投 4 場，永遠是同一個答案。
當季進行中的 profile 每天 refresh 會逐漸收斂，而且收斂方向是安全的
（一開始判不出來 → 不排除，比誤排除好）。

---

## 6. 成本比較

| 項目 | 方案 A（boxscore 逐球） | 方案 B（球季檔案表） |
|---|---|---|
| 判定規則數 | 5 條（R0–R3, R5）+ 順序性 | **2 條**（P0, P1） |
| 需要校準的門檻 | `s_pg >= 5`（實測已失效）、`pos_asof` 一年有效期 | P1 的比例係數（一個） |
| 會過期的欄位 | 有（`primaryPosition`，需 `pos_asof` + 保鮮期） | **無** |
| 新增 API 呼叫 | **0** | 一次性 98 次（63 秒），之後每天 0–3 次 |
| 新增資料表 | 0 | 1 張（1,750 列 / 68 KB） |
| `pitches_json` 增量 | **+39 MB（+7.1%）** | 0 |
| `sync/extract.py` 改動 | ~+60 行（建 role 查表） | **0 行** |
| 10 場實測命中 | 9/10（1 場靠會過期的 R5） | **10/10** |
| 賽季初期表現 | 退化到依賴 `primaryPosition` | 不受影響 |
| 外部依賴 | 無新增（自我包含） | 多一個端點、一張表 |

### 方案 B 的改動清單（估計）

| 檔案 | 動作 | 行數 |
|---|---|---|
| `site_builder/api/pitcher_profiles.py` | 新增：批次 hydrate 抓取 | ~45 |
| `site_builder/db/schema.py` | 新增一張表 | ~10 |
| `site_builder/db/pitcher_profiles.py` | 新增：讀寫 + 差集查詢 | ~50 |
| `site_builder/sync/pitcher_profiles.py` | 新增：掃 game_logs → 差集 → 批次抓 → 寫入 | ~60 |
| `site_builder/stats/core/atypical.py` | 新增：野手代投 2 規則 + 短打 2 規則 + 統一入口 | ~90 |
| `stats/tables/vs_pitch_types.py`、`usage_by_count.py` | 各加一行過濾 | ~6 |
| `stats/batter_statcast.py` | 傳入 profile 查表 | ~5 |
| `build.py` | 掛進 `refresh` / `statcast` | ~10 |
| `tests/` | 3 個測試檔 | ~150 |

**`sync/extract.py` 與 `pitches_json` 完全不動。**

---

## 7. 結論與建議

**建議走方案 B（球季檔案表）。**

理由不是覆蓋率（9/10 vs 10/10，差距很小），而是：

1. **方案 A 的三個弱點全部集中在賽季初期**，而 `refresh` 每天在跑，那正是它最需要工作
   的時候（§5.3）。
2. **R0 的絕對門檻沒有安全值**，因為野手代投與真後援投手的出賽場次分布在 MiLB 是重疊的
   （§5.2）。方案 B 用比例判斷，兩個維度天然分開。
3. **維度正確。** 「這個人在這個球季是投手還是野手」本來就是 per-(投手, 球季) 的事實。
   今天複製到每球的代價是 39 MB，可以接受；但這個排除框架設計上就是要擴充的（決策 #4），
   而未來會想加的東西（季後賽/表演賽、比分懸殊程度、投手當天狀況）大多也不是 per-pitch
   的事實。每加一個就往 pitch dict 塞一組欄位，`pitches_json` 會持續膨脹，
   `extract.py`（已 438 行）會逐漸變成什麼都要知道的上帝函式。

**方案 A 最強的反方論點**（不是安慰獎，是真的工程優點）：**不新增外部依賴**。
多一個端點、多一張表，就多一個會壞、會過期、會需要 migration 的地方；而方案 A 的資料
是自我包含的——判定一場比賽只需要那場比賽的 JSON，不需要跨表 join。

不採納的理由是：**這個自我包含只在資料完整時成立，而 `seasonStats` 在賽季初期本來就不完整**
（§5.3）。自我包含的前提被資料本身推翻了。

### 如果最後決定走方案 A，需要的最小修正

1. **R0 第二條件改成比例式**（`s_bg == 0 or s_pg > s_bg`），否則 Eric Yang 這類 MiLB
   案例會持續漏抓。
2. **明確接受「賽季前兩三週的判定依賴 `primaryPosition`」**，並在那段期間加稽核 log。
   注意：球速已刪，會失去唯一的交叉驗證手段，所以這個 log 只能記錄「走到 R5」的次數，
   **無法判斷對錯**。

### 一個混合選項（討論中提過但未展開）

先走方案 B，若日後稽核發現灰色地帶變多，再單獨加一張
`(game_pk, pitcher_id) → 當場守位 / 打序` 的小表補強——同樣不必碰逐球資料。
以目前實測結果（10/10、0 筆無檔案）看，**現在不需要**。

---

## 8. 未決事項

1. **P1 的比例係數。** `g_bat > 2 × g_pitch` 抓到 9 人；`g_bat > g_pitch` 會多抓
   Edinson Duran（702750, C, 2026, 投 5 場 / 打 6 場, 5 顆球）。Duran 是轉換中的球員，
   任何規則都無法乾淨切開。需要在實作時把兩種門檻在全庫各跑一次再定案，
   並確認無 DH 年代的後援投手（會有少量打擊出賽）不被誤觸。
2. **當季 profile 的刷新策略。** 完賽球季只抓一次（凍結值）；進行中的球季每次 `refresh`
   重抓。需要用 `fetched_at` + `season` 判斷。
3. **短打排除**沿用原設計（`BUNT_PA` / `BUNT_PITCH` 兩種粒度），本文件未重新檢視。
4. **兩個硬性順序限制**沿用原設計 §6：過濾必須在 `ensure_pre_strikes()` 之後；
   跨球的聚合必須在 `compute_pitch_splits` 切分手別之前。
5. **UI 註記**：排除只影響三張表，同頁的整體 Statcast 摘要不變，因此各列 `count` 加總
   不等於摘要的 `total_pitches`。沿用原設計 §8.4 的判斷，需要在 UI 加說明。

---

## 9. 附錄：實測證據與可重跑的查詢

### A. 判定需求範圍

掃 `game_logs`，只取 `pitches[0].batter_id == player_mlb_id` 的列（打者列），
再濾掉 `pitch_type` 為空或屬於 `{UN, AB, AS, IN, PO, NP}` 的球，
統計 distinct `(pitcher_id, season, sport_level)`。
→ 1,750 組合 / 1,370 位投手 / 14,413 顆球。

### B. 球季檔案抓取（實跑 98 次呼叫 / 63 秒）

```
GET https://statsapi.mlb.com/api/v1/people
    ?personIds=<最多100人>
    &hydrate=stats(group=[hitting,pitching],type=yearByYear,sportId=<N>)
```

對 sportId ∈ {1, 11, 12, 13, 14, 15, 16} 各跑一輪，把同一 `(player_id, season)`
的 `gamesPlayed` / `gamesStarted` 跨層級加總。

實查驗證：
- Ohtani（660271）2025：hitting G=158 / pitching G=14 GS=14 → P0 不排除 ✓
- Munguia（665998）2025 sportId=11：hitting G=91 / pitching G=2 GS=0 → P1 排除 ✓
- Samuel Perez（682840）2022 sportId=14：pitching G=24 GS=0、**無 hitting split**
  （MiLB 有 DH，真投手不打擊）→ P1 不成立，不排除 ✓
- 不指定 sportId 時 Munguia 完全查無資料（`yearByYear` 預設只回 MLB）
- `sportIds=[1,11,...]` 複數形式不支援，回傳空 stats

### C. `withMetrics` 已含 boxscore（gamePk 807678, ROK）

回應 1.66 MB；`gameData.players` 72 人含 `primaryPosition`；
`liveData.boxscore.teams[side].players[]` 含 `allPositions` / `battingOrder` /
`seasonStats.batting.gamesPlayed` / `seasonStats.pitching.gamesPlayed`；
`teams[side].pitchers[0]` 存在。Rookie 層級一樣齊全。

### D. 儲存量測

`pitches_json` 總計 551 MB / 326,990 顆球（DB 檔 587 MB）。
`pitcher_role` dict 以 `separators=(',',':')` 序列化約 126 bytes/球
→ +39 MB（+7.1%）。球季檔案表 1,750 列 × ~40 bytes ≈ 68 KB。

### E. 球速規則失效的證據（本次已刪除球速，記錄備查）

原設計宣稱「野手代投 45.3 mph vs 最慢真投手 74.7 mph，中間 29 mph 空隙，門檻 70 零誤判」。
在**打者實際面對的登板**（≥5 顆有追蹤的球，共 1,505 次）上重跑，排序是：

| 均速 | 最高 | 球數 | 日期 / 層級 | 是誰 |
|---|---|---|---|---|
| 45.3 | 50.2 | 5 | 2025-05-18 AAA | Ismael Munguia（LF，真的野手代投） |
| **66.8** | 84.0 | 7 | 2008-04-27 MLB | **Jeff Francis（P，如假包換的投手）** |
| 74.7 | 82.9 | 7 | 2026-05-17 AAA | Austin Voth（P） |

門檻 70 會把 Jeff Francis 誤判成野手代投。另外，球速規則只能抓到 §4.1 那 9 個案例中的
1 個（Munguia），其餘 8 個都在 70 mph 以上——**漏抓率 89%**。

### F. `primaryPosition` 反向誤判的真實案例

Ruben Salinas（693730）：`primaryPosition` = **CF**，但 2025 球季投 21 場、打擊 0 場。
原設計的 R5 會把他判成野手代投（該場實際上被 R0 的 `s_pg=10` 擋住，
但該季前 4 次登板落在風險窗口內）。方案 B 判為投手 ✓。

全庫中 `primaryPosition` 非 `P`/`TWP` 的只有 11 個 `(投手, 球季)` 組合，
Salinas 是唯一「非 P 但實為投手」的一個。
**即 R5 目前實際誤判 0 次，但那是靠 `s_pg = 10` 這個偶然，不是規則的保證。**

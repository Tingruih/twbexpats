# 打者「非典型打席/投球情境」排除 — 設計文件

> 需求與共識見 `2026-07-30-vs-pitch-types-atypical-exclusion-requirements.md`。
> 本文件處理解法：架構、資料欄位、分類規則、順序性限制、驗證方式。
> 文中所有數字都是對 `data/tracker.sqlite3` 全庫實測或對 MLB Stats API 實查的結果，
> 逐項證據列在附錄。

---

## 1. 核心設計判斷

原需求文件假設「投手的 `primaryPosition` 就是野手代投的判斷依據」。實測發現這個欄位
**會過期**：`gameData.players[].primaryPosition` 是 **API 查詢當下**的生涯快照，不是
比賽當時的狀態。

實查 2013-06-01 藍鳥隊比賽（gamePk 347580）中的 Anthony Gose（543238）：

| 來源 | 值 |
|---|---|
| `gameData.players.ID543238.primaryPosition` | Pitcher (1) ← 他**現在**是投手 |
| `liveData.boxscore...players.ID543238.allPositions` | LF (7) ← 他**當時**守左外野 |

兩個方向都會錯：野手轉投手（Gose）造成漏排除；投手轉野手（Rick Ankiel 現在的
`primaryPosition` 是 CF）造成誤排除。

因此本設計的第一個判斷是：**把訊號分成「會過期」與「不會過期」兩類，主要規則只用
不會過期的訊號，會過期的那一個降級成最後一層並附上觀測日期。**

| 訊號 | 來源 | 過期性 |
|---|---|---|
| 是否為該隊先發投手 | `boxscore.teams[side].pitchers[0]` | 不過期（當場事實） |
| `allPositions` | `boxscore.teams[side].players[].allPositions` | 不過期（當場事實） |
| `battingOrder` + 是否 DH 制 | `boxscore.teams[side]` | 不過期（當場事實） |
| `seasonStats.batting/pitching.gamesPlayed` | `boxscore.teams[side].players[]` | 不過期（當場為止的球季累計） |
| `start_speed` | 已存在於 `pitches_json` | 不過期（物理量測） |
| `primaryPosition` | `gameData.players[]` | **會過期**（抓取當下的生涯快照） |

第二個判斷來自另一個實測事實：**全庫 63,635 顆「有球種、能進表」的球，缺 `start_speed`
的有 0 顆（0.00%）**。`pitch_type` 與 `start_speed` 來自同一套追蹤系統，凡是能進入
`vs_pitch_types` 的球，資料庫裡現在就已經有球速。

→ **球速規則對整個既有歷史立即生效，不需要重抓任何一場比賽。** 這解除了需求文件決策 #3
（不回填）對本功能造成的限制：舊資料不是完全無法處理，只是可用的證據較少。

---

## 2. 架構：三層責任分離

```
extract.py  ──→  只存原始證據（含觀測日期），不做任何判斷
                        │
stats/core/atypical.py ──→  純函式分類器，規則可隨時改、不用重抓資料
                        │
stats/tables/*.py  ──→  每張表宣告自己要套用哪些排除原因
```

分層的理由：分類規則寫在 `stats/` 層代表**規則變更可以回溯套用到已抓的資料**。如果在
抓取層就存算好的布林旗標，日後任何規則調整都得重抓全部比賽。

這也符合 `site_builder/` 既有的分層依賴：`api/` → `stats/` → `sync/`，低層不依賴高層。

---

## 3. 資料層：`sync/extract.py` 新增欄位

`extract_pitch_logs()` 收到的 `game_data` 是完整的 `game/{pk}/withMetrics` 回應，
`liveData.boxscore` 與 `gameData.players` 都在裡面，**不需要新的 API 呼叫**（符合需求
決策 #2）。

在逐 play 迴圈開始前建立一份 `{pitcher_id: role_dict}` 查表（每場只算一次），逐球寫入：

```python
"pitcher_role": {
    "is_sp":    True,          # 是否為該隊先發投手（pitchers[0]）
    "game_pos": ["4", "1"],    # 該場 allPositions 的 code 清單
    "bo":       "301",         # 該場 battingOrder（無則 None）
    "dh":       True,          # 該場是否 DH 制（先發投手不在 battingOrder 裡）
    "s_bg":     8,             # seasonStats.batting.gamesPlayed
    "s_pg":     1,             # seasonStats.pitching.gamesPlayed
    "pos":      "6",           # primaryPosition.code（唯一會過期的欄位）
    "pos_asof": "2026-07-31",  # 觀測日期
}
```

`extract_pitch_logs()` 的 `role` 參數為 `"pitcher"` 時（被追蹤的球員自己是投手），這份
資料描述的就是他本人、下游不會用到；為了保持單一寫入路徑，兩種 role 一律照寫。

採用巢狀 dict 而非平鋪欄位，與既有的 `defense` / `offense` 一致。逐球重複儲存雖然冗餘，
但 pitch dict 本來就已經高度反正規化（`defense` 每球都存 9 個守備球員 id），改成每場一
份會需要把 game → pitcher → role 的對照表穿過每一個 table 函式的簽名，代價更大。

### `pos_asof` 的用途

這是本設計把「欄位會過期」這件事**明確化**的方式。`pos` 的語意是「在 `pos_asof` 這天觀
測到的生涯守位」，分類器據此判斷可不可信（見 R5）。沒有這個欄位的話，未來若為了別的
需求清空 `pitches_json` 重抓（`sync/statcast.py` 的 `hit_coord_checked` 就是這種前例），
十幾年前的比賽會被靜默貼上重抓當下的守位而無從察覺。

`extract.py` 需要加註解說明這個不變量，比照 `y0` 欄位既有的註解寫法。

---

## 4. 分類層：`stats/core/atypical.py`

### 4.1 排除原因與粒度

```python
class Reason(StrEnum):
    POSITION_PLAYER_PITCHING = auto()   # 粒度：PA
    BUNT_PA                  = auto()   # 粒度：PA
    BUNT_PITCH               = auto()   # 粒度：pitch
```

粒度是框架的第一等概念，未來新增原因時必須指定。PA 粒度的原因會排除整個打席的所有球，
pitch 粒度只排除單顆球。

對外只有一個入口：

```python
def exclude_atypical(pitches: list[dict], reasons: Collection[Reason]) -> list[dict]
```

### 4.2 野手代投的判定

按證據強度排序，**先命中先決定**：

| # | 條件 | 判定 | 過期性 |
|---|---|---|---|
| R0 | `is_sp` 為真，**或** `s_pg >= 5` | **不排除** | 不過期 |
| R1 | `game_pos` 含 `2`–`9` 的守備位置 | 排除 | 不過期 |
| R2 | `dh` 且 `bo` 非空 且 `s_pg < 5` | 排除 | 不過期 |
| R3 | `s_bg > s_pg` 且 `s_pg < 5` | 排除 | 不過期 |
| R4 | 該次登板均速 `< POSITION_PLAYER_MAX_VELO` 且該登板球數 `>= 5` | 排除 | 不過期，**唯一對舊資料生效** |
| R5 | `pos` 非 `1`/`Y` 且 `\|pos_asof − 比賽日\| < 1 年` | 排除 | 會過期（已由 asof 鎖住） |
| R6 | 以上皆無 | 不排除 | — |

**R0 第一個條件是兩刀流的完整解。** 兩刀流球員投球幾乎必然是先發，野手代投永遠不會是
先發投手。Ohtani 靠 R0 就結案，完全不需要碰會過期的 `primaryPosition`，也不需要維護一份
兩刀流名單。

**R0 第二個條件保護後援投手不被 R1 誤傷。** 真投手偶爾會在延長賽的守備調度中先移到外野
再回來投球，此時 `game_pos` 會是 `['1', '7']` 而觸發 R1。用「本季已投 5 場以上」把已建立
的後援投手擋在前面。

`s_pg` 的門檻 5 同時用在 R0、R2、R3，用來區分「球季內反覆代投的野手」與「真正的投手」。
實測 2024 年全 MLB 53 位野手代投中，單季代投場次最多的是 4 場（Enrique Hernández、
Jake Bauers、Emmanuel Rivera），門檻 5 有安全邊際；同期真投手的 `s_pg` 實測為 3–56。

三條 `s_pg` 相關規則在舊資料（無 `pitcher_role`）上一律放棄，直接落到 R4。

**R1 的位置碼**：只認 2–9（捕手到右外野）。刻意排除 `10`（DH）、`11`（PH）、`12`（PR）
——DH 會誤傷同場投球的兩刀流（Ohtani 的 `allPositions` 實測是 `['1', '10']`），而 PH/PR
本身不是守備位置。這些案例由 R2/R3 接手。

**DH 制的判定**：`該隊 pitchers[0] 不在 battingOrder 裡` → DH 制。不用去猜年份與聯盟
規則，也不用找 DH 球員（實測 DH 球員被換下後 `position` 會變成他最後守的位置，用 code
`10` 反查會失準）。

### 4.3 短打的判定

所有需要的欄位**都已經在資料庫裡**，不需要新抓資料。

- **`BUNT_PA`**（打席層級）：打席結果 `pa_event == "sac_bunt"`，或該打席最後一球的
  `trajectory` 屬於 `{bunt_grounder, bunt_line_drive, bunt_popup}` → 排除該打席**所有**球。
- **`BUNT_PITCH`**（單球層級）：`result_code` 屬於 `{M, L, O}`（揮空短打、界外觸擊、
  觸擊界外碰觸，取自 `SWING_CODES` 中的短打子集）但該打席最後不是短打結果 → 只排除
  這幾顆。

`BUNT_PA` 的副作用是**解掉了需求文件裡「take bunt 無法排除」的限制的一大半**：打者擺出
短打姿勢、被投出好球或壞球、後來仍以短打結束打席——這些中途的 take 球會隨整個打席一起
被排除。真正無解的只剩「擺姿勢後縮桿，最後揮棒打出非短打結果」的打席（見 §8）。

### 4.4 登板層級的前置 annotate pass

R4 需要「該次登板的均速」，`BUNT_PA` 需要打席邊界。兩者都是跨球的聚合，但 table 函式
收到的是跨場次攤平的 pitch list。

比照 `core/pitches.py::ensure_pre_strikes` 的既有模式，新增一個原地標註的 pass：
以 `(game_pk, pitcher_id)` 分組算登板均速與球數，以 `is_pa_final` 切打席邊界，把結果寫回
每顆球。冪等，重複呼叫無副作用。

---

## 5. 表格層：宣告式套用

| 表 | 套用的排除原因 |
|---|---|
| `compute_vs_pitch_types` | `POSITION_PLAYER_PITCHING`, `BUNT_PA`, `BUNT_PITCH` |
| `compute_vs_pitch_groups` | 同上 |
| `compute_pitch_group_usage_by_count` | 只有 `POSITION_PLAYER_PITCHING` |
| `compute_batter_pitch_hand_splits` | 自動繼承（它包著上面三個函式） |

**`usage_by_count` 刻意不排除短打。** 這張表算的是「投手在這個球數丟什麼球種」，投手選
球種是在打者出棒**之前**決定的，打者有沒有做短打動作不影響投手的配球決策。排掉只會無故
縮小投手配球的樣本。野手代投則確實會汙染配球分布（球種極端偏斜），所以要排。

**明確不動**（沿用需求文件）：`season_stats` 來源的官方統計、`compute_batter_statcast`
的整體 Statcast 摘要、以及所有投手側的表。

`compute_pitch_plinko` 這次不納入範圍，但框架的 PA 粒度已經為它預留——plinko 畫的是球數
轉移路徑，只能整個打席排除，逐球挖空會破壞路徑。

---

## 6. 兩個硬性順序限制

寫錯不會報錯，只會靜默算出錯的數字：

1. **必須在 `ensure_pre_strikes()` 之後才過濾。** 它靠連續走訪整串球去推算舊資料缺少的
   pre-count（`core/pitches.py:109`），中間被挖空的球會讓後續所有球的 pre-count 推導錯位，
   `usage_by_count` 的球數分桶會跟著全錯。過濾點放在三個 table 函式的入口，此時
   `batter_statcast.py:29` 的 `ensure_pre_strikes` 已經跑完。
2. **登板層級的 annotate pass 要在切分手別之前跑。** `compute_pitch_splits` 會先把 pitch
   list 依 `pitch_hand` 過濾再交給 table 函式；聚合必須在完整清單上算好。

兩點都要寫成註解與測試。

---

## 7. 球速門檻：量測值，不是魔術常數

全庫 2,508 次登板（每次 ≥5 顆有追蹤的球）的實測分布：

| | 均速 | 最高球速 |
|---|---|---|
| 唯一的野手代投（Ismael Munguia, LF） | **45.3** | 50.2 |
| 最慢的真投手（Austin Voth） | **74.7** | 76.0 |

中間有 29 mph 的空隙。初始值 `POSITION_PLAYER_MAX_VELO = 70.0`，在現有全庫是零誤判。

新欄位上線後這個門檻**自我校準**：拿 R0–R3 判定為真投手的所有登板算實測球速下限，門檻
設在下限之下。這與專案處理 FIP 常數與 park factor 的既有做法一致——算出來快取，不手寫。

`statcast` / `refresh` 執行時輸出稽核 log：

- 有沒有登板被 R0 判為真投手、或 R1–R3 皆未命中，卻落在門檻之下（→ 門檻太高）
- 有沒有被排除的登板均速 90+（→ 判錯了）
- 有沒有走到 R5 才命中的案例（→ 這是唯一依賴會過期欄位的路徑，值得留紀錄）

---

## 8. 已知限制

1. **歷史資料中球速落在 70–88 mph 重疊區的野手代投抓不到。** 舊資料只有球速可用，而
   2024 年全 MLB 的野手代投均速範圍是 45.2–78.8，與真投手下緣（74.7）有重疊。實測現況：
   全庫的野手代投只有 1 次且是 45.3 mph，目前漏網數為 0。
2. **新抓比賽的極端組合。** 要同時滿足「非先發 + 當場沒守別的位置 + 沒打序 + 球季累計是
   空的 + 球速在重疊區 + 且他是生涯轉換者」才會漏。前五項在實測中出現過（Nick Pratto，
   當天剛升上大聯盟），第六項才會讓 R5 失效。這個組合可由 §7 的稽核 log 偵測。
3. **非短打結尾打席中途的 take bunt 抓不到。** 打者擺出短打姿勢又縮桿、最後揮棒打出非
   短打結果——逐球資料沒有任何欄位可以辨識這種情況。維持需求文件的原判斷。
4. **排除只影響三張表，同頁的整體 Statcast 摘要不變。** 因此 `vs_pitch_types` 各列的
   `count` 加總不會等於摘要區的 `total_pitches`。這是刻意的（不改寫官方定義），需要在
   UI 上加註說明。

---

## 9. 對既有數據的預期影響

**短打**：欄位已存在，跑 `build.py build` 即對**全部歷史**生效。全庫 428 顆短打動作球
（佔可進表球數 0.67%），其中 214 顆是打席最後一球，打席結果含 **61 支一壘安打**——這些
目前全部算在 `vs_pitch_types` 的 AVG/wOBA 裡。順帶修掉兩個既有偏差：短打進場的 EV 約
30 mph 會拉低 `hard_hit_pct` 的分母，`bunt_grounder`/`bunt_popup` 已被折進
`GB_TRAJECTORIES`/`PU_TRAJECTORIES`。

**野手代投**：新欄位只對之後新抓的比賽生效；舊資料靠 R4（球速）處理，同樣跑
`build.py build` 即生效。

實測案例——李灝宇 2025 AAA 對滑球（唯一受影響的既有資料）：

| | 球數 | AVG | wOBA | hard-hit% |
|---|---|---|---|---|
| 現況 | 399 | .229 | .278 | 30.8% |
| 排除後 | 394 | .221 | .272 | 29.7% |

注意汙染的形式：那 5 顆 42.8–50.2 mph 的慢球被分類器全部標成 **Slider**，沒有自成一列
幽靈球種，而是直接混進他真正的滑球那一列。

---

## 10. 測試計畫

現有 `tests/` 沒有涵蓋 `stats/tables/`，本次一併補上。

**`tests/test_atypical.py`**（新增）

- R0–R6 每條規則各一個 case，用 §11 附錄的真實案例當 fixture
- 兩刀流：`is_sp=True` 必須不排除
- 後援投手臨時守外野再回來投球（`game_pos=['1','7']` 且 `s_pg>=5`）必須不排除
- 真投手（`s_bg=0`、無打序、`game_pos=['1']`、高球速）必須不排除
- `pos_asof` 距比賽日超過一年時 R5 必須放棄
- `BUNT_PA` 必須排除打席中途的 take 球
- `BUNT_PITCH` 不得影響同打席的其他球
- 舊資料（無 `pitcher_role` 欄位）必須退回 R4，且 R4 不成立時不排除

**`tests/test_extract.py`**（擴充）

- `pitcher_role` 七個欄位的擷取正確性，含 boxscore 缺欄位時的降級
- DH 制判定（`pitchers[0]` 在/不在 `battingOrder`）

**`tests/test_vs_pitch_types.py`**（新增）

- 三張表各自套用的原因集合正確（特別是 `usage_by_count` 不排除短打）
- 過濾在 `ensure_pre_strikes` 之後：構造一組缺 pre-count 的舊資料，驗證分桶結果
- `compute_batter_pitch_hand_splits` 正確繼承

---

## 11. 附錄：實測證據

**A. `primaryPosition` 會過期**（MLB Stats API 實查）

- Gose（543238）2013-06-01 gamePk 347580：`gameData` 顯示 Pitcher，boxscore `allPositions`
  顯示 LF
- Ankiel（150449）現在的 `primaryPosition` 是 CF
- Ohtani（660271）：`primaryPosition` = `Y` (Two-Way Player)；2022-04-07 gamePk 661042 的
  `allPositions` = `['1', '10']`

**B. `seasonStats` 是當場為止的累計**（gamePk 745770）

Adam Ottavino 在該場顯示 `pitching.gamesPlayed = 56`，其 2024 球季總計為 60 場 → 確認為
running total。已完成球季的數值不會再變。

**C. 分類規則對 2024 年 20 個野手代投案例的覆蓋**

| 命中規則 | 人數 | 案例 |
|---|---|---|
| R1（當場守過別的位置） | 9 | Castro, Reyes, Rojas, D.Smith, Wisdom, Hernández, Bauers, Tellez, Rivera |
| R2（DH 制卻有打序） | 5 | Bote, Hedges, Mendick, Sanó, Wallner |
| R3（球季累計以打擊為主） | 5 | Alvarez, Cabrera, Kessinger, Knizner, L.Williams |
| R5（最後一層） | 1 | Pratto（當天剛升上大聯盟，`s_bg=0`） |
| 合計 | **20/20** | |

同場的真投手無一誤觸（`s_bg` 皆為 0 或 1，`s_pg` 為 3–56）。

2024 年全 MLB 共 855 名投手，其中 53 名 `primaryPosition` 非 P。

**D. 球種與球速的覆蓋率**（全庫）

| level | 球數 | 有球種 | 有球速 |
|---|---|---|---|
| AA | 70,187 | 0.0% | 0.0% |
| AAA | 66,280 | 23.6% | 23.6% |
| A | 56,584 | 18.4% | 18.4% |
| A+ | 46,683 | 0.0% | 0.0% |
| MLB | 46,629 | 78.9% | 79.1% |
| ROK | 28,067 | 2.9% | 2.9% |
| A(Short) | 12,304 | 0.0% | 0.0% |

有球種的 63,635 顆球中，缺球速的有 **0 顆**。MLB 逐年：2007 年起開始有追蹤（34.1%），
2008 年起 94.6%+，2012 年起接近 100%。未追蹤的球本來就進不了 `vs_pitch_types`。

**E. 短打分布**（全庫，僅計可進表的球）

428 顆（0.67%），其中 214 顆為打席最後一球。

- `result_code`：`L`(界外觸擊) 190、`M`(揮空短打) 34、`O`(觸擊界外碰觸) 0
- `trajectory`：`bunt_grounder` 185、`bunt_popup` 17、`bunt_line_drive` 2
- 打席結果：`sac_bunt` 78、`single` 61、`field_out` 52、`strikeout` 10、其他 13

# 跨層級合計的數據錯誤

驗證日期：2026-07-28
驗證對象：`data/tracker.sqlite3` 全庫（103 名球員、528 筆有 statcast 的 season_stats 列）

> 這份文件只記錄**已經用實際資料驗證過**的錯誤，每一項都附可重現的數字。
> 相關但未在此驗證的項目見 `docs/UNFIXED_BUGS.md`。

---

## 摘要

球員頁的「合計 / All Levels」數據有**兩個彼此獨立**的 bug：

| | 病因 | 影響 |
|---|---|---|
| **Bug A** | 跨層級合併時，所有比率欄位一律用「球種投球數」加權，但各欄位的真正分母不同 | 18 組 (球員, 年度, 表格) 的球種分析數字錯誤，最大誤差 AVG 差 .106、Whiff% 差 30.6pp、轉速差 96 rpm |
| **Bug B** | 同一年度同一層級有多支球隊時，整季 statcast 被複製到每一筆 season_stats 列，合併時重複累加 | 18 組 (球員, 年度) 受影響，張育成 2022 的合計球數是實際的 3.6 倍；另外三張表直接印出 4 列一模一樣的 MLB |

兩者互相獨立：Bug A 在沒有重複列時照樣發生，Bug B 在加權正確時照樣發生。

---

## §1 驗證方法

對每一個有多層級 statcast 的 (球員, 年度)：

1. **目前值**：讀 `season_stats.stat_json.statcast`（各層級已存的聚合），走 production 路徑丟進 `combine_statcast_dicts()` / `combine_pitch_type_data()`
2. **真值**：從 `game_logs.pitches_json` 把該年度所有層級的原始逐球資料池化，直接呼叫 `compute_batter_statcast()` / `compute_pitcher_statcast()` 重算
3. 逐欄位比對，門檻 |Δ| ≥ 0.0011

真值路徑用的是**與單層級完全相同的計算函式**，只是餵進去的球比較多，所以真值不依賴任何新公式，可信度等同單層級數據本身。

驗證 Bug B 時另外做了一次隔離掃描：比較「含重複列的合併」與「去重後的合併」，把重複造成的偏差與加權造成的偏差分開。

---

## §2 Bug A — 跨層級加權用錯分母

### 2.1 病因

`site_builder/stats/tables/weighted.py:56`

```python
for f in rate_fields:
    v = pt.get(f)
    if v is not None:
        bucket["wsums"][f] += v * n      # n = 該球種的投球數
        bucket["wcounts"][f] += n
```

所有 `rate_fields` 共用同一個權重 `n`。但各欄位的分母其實不同：AVG 的分母是 AB、Whiff% 的分母是揮棒數、Barrel% 的分母是有初速的擊球數、平均球速的分母是「有球速資料的球數」。只有 `put_away_pct` 被特別處理（用 `two_strike_count`）。

同樣的問題也出現在 `site_builder/stats/combine.py` 的頂層純量欄位，只是那裡已經有 `_wpct_own_den()` 修好了一部分。

### 2.2 各欄位真分母對照表

**球種表**（`weighted.py`，供 `pitch_arsenal` / `pitch_outcomes` / `vs_pitch_types` / `vs_pitch_groups` 使用）

| 欄位 | 真正分母 | 目前權重 | 判定 |
|---|---|---|---|
| `strike_pct` | 全部球數 | `count` | 正確 |
| `swstr_pct` | 全部球數 | `count` | 正確 |
| `csw_pct` | 全部球數 | `count` | 正確 |
| `put_away_pct` | 兩好球球數 | `two_strike_count` | 正確（已特別處理） |
| `count` / `pct` | 直接加總 | — | 正確 |
| `zone_pct` | 有 zone 資料的球數 | `count` | **錯**，實測 Δ < 0.001 |
| `z_swing_pct` | 好球帶內球數 | `count` | **錯** |
| `o_swing_pct` / `chase_pct` | 好球帶外球數 | `count` | **錯** |
| `whiff_pct` | 揮棒數 | `count` | **錯** |
| `z_whiff_pct` | 好球帶內揮棒數 | `count` | **錯** |
| `avg` | AB | `count` | **錯** |
| `woba` | 有效 PA（`woba_den`） | `count` | **錯** |
| `barrel_pct` / `hard_hit_pct` | 有初速的擊球數（`bbe_ev`） | `count` | **錯** |
| `velo` `ivb` `hb` `spin` `extension` `v_rel` `h_rel` | **該欄位非空的球數** | `count` | **錯** |

最後一列是誤差最大的一類，也最容易被忽略：`mean_round()` 只對非 None 的值取平均，但合併時用整個球種的球數加權。低階層級（ROK、A）常常只有一部分球有轉速／位移資料，那些層級因此被嚴重高估權重。

**頂層純量欄位**（`combine.py`，供 Statcast 概覽 / Plate Discipline / 擊球型態 使用）

| 欄位 | 真正分母 | 目前權重 | 判定 |
|---|---|---|---|
| `swing_pct` `swstr_pct` `csw_pct` `strike_pct` | 全部球數 | `total_pitches` | 正確 |
| `whiff_pct` `z_swing_pct` `o_swing_pct` `z_contact_pct` | 各自分母 | `*_den`（已修） | 正確 |
| `gb_pct` `ld_pct` `fb_pct` `pu_pct` `air_pct` | 進場擊球數 | `bbe` | 正確 |
| `pull_pct` `straight_pct` `oppo_pct` `pull_air_pct` | 進場擊球數 | `bbe` | 正確 |
| `woba` / `woba_against` | 有效 PA | `pa_count`（＝`woba_den`） | 正確 |
| `max_ev` | — | 取各層級最大值 | 正確 |
| `barrel_pct` `hard_hit_pct` `avg_ev` | 有初速的擊球數（`bbe_ev`） | `bbe`（＝所有進場擊球） | **錯** |
| `avg_la` `swsp_pct` | 有仰角資料的擊球數 | `bbe` | **錯** |
| `hr_fb_pct` | 飛球數 | `bbe` | **錯** |
| `avg_extension` | 有 extension 的球數 | `total_pitches` | **錯** |
| `zone_pct` | 有 zone 資料的球數 | `total_pitches` | **錯**，實測 Δ ≤ 0.006 |
| `ev90` | — | `bbe` 加權平均 | **錯，且無法用加權修正** |

`ev90` 是第 90 百分位。百分位不是可加性的統計量，各層級的百分位再怎麼加權平均都還原不出池化後的百分位。要正確只能重算。

### 2.3 實測誤差 — 球種表

全庫掃描出 **18 組 (球員, 年度, 表格)** 受影響：

| 球員 | 年度 | 表格 | 層級 | 最大誤差 |
|---|---|---|---|---|
| 林盛恩 | 2025 | 球種數據 | ROK, A | 轉速 96.4 rpm |
| 鄧愷威 | 2025 | 球種數據 | MLB, AAA | 轉速 0.86 |
| 鄧愷威 | 2024 | 球種數據 | MLB, AAA | 轉速 0.69 |
| 林鋅杰 | 2021 | 球種數據 | ROK, A | 轉速 0.45 |
| 徐基麟 | 2021 | 對戰結果 | ROK, A | Z-Whiff% 30.6pp |
| 徐基麟 | 2021 | 球種數據 | ROK, A | Whiff% 30.6pp |
| 張育成 | 2023 | 對戰球種 | MLB, AA, AAA | Hard-Hit% 23.3pp |
| 林盛恩 | 2025 | 對戰結果 | ROK, A | Hard-Hit% 12.6pp |
| 鄭宗哲 | 2026 | 對戰球種 | MLB, AAA | AVG .106 |
| 李灝宇 | 2026 | 對戰球種 | MLB, A, AAA | O-Swing% 8.4pp |
| 張育成 | 2023 | 分類 | MLB, AAA | Z-Swing% 3.8pp |
| 鄭宗哲 | 2025 | 對戰球種 | MLB, A, AAA | Z-Swing% 3.1pp |
| 鄧愷威 | 2025 | 對戰結果 | MLB, AAA | Hard-Hit% 2.8pp |
| 林鋅杰 | 2021 | 對戰結果 | ROK, A | Hard-Hit% 1.9pp |
| 鄧愷威 | 2024 | 對戰結果 | MLB, AAA | Z-Whiff% 1.7pp |
| 李灝宇 | 2026 | 分類 | MLB, A, AAA | Hard-Hit% 1.3pp |
| 鄭宗哲 | 2026 | 分類 | MLB, AAA | Hard-Hit% 1.2pp |
| 鄭宗哲 | 2025 | 分類 | MLB, A, AAA | AVG .0065 |

各欄位的全域最壞誤差：

```
spin           Δ=96.4     林盛恩 2025 球種數據 CU  n=55 : 2421.4  vs 2325.0
whiff_pct      Δ=0.3056   徐基麟 2021 球種數據 CU  n=9  : 0.5556  vs 0.25
z_whiff_pct    Δ=0.3056   徐基麟 2021 對戰結果 CU  n=9  : 0.5556  vs 0.25
hard_hit_pct   Δ=0.2333   張育成 2023 對戰球種 CU  n=30 : 0.6333  vs 0.4
avg            Δ=0.1058   鄭宗哲 2026 對戰球種 CU  n=65 : 0.2728  vs 0.167
woba           Δ=0.0859   鄭宗哲 2026 對戰球種 CU  n=65 : 0.366   vs 0.2801
o_swing_pct    Δ=0.0837   李灝宇 2026 對戰球種 KC  n=6  : 0.4167  vs 0.333
hb             Δ=0.0837   鄧愷威 2025 球種數據 CH  n=129: 13.8837 vs 13.8
ivb            Δ=0.0780   徐基麟 2021 球種數據 FF  n=41 : 16.422  vs 16.5
velo           Δ=0.0759   鄧愷威 2025 球種數據 CU  n=191: 83.1759 vs 83.1
barrel_pct     Δ=0.0630   林盛恩 2025 對戰結果 CU  n=55 : 0.08    vs 0.143
z_swing_pct    Δ=0.0551   張育成 2023 對戰球種 CH  n=50 : 0.7869  vs 0.842
chase_pct      Δ=0.0132   林盛恩 2025 球種數據 SL  n=48 : 0.3312  vs 0.318
h_rel          Δ=0.0093   林鋅杰 2021 球種數據 CH  n=57 : -1.5793 vs -1.57
v_rel          Δ=0.0080   鄧愷威 2024 球種數據 SI  n=560: 5.392   vs 5.4
extension      Δ=0.0067   林盛恩 2025 球種數據 SL  n=48 : 6.0533  vs 6.06
```

`strike_pct`、`swstr_pct`、`csw_pct`、`put_away_pct`、`zone_pct` 全庫零誤差，與 §2.2 的判定完全吻合。

**病因實例（轉速誤差 96 rpm）**

林盛恩 2025 曲球：

```
A   層級：CU 33 球，33 球有轉速，平均 2264.9
ROK 層級：CU 22 球，只有  6 球有轉速，平均 2655.7

目前 combine：(33 × 2265   + 22 × 2656  ) / 55 = 2421.4
原始資料重算：(33 × 2264.9 + 6  × 2655.7) / 39 = 2325.0
```

ROK 的 22 顆球裡有 16 顆根本沒有轉速資料，卻讓那個層級拿到 22 的權重。

### 2.4 實測誤差 — 頂層純量欄位

排除 Bug B 的重複列後掃描 117 組 (球員, 年度)，純加權誤差：

```
avg_ev          Δ=1.4740   林盛恩 2025 [ROK, A]  : 79.326  vs 80.8
hr_fb_pct       Δ=0.2280   林振瑋 2023 [ROK, A]  : 0.45    vs 0.222
ev90            Δ=0.1390   鄭宗哲 2026 [MLB, AAA]: 100.639 vs 100.5
avg_extension   Δ=0.0860   林盛恩 2025 [ROK, A]  : 6.104   vs 6.19
avg_la          Δ=0.0490   鄭宗哲 2026 [MLB, AAA]: 14.649  vs 14.6
hard_hit_pct    Δ=0.0460   徐基麟 2021 [ROK, A]  : 0.296   vs 0.25
barrel_pct      Δ=0.0280   林盛恩 2025 [ROK, A]  : 0.079   vs 0.051
zone_pct        Δ=0.0060   林盛恩 2025 [ROK, A]  : 0.508   vs 0.502
```

其餘欄位零誤差，與 §2.2 的判定吻合。

### 2.5 目前有沒有真的顯示出來

**這一節很重要，否則會高估 Bug A 的當下影響。**

`tab_advanced.j2:160`、`:223`、`:275` 與 `m_advanced.j2:192`、`:249`、`:287` 都有這一行：

```jinja
{% set level_entries = entries if entries|length == 1 else entries[1:] %}
```

`entries[1:]` 把 `_combined` 那筆跳過了。所以：

- **§2.4 的頂層純量欄位錯誤目前沒有被渲染**——Statcast 概覽 / Plate Discipline / 擊球型態 只印各層級的原始值。這是潛在錯誤，一旦這三張表開始顯示合計列就會浮現。
- **§2.3 的球種表錯誤正在線上顯示**——「投球球種分析 / 對戰球種分析」的 All Levels 檢視、Pitch Plinko 與球路位移圖都會用到 `_combined`。

---

## §3 Bug B — 同年同層級多隊重複計算

### 3.1 病因

`site_builder/sync/statcast.py:153`

```python
if sport_level:
    if row_sport_level == sport_level:
        stat_doc["statcast"] = statcast_data
```

statcast 是以 `(year, sport_level)` 為單位聚合的（`load_all_pitches_for_player()` 的 key 就是這個），但寫回時會寫進**每一筆** sport_level 相符的 season_stats 列。球季中途轉隊的球員在同一層級會有多筆列，於是每一筆都拿到一份完整的整季資料。

`site_builder/render/pages.py:395` 接著替每一筆列各建一個 entry：

```python
statcast_by_year.setdefault(s.year, []).append({
    "sport_level": s.sport_level, "team_name": s.team_name, "sc": sc, "stat": s,
})
```

`combine_statcast_dicts()` 就把同一份資料累加了 N 次。

同一段程式碼裡的 `saber_written` 旗標正是為了避免 wRC+ / WAR 重複寫入而存在，statcast 卻沒有對應的保護。

### 3.2 全庫實測

**19 個 (球員, 年度, 層級) 組合、分布在 18 個 (球員, 年度)：**

| 年度 | 球員 | 重複層級 | 合計球數膨脹 | 比率是否偏移 |
|---|---|---|---|---|
| 2023 | 陳聖平 | ROK×2 | 1.07× | 是，wOBA Δ=0.0130 |
| 2023 | 李灝宇 | A+×2 | 1.98× | 是，Whiff% Δ=0.0050 |
| 2022 | 張育成 | MLB×4 | 3.60× | 是，LD% Δ=0.0180 |
| 2021 | 王志庭 | ROK×2 | 1.51× | 是，Whiff% Δ=0.0350 |
| 2019 | 胡智為 | AA×2, AAA×2 | 2.00× | 否 |
| 2019 | 王維中 | MLB×2 | 1.55× | 是，LD% Δ=0.0210 |
| 2018 | 黃暐傑 | AA×2 | 2× | 否（單一層級，只有計數翻倍） |
| 2016 | 林凱威 | ROK×2 | 2× | 否（單一層級，只有計數翻倍） |
| 2015 | 王建民 | AAA×2 | 2× | 否（單一層級，只有計數翻倍） |
| 2014 | 王建民 | AAA×2 | 2× | 否（單一層級，只有計數翻倍） |
| 2013 | 王建民 | AAA×2 | 1.79× | 是，HR/FB% Δ=0.0180 |
| 2011 | 陳鴻文 | AAA×2 | 1.57× | 是，Straight% Δ=0.0160 |
| 2011 | 蔣智賢 | AA×2 | 2× | 否（單一層級，只有計數翻倍） |
| 2011 | 蔡孟修 | ROK×2 | 2× | 否（單一層級，只有計數翻倍） |
| 2010 | 陳鏞基 | AA×2 | 2× | 否（單一層級，只有計數翻倍） |
| 2009 | 邱子愷 | ROK×2 | 2× | 否（單一層級，只有計數翻倍） |
| 2009 | 張立帆 | ROK×2 | 2× | 否（單一層級，只有計數翻倍） |
| 2008 | 林柏佑 | ROK×2 | 2× | 否（單一層級，只有計數翻倍） |

行為分兩種：

- 該年度**只有一個層級**時，重複的是完全相同的值，加權平均不變，只有計數欄位（`total_pitches`、`bbe`、`pa_count`、球種 `count`）翻倍
- 該年度**還有其他層級**時，被重複的層級拿到 N 倍權重，**所有比率也跟著偏移**

### 3.3 已建置站台上的實證

`dist/retired/player/644374/index.html`（張育成 2022，MLB 四隊 + AAA + AA）：

**合計列的球數是 MLB 單獨的 4 倍**

```
合計列  Four-Seam Fastball  972 球
MLB 列  Four-Seam Fastball  243 球      972 = 243 × 4
```

（AAA / AA 在 2022 沒有球種辨識資料，所以合計恰好等於 4 × MLB。）

**HTML 出現 4 個重複的 DOM id**

```
$ grep -o 'id="arsenal-2022-[^"]*"' index.html | sort | uniq -c
   1 id="arsenal-2022-_combined"
   1 id="arsenal-2022-AA"
   1 id="arsenal-2022-AAA"
   4 id="arsenal-2022-MLB"
```

**Statcast 概覽 / Plate Discipline / 擊球型態 三張表各印出 4 列一模一樣的 MLB**

```
2022 | MLB | 762 | 64.6% | 47.8% | 67.6% | 29.1% | 81.7% | ...
2022 | MLB | 762 | 64.6% | 47.8% | 67.6% | 29.1% | 81.7% | ...   ← 重複
2022 | MLB | 762 | 64.6% | 47.8% | 67.6% | 29.1% | 81.7% | ...   ← 重複
2022 | MLB | 762 | 64.6% | 47.8% | 67.6% | 29.1% | 81.7% | ...   ← 重複
2022 | AAA |  94 | 57.4% |     - |     - |     - |     - | ...
2022 | AA  |  22 | 63.6% |     - |     - |     - |     - | ...
```

這三張表跳過了 `_combined`（見 §2.5），躲掉了 Bug A，但躲不掉 Bug B。

---

## §4 受影響的表格清單

**Bug A（加權）— 只在「合計 / All Levels」檢視**

桌機 `tab_advanced.j2:333+`、手機 `m_advanced.j2:352+`

| 表格 | 受影響欄位 |
|---|---|
| 投手「球種數據」 | Velo, iVB, HB, Spin, Ext, vRel, hRel, Zone%, Chase%, Whiff%, wOBA |
| 投手「對戰結果」 | Z-Whiff%, O-Swing%, AVG, wOBA, Barrel%, Hard-Hit% |
| 打者「對戰球種分析」 | Zone%, Z-Swing%, O-Swing%, Whiff%, AVG, wOBA, Barrel%, Hard-Hit% |
| 打者「分類」（快速球／變化球／慢速球） | 同上 |
| 上述四張的左右投打分頁 | `pitcher_bat_side_splits` / `batter_pitch_hand_splits`，同一組欄位 |

**加權正確、但受 Bug B 影響**

| 表格 | 說明 |
|---|---|
| 各球數配球比例（`usage_by_count`） | 純加總，公式正確 |
| Pitch Plinko（`tab_plot.j2` / `m_plot.j2`） | 純加總，公式正確 |
| 球路位移圖（`pitch_movement`） | 純加總，公式正確 |
| Statcast 概覽 / Plate Discipline / 擊球型態 | 跳過合計列，只中 Bug B 的重複列 |

**完全未受影響**

`stats/core/career.py`、`stats/core/aggregate.py` 的生涯合計與年度合計是「先加總計數欄位、再從總計重算比率」，數學上正確。歷年賽季成績、歷年進階數據兩張表不受這兩個 bug 影響。

---

## §5 二次捨入

`site_builder/util/numbers.py:23` 的 `ratio()` 預設 `digits=3`，各層級的比率在存進資料庫前就已經捨入；`weighted.py:70` 合併後再捨入到 4 位。誤差上界約 5×10⁻⁴。

`spin` 更明顯：各層級先 `mean_round(..., 0)` 取整才進合併。

相對於 §2、§3 這是次要問題，但修加權時順手一起處理比較乾淨——各層級存未捨入值，只在顯示時捨入。`compute_pitch_woba()` 的 docstring 已經記載了這個原則，只是還沒推廣到其他欄位。

---

## §6 不在此文件範圍的相關問題

以下是**單層級的公式問題**，重算多少次結果都一樣，不會被跨層級的修正解掉。詳見 `docs/UNFIXED_BUGS.md`：

- **#16** `gb_pct` / `ld_pct` / `fb_pct` / `pu_pct` / `air_pct` 用所有 in-play 當分母，未知 trajectory 的擊球會稀釋比例；spray 類應該用 `spray_total`
- **#17** `compute_ev90()` 的 nearest-rank index 有 off-by-one，n 是 10 的倍數時會取到下一個 rank
- **#18** `spray.py` 把非 `"L"` 的打擊側全部當右打，左右開弓與未知打擊側會被誤判

---

## §7 修正方向

**Bug B** 成本低、現在就在線上顯示錯誤數字，建議優先。兩個切入點：

- `render/pages.py` 建 `statcast_by_year` 時以 `(year, sport_level)` 去重（`UNFIXED_BUGS.md` #14 的建議）
- 或 `sync/statcast.py` 只寫入該層級第一筆列，比照同檔案既有的 `saber_written` 旗標

去重應該放在渲染層：`season_stats` 每隊一列是**正確**的（歷年賽季成績、歷年進階數據都需要），錯的只是 statcast 被複製到每一列。

**Bug A** 沒辦法只改 `weighted.py`——各層級存的資料裡根本沒有真正的分母。可行方向：

1. **各層級補存真分母**，比照 `discipline_metrics()` 既有的 `*_den` 做法，合併時用對應分母加權。`ev90` 無論如何都無法正確合併，只能顯示「—」。
2. **合計改用原始 pitches 重算**——把該年度所有層級的 pitches 池化，直接呼叫與單層級相同的 `compute_*_statcast()`。數學上零誤差、`ev90` 也正確，並且天然免疫 Bug B。代價是需要一個地方存放預先算好的結果，或在建置時付出重算成本。

方向 2 的附帶效果是可以整段刪除 `stats/combine.py`、`stats/tables/weighted.py` 以及各模組的 `combine_*()` 函式，讓「合計」不再是另一套需要獨立維護的演算法。

---

## 重現方式

本文件所有數字由以下比對產生：讀 `season_stats.stat_json.statcast` 走 production 合併路徑，對照 `game_logs.pitches_json` 池化後重算的結果。比對腳本未納入版控（一次性驗證），§1 已記錄完整方法，可依此重建。

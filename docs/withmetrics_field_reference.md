# `withMetrics` 端點完整欄位參考

本文件記錄 MLB Stats API `GET /api/v1/game/{gamePk}/withMetrics` 回傳 JSON 中，
**`liveData.plays`**（打席／逐球資料，也是目前 `site_builder` 抓取 Statcast 的唯一資料來源）
與 **`gameData`** 底下所有欄位的定義，並標明：

- **feed/live 有嗎**：現行 `site_builder/api/games.py::get_game_play_by_play()` 打的
  `GET /api/v1.1/game/{gamePk}/feed/live` 端點是否也有這個欄位
- **目前程式碼有抓嗎**：`site_builder/sync/extract.py::extract_pitch_logs()` /
  `_extract_runners()` 現在有沒有讀取並寫進 `game_logs.pitches_json`

> 調查方法：實際對同一場 2024-06-01 的 MLB 比賽（`gamePk=744932`）分別呼叫兩個端點，
> 對整棵 JSON 樹做遞迴 key-diff，並抽樣真實回傳值驗證型別與意義；另外用一場 MiLB 比賽
> （`gamePk=753515`）驗證 `withMetrics` 在小聯盟層級也能打，但 Statcast 系欄位
> （`contextMetrics` 內容）只有 MLB 比賽才有值。
>
> **結論**：`feed/live` 是 `withMetrics` 的**嚴格子集**——對整份 JSON 做完整 diff，
> `feed/live` 沒有任何欄位是 `withMetrics` 沒有的（0 個）。`withMetrics` 只在兩處新增內容：
> `gameData.ruleSettings`，以及 `liveData.plays`（`allPlays[]`/`currentPlay`）底下的一批
> 逐打席／逐球進階指標。`liveData.boxscore`、`liveData.linescore`、`liveData.decisions`、
> `liveData.leaders`、`gameData.game/datetime/status/teams/players/venue/weather/...`
> 等其餘區塊在兩個端點之間逐位元組相同，因此本文件不重複列出（不影響切換決策）。

---

## 目錄

1. [gameData 層級新增欄位](#一gamedata-層級新增欄位)
2. [Play 層級欄位（`liveData.plays.allPlays[]`）](#二play-層級欄位liveDataplaysallplays)
3. [Play 子物件欄位](#三play-子物件欄位)
4. [Event／逐球層級欄位（`playEvents[]`）](#四event逐球層級欄位playevents)
5. [Event 子物件欄位](#五event-子物件欄位)
6. [現有 `extract.py` 欄位對應總表](#六現有-extractpy-欄位對應總表)

---

## 一、gameData 層級新增欄位

| 欄位 | 型別 | feed/live 有嗎 | 目前程式碼有抓嗎 | 定義 |
|---|---|---|---|---|
| `gameData.ruleSettings[]` | list[dict] | ❌ 沒有 | ❌ 沒有 | 該場比賽生效的規則設定清單。每個元素含 `settingId`、`settingName`（如 `designatedHitter`、`extraInningsRunnerOnSecond`、`replayChallenges`）、`settingDisplayName`、`settingDescription`、`valueType`（`boolean`/`numeric`）、`settingValue`。屬於**game 層級**（一場比賽一份，不隨打席/球數重複），非本文件核心關注的逐球資料。 |

---

## 二、Play 層級欄位（`liveData.plays.allPlays[]`）

「Play」= 一個完整打席（at-bat）。以下是該 dict 的**所有**頂層欄位（不只新增的），
`extract_pitch_logs()` 目前是逐一走訪這個陣列來取得每個打席。

| 欄位 | 型別 | feed/live 有嗎 | 目前程式碼有抓嗎 | 定義 |
|---|---|---|---|---|
| `result` | dict | ✅ 有 | ✅ 有（`.eventType`/`.event`） | 打席最終結果，見下方子表 |
| `about` | dict | ✅ 有 | ✅ 有（`.inning`） | 打席發生的局數/時間等中繼資料，見下方子表 |
| `count` | dict | ✅ 有 | ✅ 有（→ `pa_final_balls`/`pa_final_strikes`/`pa_final_outs`，只在該打席最後一球） | 打席**結束當下**的球數（balls/strikes/outs）；逐球的球數是取用 `playEvents[].count`，這個是 play 層級的最終值 |
| `matchup` | dict | ✅ 有 | ✅ 有（`.pitcher`/`.batter`/`.batSide`/`.pitchHand`） | 打席的投打對戰資訊，見下方子表 |
| `pitchIndex[]` | list[int] | ✅ 有 | ❌ 沒有 | `playEvents[]` 中屬於「投球」的索引位置 |
| `actionIndex[]` | list[int] | ✅ 有 | ❌ 沒有 | `playEvents[]` 中屬於「場上動作」（換人、暫停等）的索引位置 |
| `runnerIndex[]` | list[int] | ✅ 有 | ❌ 沒有 | `playEvents[]` 中屬於「跑壘動作」（盜壘、牽制等）的索引位置 |
| `runners[]` | list[dict] | ✅ 有 | ✅ 有（`_extract_runners()`） | 打席結束時的跑壘/得分/守備 credit 明細（現在只掛在最後一球那筆 pitch dict 上） |
| `playEvents[]` | list[dict] | ✅ 有 | ✅ 有（逐球資料主要來源） | 這個打席內的每一顆球/每個動作，見第四節 |
| `playEndTime` | str (ISO8601) | ✅ 有 | ❌ 沒有 | 打席結束時間戳 |
| `atBatIndex` | int | ✅ 有 | ❌ 沒有 | 該打席在全場的序號（從 0 開始） |
| `reviewDetails` | dict | ✅ 有（僅重播挑戰時出現） | ❌ 沒有 | 挑戰重播詳情：`isOverturned`、`inProgress`、`reviewType`、`challengeTeamId` |
| `credits[]` | list[dict] | 🆕 只有 withMetrics | ❌ 沒有 | 打席相關計分代碼清單，如 `{"player": {"id":...}, "credit": "b_pa"}`（打席）、`p_pa`（投手打席）；資訊量低，`result.eventType` 已足夠涵蓋大部分語意 |
| `flags[]` | list[dict] | 🆕 只有 withMetrics | ❌ 沒有 | 特殊計分旗標，如犧牲觸擊/高飛：`[{"credit": "b_sac_fly"}]`；多數情況為空陣列 |
| `homeTeamWinProbability` | float (0–100) | 🆕 只有 withMetrics | ✅ 有（→ `home_wp`，只在該打席最後一球） | 打席結束當下，主隊的獲勝機率（百分比） |
| `awayTeamWinProbability` | float (0–100) | 🆕 只有 withMetrics | ❌ 沒有（未落地存欄位，讀取時可用 `100 - home_wp` 反推） | 客隊獲勝機率，恆等於 `100 - homeTeamWinProbability` |
| `homeTeamWinProbabilityAdded` | float | 🆕 只有 withMetrics | ✅ 有（→ `wpa`，只在該打席最後一球） | 這個打席讓主隊勝率增減多少個百分點（WPA，主隊視角，可正可負） |
| `leverageIndex` | float | 🆕 只有 withMetrics | ✅ 有（→ `leverage_index`，只在該打席最後一球） | 局勢緊張度指數（LI）。以 1.0 為聯盟平均緊張度，數字越高代表這個打席對比賽結果影響越關鍵 |
| `dramaIndex` | float (0–100) | 🆕 只有 withMetrics | ✅ 有（→ `drama_index`，只在該打席最後一球） | MLB 官方定義的「精彩程度」綜合指標，混合勝率變化與比賽情境，用於轉播/精華片段排序，無公開精確公式 |
| `contextMetrics` | dict | 🆕 只有 withMetrics | ✅ 有（`.xWoba`/`.catchProbability` → `pa_xwoba`/`catch_probability`，只在該打席最後一球） | 該打席結果的期望值指標，見下方 |

### `contextMetrics`（play 層級）

| 欄位 | 型別 | 定義 |
|---|---|---|
| `xWoba` | float | 這個打席**實際結果**對應的期望 wOBA 貢獻值（依打擊初速/角度或結果類型查表得出），只在有值時出現 |
| `catchProbability` | int (0–100) | 若該打席是飛球，野手接殺這顆球的機率（Statcast Catch Probability 的官方版本，OAA 系列指標的素材） |

> 注意：MiLB 比賽這個欄位存在，但通常是空 dict `{}`——只有 MLB 比賽有 Statcast 來源可算。

---

## 三、Play 子物件欄位

以下都是 **feed/live 本來就有**、withMetrics 沒有新增內容的既有欄位，列出是為了回答「play
層級所有資料」，非切換時需要特別處理的部分。

### `result`

| 欄位 | 型別 | 定義 |
|---|---|---|
| `type` | str | 打席類型，如 `"atBat"` |
| `event` | str | 事件的人類可讀名稱，如 `"Walk"`、`"Home Run"` |
| `eventType` | str | 事件的機器可讀代碼，如 `"walk"`、`"home_run"`（`extract.py` 用這個判斷 `pa_event`） |
| `description` | str | 完整播報文字 |
| `rbi` | int | 這個打席貢獻的打點數 |
| `awayScore`/`homeScore` | int | 打席結束當下的比分 |
| `isOut` | bool | 打者是否出局 |

### `about`

| 欄位 | 型別 | 定義 |
|---|---|---|
| `atBatIndex` | int | 同 play 層級的 `atBatIndex` |
| `halfInning` | str | `"top"`/`"bottom"` |
| `isTopInning` | bool | 是否為上半局 |
| `inning` | int | 第幾局（`extract.py` 用這個填 pitch dict 的 `inning`） |
| `startTime`/`endTime` | str | 打席起訖時間 |
| `isComplete` | bool | 打席是否已完成 |
| `isScoringPlay` | bool | 這個打席是否有得分 |
| `hasReview` | bool | 是否有申請重播 |
| `hasOut` | bool | 是否產生出局數 |
| `captivatingIndex` | int | 舊版「精彩度」指標（withMetrics 的 `dramaIndex` 是它的進階版） |

### `count`（play 層級，打席結束當下）

| 欄位 | 型別 | 定義 |
|---|---|---|
| `balls` | int | 結束時的壞球數 |
| `strikes` | int | 結束時的好球數 |
| `outs` | int | 結束時的出局數 |

### `matchup`

| 欄位 | 型別 | 定義 |
|---|---|---|
| `batter` | dict `{id, fullName, link}` | 打者 |
| `batSide` | dict `{code, description}` | 打者站位（左/右打） |
| `pitcher` | dict `{id, fullName, link}` | 投手 |
| `pitchHand` | dict `{code, description}` | 投手慣用手 |
| `postOnFirst`/`postOnSecond`/`postOnThird` | dict `{id, fullName, link}` | 打席結束當下一、二、三壘的跑者（沒人上壘則該 key 不存在） |
| `batterHotColdZones`/`pitcherHotColdZones` | list | 熱區資料，本場樣本中恆為空陣列 |
| `splits` | dict `{batter, pitcher, menOnBase}` | 左右投打對戰情境代碼 |

### `reviewDetails`

| 欄位 | 型別 | 定義 |
|---|---|---|
| `isOverturned` | bool | 重播後判決是否被推翻 |
| `inProgress` | bool | 重播是否進行中 |
| `reviewType` | str | 重播類型代碼 |
| `challengeTeamId` | int | 提出挑戰的球隊 ID |

---

## 四、Event／逐球層級欄位（`playEvents[]`）

`playEvents[]` 是每個打席內部，依時間序排列的「事件」清單，`type` 欄位共有四種值
（本場樣本統計）：`pitch`（272 顆真正投球）、`action`（24 筆場上動作，如換人/暫停）、
`pickoff`（3 筆牽制）、`stepoff`（2 筆踏板）。`isPitch=True` 只對應 `type=="pitch"`，
`extract_pitch_logs()` 現在除了處理 `isPitch=True` 的投球事件外，也額外擷取
`pickoff`/`stepoff` 兩種事件（寫入 `events_json`，見第六節）；`action`/`no_pitch`
類型的事件本身仍完全被忽略。

| 欄位 | 型別 | feed/live 有嗎 | 目前程式碼有抓嗎 | 定義 |
|---|---|---|---|---|
| `details` | dict | ✅ 有 | ✅ 有（部分欄位） | 這顆球/這個動作的結果細節，見下方子表 |
| `count` | dict | ✅ 有 | ✅ 有（`balls`/`strikes`/`outs`） | 這顆球**投完之後**的球數 |
| `preCount` | dict | 🆕 只有 withMetrics | ✅ 有（→ `pre_balls`/`pre_strikes`/`pre_outs`；缺值時 `pre_balls`/`pre_strikes` fallback 手動累加 `pa_pre_balls`/`pa_pre_strikes`，`pre_outs` 缺值時則為 `None`，無 fallback） | 這顆球**投出之前**的球數（`balls`/`strikes`/`outs`），可直接取代或驗證現有的手動推算邏輯，且多了目前完全沒有的「投球前出局數」 |
| `index` | int | ✅ 有 | ✅ 有（僅牽制/踏板事件透過 `events_json.index` 保留；一般投球事件本身不重存） | 事件在 `playEvents[]` 中的序號 |
| `startTime`/`endTime` | str | ✅ 有 | ❌ 沒有 | 事件起訖時間 |
| `isPitch` | bool | ✅ 有 | ✅ 有（篩選用） | 是否為真正的一次投球 |
| `type` | str | ✅ 有 | ✅ 有（`pickoff`/`stepoff` 走 `events_json.type`；`action`/`no_pitch` 仍完全略過，投球事件本身隱含用 `isPitch` 篩選） | `pitch`/`action`/`pickoff`/`stepoff` |
| `player` | dict `{id, link}` | ✅ 有 | ❌ 沒有 | 非投球事件（如換人）的當事球員 |
| `playId` | str (UUID) | ✅ 有 | ✅ 有（投球事件 → `play_id`；牽制/踏板事件 → `events_json.play_id`） | 這顆球的全域唯一 ID（可用來對應 Baseball Savant 等外部資料） |
| `pitchNumber` | int | ✅ 有 | ✅ 有（→ `pitch_number`） | **該打席內第幾球**（含界外），非投手單場累計球數。**經 2026-07 實測驗證更正**：實測投手單場投 99 球，但 `pitchNumber` 最大只到 8，且每個新打席歸 1 重算，原文件「該投手單場累計第幾球」是錯的 |
| `actionPlayId` | str | ✅ 有（僅動作事件） | ❌ 沒有 | 場上動作事件的 ID |
| `isBaseRunningPlay` | bool | ✅ 有 | ❌ 沒有 | 是否為跑壘相關事件 |
| `isSubstitution` | bool | ✅ 有（僅動作事件） | ❌ 沒有 | 是否為換人事件 |
| `position` | dict `{code, name, type, abbreviation}` | ✅ 有（僅換人事件） | ❌ 沒有 | 換人後守備位置 |
| `battingOrder` | str | ✅ 有（僅換人事件） | ❌ 沒有 | 打序代碼 |
| `replacedPlayer` | dict `{id, link}` | ✅ 有（僅換人事件） | ❌ 沒有 | 被換下場的球員 |
| `officials[]` | list[dict] | ✅ 有 | ❌ 沒有 | 該球時場上四位裁判，見下方子表 |
| `pitchData` | dict | ✅ 有（部分子欄位新增） | ✅ 有（含新增的 `strikeZoneInfo.*`/`breaks.breakVertical`） | 投球物理量，見下方子表 |
| `hitData` | dict | ✅ 有（部分子欄位新增） | ✅ 有（含新增的 `hitProbability`/`batSpeed`/`isSwordSwing`） | 擊球物理量，見下方子表 |
| `defense` | dict | 🆕 只有 withMetrics | ✅ 有（→ `defense` 濃縮 dict，經 `_condense_defense()` 只留 9 個守備位置的球員 id） | 這顆球投出當下 9 個守備位置的球員，見下方子表 |
| `offense` | dict | 🆕 只有 withMetrics | ✅ 有（→ `offense` 濃縮 dict，經 `_condense_offense()` 存投球前壘況＋代打偵測，不重存 `batter_id`） | 這顆球投出當下的打者與壘上跑者，見下方子表 |
| `homeTeamWinProbability` | float | 🆕 只有 withMetrics | ❌ 沒有 | **經 2026-07 實測驗證更正**：抽樣 4 場（含 2024 世界大賽 G1）逐球層級此欄位全部是 0，並非真正逐球更新——WP 只有 play（打席結束）層級才有真實值（見第二節對應欄位），原文件「這代表 WP 系列指標其實可以做到每球精度，不只打席結束時才有」是錯的 |
| `awayTeamWinProbability` | float | 🆕 只有 withMetrics | ❌ 沒有 | 同上，客隊視角，實測同樣恆為 0 |
| `homeTeamWinProbabilityAdded` | float | 🆕 只有 withMetrics | ❌ 沒有 | 同上，實測恆為 0，WPA 只有 play 層級才有真實值 |
| `leverageIndex` | float | 🆕 只有 withMetrics | ❌ 沒有 | 同上，實測恆為 0，LI 只有 play 層級才有真實值 |
| `dramaIndex` | float | 🆕 只有 withMetrics | ❌ 沒有 | 同上，實測恆為 0，drama 只有 play 層級才有真實值 |
| `contextMetrics` | dict | 🆕 只有 withMetrics | ✅ 有（`.averagePitchSpeedPlayer`/`.maxPitchSpeedPlayer`/`.pitchSpeedPlayerRank`/`.homeRunBallparks` → `avg_pitch_speed_player`/`max_pitch_speed_player`/`pitch_speed_pct`/`hr_ballparks`；與同名 play 層級欄位不同，此為逐球真實值） | 逐球脈絡指標，見下方子表 |

---

## 五、Event 子物件欄位

### `details`

| 欄位 | 型別 | feed/live 有嗎 | 目前有抓嗎 | 定義 |
|---|---|---|---|---|
| `description` | str | ✅ | ❌ | 這顆球/動作的播報文字 |
| `event`/`eventType` | str | ✅ | ❌（play 層級的才有抓） | 動作事件（非投球）專用的結果分類 |
| `awayScore`/`homeScore` | int | ✅ | ❌ | 這顆球當下比分 |
| `isScoringPlay` | bool | ✅ | ❌ | 是否觸發得分 |
| `isOut` | bool | ✅ | ✅（僅牽制/踏板事件透過 `events_json.is_out`；投球事件本身不重存） | 是否造成出局 |
| `hasReview` | bool | ✅ | ❌ | 是否有申請重播 |
| `call` | dict `{code, description}` | ✅ | ❌ | 裁判判決（好壞球判決等） |
| `code` | str | ✅ | ✅（`result_code`） | 該球結果代碼，如 `"B"`/`"C"`/`"S"` |
| `ballColor`/`trailColor` | str (rgba) | ✅ | ❌ | 動畫用顏色，網站不需要 |
| `isInPlay`/`isStrike`/`isBall` | bool | ✅ | ✅ | 這球是否形成打擊入場/好球/壞球 |
| `type` | dict `{code, description}` | ✅ | ✅（`pitch_type`/`pitch_name`） | 球種 |
| `fromCatcher` | bool | ✅（僅牽制事件） | ✅（→ `events_json.from_catcher`） | 牽制是否由捕手發動 |
| `disengagementNum` | int | ✅（僅牽制/踏板事件） | ✅（→ `events_json.disengagement_num`） | 該打席第幾次「脫離投手板」（2023 起限制牽制次數規則的計數） |
| `runnerGoing` | bool | ✅（僅特定事件） | ✅（→ `events_json.runner_going`） | 跑者是否正在起跑（盜壘中） |

### `count` / `preCount`（結構相同）

| 欄位 | 型別 | 定義 |
|---|---|---|
| `balls` | int | 壞球數 |
| `strikes` | int | 好球數 |
| `outs` | int | 出局數 |

### `pitchData`

| 欄位 | 型別 | feed/live 有嗎 | 目前有抓嗎 | 定義 |
|---|---|---|---|---|
| `startSpeed`/`endSpeed` | float (mph) | ✅ | ✅ | 出手/過壘速度 |
| `strikeZoneTop`/`strikeZoneBottom` | float (ft) | ✅ | ✅ | 該打者的好球帶上下緣 |
| `zone` | int | ✅ | ✅ | 好球帶九宮格+外圍分區代碼（1–14） |
| `typeConfidence` | float | ✅ | ✅ | 球種分類信心值 |
| `plateTime` | float (sec) | ✅ | ✅ | 出手到過壘所需時間 |
| `extension` | float (ft) | ✅ | ✅ | 出手延伸距離 |
| `coordinates` | dict | ✅ | ✅（大部分子欄位） | 座標與初速/加速度，見下方 |
| `breaks` | dict | ✅ | ✅（全部子欄位，含新增的 `breakVertical`） | 位移/轉速資料，見下方 |
| `strikeZoneInfo` | dict | 🆕 只有 withMetrics | ✅ 有（見下方 `pitchData.strikeZoneInfo` 子表） | 新版好球帶模型明細，見下方 |

#### `pitchData.coordinates`

| 欄位 | 定義 |
|---|---|
| `pfxX`/`pfxZ` | 水平/垂直位移量（含重力影響，英吋） |
| `pX`/`pZ` | 過本壘板時的水平/垂直座標 |
| `x0`/`y0`/`z0` | 出手點座標 |
| `vX0`/`vY0`/`vZ0` | 出手點三軸速度分量 |
| `aX`/`aY`/`aZ` | 三軸加速度分量 |
| `x`/`y` | 轉播圖表用的螢幕座標（現有程式碼未使用，也不建議用） |

#### `pitchData.breaks`

| 欄位 | 定義 |
|---|---|
| `breakAngle` | 位移角度 |
| `breakLength` | 最大位移量（英吋） |
| `breakY` | 最大位移發生位置的 y 座標 |
| `breakVertical` | 垂直位移（含重力） |
| `breakVerticalInduced` | 誘導垂直位移（IVB，扣除重力後的「純」垂直位移，現有程式碼取為 `ivb`） |
| `breakHorizontal` | 水平位移（HB） |
| `spinRate` | 轉速（rpm） |
| `spinDirection` | 轉軸方向（時鐘方向角度） |

#### `pitchData.strikeZoneInfo`（🆕 withMetrics 新增，現已全部擷取）

| 欄位 | 型別 | 定義 |
|---|---|---|
| `plateX`/`plateY`/`plateZ` | float | 新版模型下，球通過本壘板平面的三維座標 |
| `strikeZoneTop`/`strikeZoneBottom` | float | 新版模型的好球帶上下緣（與 `pitchData.strikeZoneTop/Bottom` 理論上一致，但用不同建模管線算出，可能有微小差異） |
| `strikeZoneFlat`/`strikeZoneRounded` | bool | 好球帶形狀模型是否套用「平面版」或「圓角版」邊界（MLB 2024 起測試的好球帶形狀修正） |
| `strikeZoneCornerRadiusInches` | float | 圓角好球帶模型的轉角半徑 |
| `widthInches`/`depthInches` | float | 好球帶寬度/景深（3D 好球帶模型用，取代傳統只看 2D 平面的判法） |
| `edgeDistance` | float (inches) | 球心到好球帶邊緣的最短距離（正值代表在好球帶內側，負值代表在外側——精確量化「差一點點的好壞球」） |
| `isStrike` | bool | 新版模型下這球是否落在好球帶內（可能與 `details.isStrike`〔裁判實際判決〕不同，能用來算「好球帶誤判率」） |

### `hitData`

| 欄位 | 型別 | feed/live 有嗎 | 目前有抓嗎 | 定義 |
|---|---|---|---|---|
| `launchSpeed` | float (mph) | ✅ | ✅（`ev`） | 擊球初速 |
| `launchAngle` | float (度) | ✅ | ✅（`la`） | 擊球仰角 |
| `totalDistance` | float (ft) | ✅ | ✅（`hit_distance`） | 落點總距離 |
| `trajectory` | str | ✅ | ✅ | 球路類型（`line_drive`/`fly_ball`/`ground_ball`/`popup`） |
| `hardness` | str | ✅ | ✅ | 擊球強度分類（`hard`/`medium`/`soft`） |
| `location` | str | ✅ | ✅（`hit_location`） | 落點守備位置代碼 |
| `coordinates` | dict `{coordX, coordY}` | ✅ | ✅ | 球場示意圖座標 |
| `hitProbability` | float (0–100) | 🆕 只有 withMetrics | ✅ 有（→ `hit_probability`） | 這個擊球初速+仰角組合，聯盟平均安打機率（Statcast xBA 系列的逐球版本） |
| `batSpeed` | float (mph) | 🆕 只有 withMetrics（2024/25 賽季起才有實測資料，需球棒感測器覆蓋） | ✅ 有（→ `bat_speed`） | 揮棒時球棒的最大速度（bat-tracking 數據） |
| `isSwordSwing` | bool | 🆕 只有 withMetrics | ✅ 有（→ `is_sword_swing`） | 是否為「劍擊」——揮棒速度極慢且打點偏離重心的防禦性揮棒（本場樣本中出現兩次，`batSpeed` 分別只有 43.3/35.2 mph，正常揮棒約 60–80 mph） |

### `contextMetrics`（event 層級）

| 欄位 | 型別 | 定義 |
|---|---|---|
| `averagePitchSpeedPlayer` | float (mph) | 該投手當場、該球種的平均球速（動態統計，非原始物理量） |
| `maxPitchSpeedPlayer` | float (mph) | 該投手當場、該球種目前為止的最快球速 |
| `pitchSpeedPlayerRank` | int (百分位) | 這顆球的球速在該投手當季所有同球種球速中的百分位排名；只有部分球才有值 |
| `homeRunBallparks` | int (0–30) | 若這球是全壘打，30 座球場中有幾座會出牆（Statcast 轉播常見的「這支全壘打在其他球場也是全壘打嗎」圖表數據） |

### `defense`（🆕 withMetrics 新增，投球當下守備站位，現已濃縮擷取為 `defense`，見 `_condense_defense()`）

| 欄位 | 型別 | 定義 |
|---|---|---|
| `pitcher` | dict `{id, link, pitchHand}` | 投手 |
| `catcher`/`first`/`second`/`third`/`shortstop`/`left`/`center`/`right` | dict `{id, link}` | 對應守備位置當下站守的球員 |

### `offense`（🆕 withMetrics 新增，投球當下打者/跑者狀態，現已濃縮擷取為 `offense`，見 `_condense_offense()`）

| 欄位 | 型別 | 定義 |
|---|---|---|
| `batter` | dict `{id, link, batSide}` | 打者 |
| `batterPosition` | dict `{code, name, type, abbreviation}` | 打者的防守位置（用於代打/代跑情境識別） |
| `first`/`second`/`third` | dict `{id, link}` | 投球**前**壘上跑者 |
| `postOnSecond`/`postOnThird` | dict `{id, link}` | 投球**後**（若有跑壘）二、三壘跑者；無對應的 `postOnFirst`（因為推進到一壘的情況少見） |

### `officials[]`

| 欄位 | 型別 | 定義 |
|---|---|---|
| `official` | dict `{id, link}` | 裁判 |
| `officialType` | str | 崗位，如 `"Home Plate"`/`"First Base"`/`"Second Base"`/`"Third Base"` |

---

## 六、現有 `extract.py` 欄位對應總表

方便日後改欄位時對照，目前 `extract_pitch_logs()` 寫進 `pitches_json` 每球一筆的欄位，來源如下：

| `pitches_json` 欄位 | 來源 JSON 路徑 |
|---|---|
| `game_pk` | `game_data.gamePk` |
| `inning` | `play.about.inning` |
| `pitch_type`/`pitch_name` | `event.details.type.code`/`.description` |
| `result_code`/`result_desc` | `event.details.code`/`.description` |
| `is_strike`/`is_ball`/`is_in_play` | `event.details.isStrike`/`.isBall`/`.isInPlay` |
| `zone` | `event.pitchData.zone` |
| `start_speed`/`end_speed`/`extension`/`plate_time` | `event.pitchData.*` |
| `strike_zone_top`/`strike_zone_bottom` | `event.pitchData.strikeZoneTop`/`.strikeZoneBottom` |
| `type_confidence` | `event.pitchData.typeConfidence` |
| `pfx_x`/`pfx_z`/`px`/`pz`/`x0`/`z0`/`vx0`/`vy0`/`vz0`/`ax`/`ay`/`az` | `event.pitchData.coordinates.*` |
| `ivb`/`hb`/`spin_rate`/`spin_dir`/`break_angle`/`break_length`/`break_y` | `event.pitchData.breaks.*` |
| `ev`/`la`/`hit_distance`/`trajectory`/`hit_location`/`hardness` | `event.hitData.*` |
| `hit_coord_x`/`hit_coord_y` | `event.hitData.coordinates.*` |
| `balls`/`strikes`/`outs` | `event.count.*`（投球**後**的球數） |
| `pre_balls`/`pre_strikes` | 優先取 `event.preCount.balls`/`.strikes`；缺值時 fallback 程式手動往前推算（見下方說明） |
| `pre_outs` | `event.preCount.outs`；缺值時為 `None`，**沒有**手動推算 fallback（`preCount` 出現前完全無法取得投球前出局數） |
| `batter_id`/`pitcher_id` | `play.matchup.batter.id`/`.pitcher.id` |
| `bat_side`/`pitch_hand` | `play.matchup.batSide.code`/`.pitchHand.code` |
| `is_pa_final` | 程式自算：該打席最後一個 `isPitch=True` 的事件（**不是 API 欄位**） |
| `pa_event`/`pa_event_desc` | `play.result.eventType`/`.event`（只在 `is_pa_final` 時填入） |
| `runners` | `play.runners[]`（只在 `is_pa_final` 時填入，見 `_extract_runners()`） |
| `play_id` | `event.playId` |
| `pitch_number` | `event.pitchNumber`（該打席內第幾球，非單場累計，見第四節更正說明） |
| `sz_plate_x`/`sz_plate_y`/`sz_plate_z` | `event.pitchData.strikeZoneInfo.plateX`/`.plateY`/`.plateZ` |
| `sz_top`/`sz_bottom` | `event.pitchData.strikeZoneInfo.strikeZoneTop`/`.strikeZoneBottom` |
| `sz_flat`/`sz_rounded` | `event.pitchData.strikeZoneInfo.strikeZoneFlat`/`.strikeZoneRounded` |
| `sz_corner_radius` | `event.pitchData.strikeZoneInfo.strikeZoneCornerRadiusInches` |
| `sz_width_in`/`sz_depth_in` | `event.pitchData.strikeZoneInfo.widthInches`/`.depthInches` |
| `sz_edge_distance` | `event.pitchData.strikeZoneInfo.edgeDistance` |
| `sz_is_strike` | `event.pitchData.strikeZoneInfo.isStrike` |
| `break_vertical` | `event.pitchData.breaks.breakVertical` |
| `avg_pitch_speed_player`/`max_pitch_speed_player`/`pitch_speed_pct`/`hr_ballparks` | `event.contextMetrics.averagePitchSpeedPlayer`/`.maxPitchSpeedPlayer`/`.pitchSpeedPlayerRank`/`.homeRunBallparks` |
| `hit_probability`/`bat_speed`/`is_sword_swing` | `event.hitData.hitProbability`/`.batSpeed`/`.isSwordSwing` |
| `defense` | `event.defense`（經 `_condense_defense()` 濃縮成 9 個守備位置的球員 id） |
| `offense` | `event.offense`（經 `_condense_offense()` 濃縮成投球前壘況＋代打偵測，不重存 `batter_id`） |
| `home_wp`/`wpa`/`leverage_index`/`drama_index` | `play.homeTeamWinProbability`/`.homeTeamWinProbabilityAdded`/`.leverageIndex`/`.dramaIndex`（經 `_pa_context()`，只在 `is_pa_final` 時填入） |
| `pa_xwoba`/`catch_probability` | `play.contextMetrics.xWoba`/`.catchProbability`（經 `_pa_context()`，只在 `is_pa_final` 時填入） |
| `pa_final_balls`/`pa_final_strikes`/`pa_final_outs` | `play.count.balls`/`.strikes`/`.outs`（經 `_pa_context()`，只在 `is_pa_final` 時填入） |

`extract_pitch_logs()` 現在回傳 `(pitches, nonpitch_events)` 2-tuple；`nonpitch_events`
定義了另一個快取欄位 `game_logs.events_json`（`pickoff`/`stepoff` 事件，經
`_condense_nonpitch_event()`），每筆物件的欄位對應：

| `events_json` 欄位 | 來源 JSON 路徑 |
|---|---|
| `type` | `event.type`（`pickoff`/`stepoff`） |
| `index` | `event.index` |
| `play_id` | `event.playId` |
| `inning` | `play.about.inning` |
| `pre_balls`/`pre_strikes`/`pre_outs` | `event.preCount.balls`/`.strikes`/`.outs` |
| `balls`/`strikes`/`outs` | `event.count.balls`/`.strikes`/`.outs` |
| `result_code`/`result_desc` | `event.details.code`/`.description` |
| `disengagement_num` | `event.details.disengagementNum` |
| `from_catcher` | `event.details.fromCatcher` |
| `runner_going` | `event.details.runnerGoing` |
| `is_out` | `event.details.isOut` |
| `pitcher_id`/`batter_id` | `play.matchup.pitcher.id`/`.batter.id` |

**2026-07 已完成擷取**：上一輪紀錄的「尚未使用、但已確認存在的 withMetrics 新欄位」
（`preCount.outs`、`hitData.batSpeed`/`.hitProbability`/`.isSwordSwing`、
`pitchData.strikeZoneInfo.*`、`contextMetrics.homeRunBallparks`、play 層級的
`contextMetrics.xWoba`/`.catchProbability` 與 `homeTeamWinProbability` 系列指標）
已於本輪 withMetrics 遷移全部擷取，對應見上表。唯一刻意不擷取的是 **event 層級**的
`homeTeamWinProbability`/`leverageIndex`/`dramaIndex`（實測恆為 0，見第四節更正說明），
以及第一節列出的少量低價值/場次中繼資料欄位。

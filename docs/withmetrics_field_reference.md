# `withMetrics` 端點完整欄位參考（2026-09 全面實測＋完整結構版）

**端點**：`GET https://statsapi.mlb.com/api/v1/game/{gamePk}/withMetrics`
（專案封裝於 `site_builder/api/games.py::get_game_play_by_play()`）

這份文件是這個端點**整棵 JSON 樹**的欄位清單，也是唯一權威版本。內容包含：
整份回應 JSON 從根節點到葉節點的**完整資料結構**（第三節）、每個欄位的型別、
出現率、**從哪一年開始有**、**哪些層級有**、實際值域與陷阱／死欄位標記
（第四、五、六節，含逐路徑完整表格），以及 `boxscore`／`gameData`／`metaData`
與 `site_builder/sync/extract.py` 現況對照（第七、八節）。看完你應該不用再
自己試探「這個數字到底有沒有」。

## 目錄

1. [調查方法與樣本](#一調查方法與樣本)
2. [★ 資料可用性總表：什麼年份、什麼層級才有什麼](#二-資料可用性總表)
3. [★ JSON 完整資料結構](#三json-完整資料結構)
4. [★ 死資料清單](#四死資料清單)
5. [打席層級欄位（allPlays[]，含逐路徑完整表格）](#五打席層級欄位allplays)
6. [逐球／事件層級欄位（playEvents[]，含逐路徑完整表格）](#六逐球事件層級欄位playevents)
7. [boxscore／gameData／metaData](#七boxscoregamedatametadata)
8. [extract.py 現況對照與補抓建議](#八extractpy-現況對照與補抓建議)

---

## 一、調查方法與樣本

依「年份 × 層級」對 `data/tracker.sqlite3` 的 `game_logs` 分層抽樣 499 場比賽，
逐場呼叫 `withMetrics`，對整棵 JSON 做遞迴走訪，統計每個欄位路徑的出現次數、
null／空值、型別、值分布，以及**按年份 × 層級交叉**的覆蓋率。

| 項目 | 數量 |
|---|---|
| 成功掃描場次 | **392 場**（2002–2026；MLB／AAA／AA／A+／A／A(Short)／ROK） |
| 打席（`allPlays[]`） | 30,127 |
| 事件（`playEvents[]`） | 109,151 |
| 其中真正的投球 | 98,850（`pitch` 98,850／`action` 7,813／`pickoff` 2,135／`no_pitch` 236／`stepoff` 117） |
| 擊球進場（有 `hitData.trajectory`） | 20,600 |
| 跑壘紀錄（`runners[]`） | 42,411 |
| 不重複欄位路徑 | 2,312 |

**兩個先講清楚的前提**

1. **這個端點對 2002 年的比賽一樣可用。** 抽樣時有 107 場抓取失敗，逐一重試後
   全部回 200——失敗純粹是 8 併發下的連線逾時，不是舊比賽沒有資料。要抓歷史
   資料時記得放重試，別把逾時誤判成「沒有」。
2. **欄位缺席時 MLB 是直接不給 key，不是給 null。** 所以判斷有沒有資料要用
   `"key" in obj`，而不是 `obj.get(key) is None`；`.get(k, 0)` 這種寫法會把
   「不存在」變成 0，是先前文件把 event 層級 WPA 誤判成「恆為 0」的原因。

> 「出現率」的定義：該欄位出現次數 ÷ 它父物件的出現次數，也就是
> 「父物件在的時候，這個 key 有多大機率也在」。

---

## 二、★ 資料可用性總表

### 2.1 追蹤系統（Statcast／PITCHf/x）是**逐場全有或全無**

這是最重要的一件事：**除了 MLB 與 2023 年起的 AAA，其他層級的球速／轉速／
好球帶座標，是看那座球場有沒有裝 Hawk-Eye，而不是看年份。** 同一年同一層級，
有的場子整場 100% 有資料、有的整場 0%，中間沒有灰色地帶。

實測（每格 = 該年該層級抽樣場次中，帶有球速的投球比例）：

| 年份 | MLB | AAA | AA | A+ | A | ROK |
|---|---|---|---|---|---|---|
| 2002–2006 | 0% | 0% | 0% | 0% | 0% | 0% |
| 2007 | 43% | 0% | 0% | 0% | 0% | 0% |
| 2008–2020 | 97–100% | 0% | 0% | 0% | 0% | 0% |
| 2021 | 100% | 0% | 0% | 0% | 29% | 0% |
| 2022 | 100% | 63% | 0% | 0% | 100% | 0% |
| 2023 | 100% | 100% | 0% | 0% | 47% | 0% |
| 2024 | 100% | 100% | 0% | 0% | 100% | 0% |
| 2025 | 100% | 100% | 0% | 0% | 0% | 33% |
| 2026 | 100% | 100% | 0% | 0% | 0% | 69% |

追加驗證（2024–2026 額外抽 45 場，逐場檢查）：

- **AA／A+：22 場全部 0%。**到 2026 年為止，二軍高階與 A+ 基本上完全沒有逐球追蹤資料。
- **A（Single-A）：同年不同場差異極大**——2024 抽 6 場有 4 場 100%、2 場 0%；
  2025 抽 5 場全 0%；2026 抽 6 場只有 1 場 100%。是球場決定的。
- **ROK：2026 抽 6 場有 1 場 100%**（複合訓練基地的部分球場）。
- 每一場都是「整場 100%」或「整場 0%」，沒有一場是中間值。

**實務建議**：處理非 MLB 資料時，先用該場第一顆球有沒有 `pitchData.startSpeed`
判斷整場的追蹤資料是否存在，不要逐球判斷、也不要用年份硬編碼。

### 2.2 各項資料的「第一年」

| 資料 | 欄位 | MLB 起始 | 其他層級 |
|---|---|---|---|
| 打席結果、球數、跑壘、守備 credit | `result`/`count`/`runners[]` | **2002**（有紀錄以來） | 全層級同步 |
| 勝率、WPA、LI、drama | `homeTeamWinProbability` 等 | **2002** | **全層級全年都有**（連 ROK 都算） |
| 投球前球數 `preCount` | `playEvents[].preCount` | **2002** | 全層級 100% |
| 擊球落點座標 | `hitData.coordinates.coordX/Y` | **2005** | 全層級 2005 起 ~100% |
| 逐球唯一 ID | `playEvents[].playId` | **2005** | 全層級 2005 起 |
| 打席／事件時間戳 | `about.startTime`/`endTime` | **2010** | 全層級 2010 起 |
| 球速、位移、轉速、好球帶分區、球種 | `pitchData.*`、`details.type` | **2007**（2008 起近 100%） | 見 2.1 |
| 舊 PITCHf/x ID | `playEvents[].pfxId` | 2007–**2016**（之後消失） | 無 |
| 擊球初速／仰角／距離 | `hitData.launchSpeed` 等 | **2015** | AAA 2022／A 部分球場／ROK 2025 |
| 期望 wOBA | `contextMetrics.xWoba` | **2015**（打席的 ~77%） | AAA 幾乎沒有（≤25%）、A 跟球場走 |
| 安打機率 | `hitData.hitProbability` | **2015**（100%） | **只有 MLB 穩定**，AAA 2025 起變 0 |
| 全壘打在幾座球場會出牆 | `contextMetrics.homeRunBallparks` | **2015**（投球的 ~15%） | 幾乎只有 MLB |
| 誘導垂直位移 IVB／延伸／過壘時間 | `breaks.breakVerticalInduced`、`extension`、`plateTime` | **2017**（Hawk-Eye 換代） | 跟 2.1 同步 |
| 投手板脫離次數（牽制限制規則） | `details.disengagementNum` | **2023** | 全層級（規則） |
| 投球計時器違規 | `details.violation` | **2023** | 全層級（規則） |
| 好球帶 3D 模型 | `pitchData.strikeZoneInfo` | **2020** | 跟 2.1 同步 |
| 好球帶模型的通過座標 | `strikeZoneInfo.plateX/Y/Z` | **2022** | 同上 |
| 到好球帶邊緣距離 | `strikeZoneInfo.edgeDistance` | **2024** | 同上 |
| 好球帶寬深（ABS 用） | `pitchData.strikeZoneWidth`/`Depth` | **2025** | AAA 2023 起（ABS 試驗先在 AAA） |
| 球棒揮速／sword swing | `hitData.batSpeed`/`isSwordSwing` | **2024**（2024 33%→2026 49%） | 幾乎只有 MLB |
| ABS（機器好球帶）挑戰 | `gameData.absChallenges` | **2023** | A／AAA／MLB |
| 好球帶邊緣球的位置向量 | `strikeZoneInfo.edgePositionBall/Zone` | **2025** | AAA／MLB／ROK |
| 投手丘訪問次數 | `gameData.moundVisits` | **2018** | 全層級 |

---

## 三、JSON 完整資料結構

> 這個端點是 `feed/live` 的**嚴格超集**：對整份 JSON 做 diff，`feed/live` 沒有任何
> 一個欄位是 `withMetrics` 缺的。`withMetrics` 多出來的是 `gameData.ruleSettings`
> 與 `plays` 底下的一批進階指標（`preCount`、`defense`、`offense`、`contextMetrics`、
> `strikeZoneInfo`、WP/LI/drama、`hitProbability`、`batSpeed` 等）。

以下是整份回應 JSON 從根節點到葉節點的完整結構。型別標在每個欄位後面，
`list<T>` 代表陣列裡每個元素的型別；巢狀容器（`dict`）會繼續往下展開。
每個節點的出現率、起始年份、層級限制、陷阱與死欄位標記，見對應章節的完整表格
（三級以下先看第五、六節；`gameData`／`boxscore`／`metaData` 看第七節）。

### 3.1 頂層結構

```
{
  "gamePk":     int,     // 比賽 ID
  "link":       str,     // /api/v1.1/game/{pk}/feed/live
  "copyright":  str,     // 版權宣告，可丟
  "metaData":   { ... }, // 見 3.2、七.3
  "gameData":   { ... }, // 見 3.3、七.2 —— 比賽層級中繼：球場／天氣／規則／雙方球隊與所有球員檔案
  "liveData": {
    "plays": {
      "allPlays":     [ { ... } ], // ★ 逐打席資料，見 3.4、五；平均 76.9 個/場
      "currentPlay":  { ... },     // 全場最後一個打席的複本，= allPlays[-1]，賽後沒有額外資訊
      "scoringPlays": [ int ],     // 有得分的打席在 allPlays 的 index 清單
      "playsByInning":[ { ... } ]  // 每半局 startIndex／endIndex／該局打席 index，
                                    // 以及 hits.home[]／hits.away[]（每支安打的落點座標＋打者＋投手）
    },
    "linescore": { ... },  // 各局比分、當下攻守名單
    "boxscore":  { ... },  // 見 3.6、七.1 —— ★ 雙方球員單場＋球季累計數據
    "decisions": {         // 勝投／敗投／救援投手
      "winner": { "id": int, "fullName": str, "link": str },
      "loser":  { ... },
      "save":   { ... }
    },
    "leaders": {}           // 恆空，死資料（見四、B）
  }
}
```

### 3.2 `metaData`

```
metaData: {
  timeStamp:     str,        // 這份 JSON 的產生時間 YYYYMMDD_HHMMSS
  gameEvents:    [ ... ],    // 最後一次更新觸發的事件標記，即時推播用，回溯分析沒價值
  logicalEvents: [ ... ],
  wait:          int         // 恆為 10，死欄位
}
```

### 3.3 `gameData`（詳見七.2）

```
gameData: {
  game, datetime, status,             // 比賽基本資訊、賽程時間、比賽狀態
  teams: { home: { ... }, away: { ... } },  // 球隊檔案 + record/league/division/parentOrgId
  players: { "<id>": { ... } },       // 每位球員完整檔案（生日、身高體重、慣用手、好球帶…）
  venue, weather, gameInfo,           // 球場資訊（含全壘打牆距離）、天氣、比賽時長
  review,                             // 雙方挑戰次數
  flags,                              // noHitter／perfectGame
  probablePitchers,
  officialScorer, primaryDatacaster, secondaryDatacaster,  // secondaryDatacaster 極稀有
  ruleSettings: [ { ... } ],          // ★ withMetrics 才有：該場生效的規則清單
  moundVisits,                        // 2018 起
  absChallenges,                      // 2023 起（ABS 挑戰）
  alerts: []                          // 恆空，死欄位
}
```

### 3.4 `allPlays[]`（打席層級，詳見五）

`liveData.plays.allPlays[]` 每個元素的完整巢狀結構（134 條路徑，含結構節點）：

- `about`  (dict)
  - `atBatIndex`  (int)
  - `captivatingIndex`  (int)
  - `endTime`  (str)
  - `halfInning`  (str)
  - `hasOut`  (bool)
  - `hasReview`  (bool)
  - `inning`  (int)
  - `isComplete`  (bool)
  - `isScoringPlay`  (bool)
  - `isTopInning`  (bool)
  - `startTime`  (str)
- `actionIndex[]`  (list<int>)
- `atBatIndex`  (int)
- `awayTeamWinProbability`  (float)
- `contextMetrics`  (dict)
  - `xWoba`  (float)
- `count`  (dict)
  - `balls`  (int)
  - `outs`  (int)
  - `strikes`  (int)
- `credits[]`  (list<dict>)
  - `credit`  (str)
  - `player`  (dict)
    - `id`  (int)
- `dramaIndex`  (float)
- `flags[]`  (list<dict>)
  - `credit`  (str)
- `homeTeamWinProbability`  (float)
- `homeTeamWinProbabilityAdded`  (float)
- `leverageIndex`  (float)
- `matchup`  (dict)
  - `batSide`  (dict)
    - `code`  (str)
  - `batter`  (dict)
    - `id`  (int)
  - `batterHotColdZoneStats`  (dict)
    - `stats[]`  (list<dict>)
      - `exemptions`  (list)
      - `group`  (dict)
        - `displayName`  (str)
      - `splits[]`  (list<dict>)
        - `stat`  (dict)
          - `name`  (str)
          - `zones[]`  (list<dict>)
            - `color`  (str)
            - `temp`  (str)
            - `value`  (str)
            - `zone`  (str)
      - `type`  (dict)
        - `displayName`  (str)
  - `batterHotColdZones[]`  (list<dict>)
    - `color`  (str)
    - `temp`  (str)
    - `value`  (str)
    - `zone`  (str)
  - `pitchHand`  (dict)
    - `code`  (str)
  - `pitcher`  (dict)
    - `id`  (int)
  - `pitcherHotColdZones`  (list)
  - `postOnFirst`  (dict)
    - `id`  (int)
  - `postOnSecond`  (dict)
    - `id`  (int)
  - `postOnThird`  (dict)
    - `id`  (int)
  - `splits`  (dict)
    - `batter`  (str)
    - `menOnBase`  (str)
    - `pitcher`  (str)
- `pitchIndex[]`  (list<int>)
- `playEndTime`  (str)
- `result`  (dict)
  - `awayScore`  (int)
  - `description`  (str)
  - `event`  (str)
  - `eventType`  (str)
  - `homeScore`  (int)
  - `isOut`  (bool)
  - `rbi`  (int)
  - `type`  (str)
- `reviewDetails`  (dict)
  - `additionalReviews[]`  (list<dict>)
    - `challengeTeamId`  (int)
    - `inProgress`  (bool)
    - `isOverturned`  (bool)
    - `reviewType`  (str)
  - `challengeTeamId`  (int)
  - `inProgress`  (bool)
  - `isOverturned`  (bool)
  - `player`  (dict)
    - `id`  (int)
  - `reviewType`  (str)
- `runnerIndex[]`  (list<int>)
- `runners[]`  (list<dict>)
  - `credits[]`  (list<dict>)
    - `credit`  (str)
    - `player`  (dict)
      - `id`  (int)
    - `position`  (dict)
      - `abbreviation`  (str)
  - `details`  (dict)
    - `earned`  (bool)
    - `event`  (str)
    - `eventType`  (str)
    - `isScoringEvent`  (bool)
    - `movementReason`  (NoneType/str)
    - `playIndex`  (int)
    - `rbi`  (bool)
    - `responsiblePitcher`  (NoneType/dict)
      - `id`  (int)
    - `runner`  (dict)
      - `id`  (int)
    - `teamUnearned`  (bool)
  - `movement`  (dict)
    - `end`  (NoneType/str)
    - `isOut`  (NoneType/bool)
    - `originBase`  (NoneType/str)
    - `outBase`  (NoneType/str)
    - `outNumber`  (NoneType/int)
    - `start`  (NoneType/str)

### 3.5 `playEvents[]`（逐球／事件層級，詳見六）

`allPlays[].playEvents[]` 每個元素的完整巢狀結構（196 條路徑，含結構節點）：

- `actionPlayId`  (str)
- `awayTeamWinProbability`  (float)
- `base`  (int)
- `battingOrder`  (str)
- `contextMetrics`  (dict)
  - `averagePitchSpeedLeague`  (float)
  - `homeRunBallparks`  (int)
  - `maxPitchSpeedLeague`  (float)
- `count`  (dict)
  - `balls`  (int)
  - `outs`  (int)
  - `strikes`  (int)
- `credits[]`  (list<dict>)
  - `credit`  (str)
  - `player`  (dict)
    - `id`  (int)
  - `position`  (dict)
    - `abbreviation`  (str)
- `defense`  (dict)
  - `catcher`  (dict)
    - `id`  (int)
  - `center`  (dict)
    - `id`  (int)
  - `first`  (dict)
    - `id`  (int)
  - `left`  (dict)
    - `id`  (int)
  - `pitcher`  (dict)
    - `id`  (int)
    - `pitchHand`  (dict)
      - `code`  (str)
  - `right`  (dict)
    - `id`  (int)
  - `second`  (dict)
    - `id`  (int)
  - `shortstop`  (dict)
    - `id`  (int)
  - `third`  (dict)
    - `id`  (int)
- `details`  (dict)
  - `awayScore`  (int)
  - `ballColor`  (str)
  - `call`  (dict)
    - `code`  (str)
  - `code`  (str)
  - `description`  (str)
  - `disengagementNum`  (int)
  - `event`  (str)
  - `eventType`  (str)
  - `fromCatcher`  (bool)
  - `hasReview`  (bool)
  - `homeScore`  (int)
  - `isBall`  (bool)
  - `isInPlay`  (bool)
  - `isOut`  (bool)
  - `isScoringPlay`  (bool)
  - `isStrike`  (bool)
  - `runnerGoing`  (bool)
  - `trailColor`  (str)
  - `type`  (dict)
    - `code`  (str)
    - `description`  (str)
  - `violation`  (dict)
    - `description`  (str)
    - `player`  (dict)
      - `id`  (int)
    - `type`  (str)
- `dramaIndex`  (float)
- `endTime`  (str)
- `hitData`  (dict)
  - `batSpeed`  (float)
  - `coordinates`  (dict)
    - `coordX`  (float)
    - `coordY`  (float)
  - `hardness`  (str)
  - `hitProbability`  (float)
  - `isSwordSwing`  (bool)
  - `launchAngle`  (float)
  - `launchSpeed`  (float)
  - `location`  (str)
  - `totalDistance`  (float)
  - `trajectory`  (str)
- `homeTeamWinProbability`  (float)
- `homeTeamWinProbabilityAdded`  (float)
- `index`  (int)
- `injuryType`  (str)
- `isBaseRunningPlay`  (bool)
- `isPitch`  (bool)
- `isSubstitution`  (bool)
- `leverageIndex`  (float)
- `offense`  (dict)
  - `batter`  (dict)
    - `batSide`  (dict)
      - `code`  (str)
    - `id`  (int)
  - `batterPosition`  (dict)
    - `abbreviation`  (str)
  - `first`  (dict)
    - `id`  (int)
  - `postOnFirst`  (dict)
    - `id`  (int)
  - `postOnSecond`  (dict)
    - `id`  (int)
  - `postOnThird`  (dict)
    - `id`  (int)
  - `second`  (dict)
    - `id`  (int)
  - `third`  (dict)
    - `id`  (int)
- `officials[]`  (list<dict>)
  - `official`  (dict)
  - `officialType`  (str)
- `pfxId`  (str)
- `pitchData`  (dict)
  - `breaks`  (dict)
    - `breakAngle`  (float)
    - `breakHorizontal`  (float)
    - `breakLength`  (float)
    - `breakVertical`  (float)
    - `breakVerticalInduced`  (float)
    - `breakY`  (float)
    - `spinDirection`  (int)
    - `spinRate`  (int)
  - `coordinates`  (dict)
    - `aX`  (float)
    - `aY`  (float)
    - `aZ`  (float)
    - `pX`  (float)
    - `pZ`  (float)
    - `pfxX`  (float)
    - `pfxZ`  (float)
    - `vX0`  (float)
    - `vY0`  (float)
    - `vZ0`  (float)
    - `x`  (float)
    - `x0`  (float)
    - `y`  (float)
    - `y0`  (float)
    - `z0`  (float)
  - `endSpeed`  (float)
  - `extension`  (float)
  - `plateTime`  (float)
  - `startSpeed`  (float)
  - `strikeZoneBottom`  (float)
  - `strikeZoneDepth`  (float)
  - `strikeZoneInfo`  (dict)
    - `baseballDiameterInches`  (float)
    - `depthInches`  (float)
    - `edgeDistance`  (float)
    - `edgePositionBall`  (dict)
      - `x`  (float)
      - `y`  (float)
      - `z`  (float)
    - `edgePositionZone`  (dict)
      - `x`  (float)
      - `y`  (float)
      - `z`  (float)
    - `isStrike`  (bool)
    - `plateX`  (float)
    - `plateY`  (float)
    - `plateZ`  (float)
    - `strikeZoneBottom`  (float)
    - `strikeZoneCornerRadiusInches`  (float)
    - `strikeZoneFlat`  (bool)
    - `strikeZoneRounded`  (bool)
    - `strikeZoneTop`  (float)
    - `widthInches`  (float)
  - `strikeZoneTop`  (float)
  - `strikeZoneWidth`  (float)
  - `typeConfidence`  (float)
  - `zone`  (int)
- `pitchNumber`  (int)
- `playId`  (str)
- `player`  (dict)
  - `id`  (int)
- `position`  (dict)
  - `abbreviation`  (str)
- `preCount`  (dict)
  - `balls`  (int)
  - `outs`  (int)
  - `strikes`  (int)
- `replacedPlayer`  (dict)
  - `id`  (int)
- `reviewDetails`  (dict)
  - `challengeTeamId`  (int)
  - `inProgress`  (bool)
  - `isOverturned`  (bool)
  - `player`  (dict)
    - `id`  (int)
  - `reviewType`  (str)
- `startTime`  (str)
- `type`  (str)
- `umpire`  (dict)
  - `id`  (int)

### 3.6 `boxscore`（詳見七.1）

```
liveData.boxscore.teams.{home,away}: {
  players: {
    "<id>": {
      stats:       { batting, pitching, fielding },       // 該場數據
      seasonStats: { batting, pitching, fielding },       // ★ 到這場為止的球季累計
      gameStatus:  { isCurrentBatter, isCurrentPitcher, isOnBench, isSubstitute },
      position, allPositions, battingOrder, status,
      parentTeamId, jerseyNumber
    }
  },
  batters, pitchers, bench, bullpen, battingOrder,  // 各類球員 id 清單
  teamStats: { batting, pitching, fielding },        // 該隊全隊單場數據
  info, note                                          // 官方 box score 附註
},
liveData.boxscore.officials,
liveData.boxscore.topPerformers,    // Bill James Game Score
liveData.boxscore.pitchingNotes
```

---

## 四、死資料清單

### A. 端點根本不回傳（0 筆）

| 欄位 | 實測 |
|---|---|
| `allPlays[].contextMetrics.catchProbability` | 30,127 個打席**一次都沒出現**。Statcast 的接殺機率不會從這個端點出來 |
| `playEvents[].contextMetrics.averagePitchSpeedPlayer` | 109,151 個事件**一次都沒出現** |
| `playEvents[].contextMetrics.maxPitchSpeedPlayer` | 同上，0 筆 |
| `playEvents[].contextMetrics.pitchSpeedPlayerRank` | 同上，0 筆（曾以為是「這球球速在該投手的百分位」，不存在） |

`playEvents[].contextMetrics` 這個 dict **本身 100% 存在**，但裡面實際上只可能有
`homeRunBallparks`（約 3.6% 的事件），其餘時候就是空 dict——它存在不代表有內容。

### B. 永遠是空容器

| 欄位 | 實測 |
|---|---|
| `allPlays[].matchup.pitcherHotColdZones` | 30,127 次全是 `[]` |
| `gameData.alerts` | 392 場全是 `[]` |
| `liveData.leaders.hitDistance` / `.hitSpeed` / `.pitchSpeed` | 392 場全是 `{}`（這裡不會有單場之最） |
| `gameData.teams.{home,away}.record.records` | 392 場全是 `{}` |

### C. 值恆定、零資訊量

| 欄位 | 恆定值 | 樣本 |
|---|---|---|
| `pitchData.strikeZoneInfo.strikeZoneRounded` | `False` | 17,878/17,878 |
| `pitchData.strikeZoneInfo.strikeZoneCornerRadiusInches` | `0.0` | 17,878/17,878 |
| `pitchData.strikeZoneInfo.baseballDiameterInches` | `2.9` | 3,899/3,899（棒球直徑常數，不是量測值） |
| `pitchData.breaks.breakY` | `24.0`（少數 `19.2`） | 39,793 筆只有兩種值 |
| boxscore `stats.fielding.fielding` | `'.000'` | 全部（單場守備率沒有實際計算） |
| boxscore `stats.fielding.caughtStealingPercentage` | `'.---'` | 全部 |
| boxscore `stats.pitching.passedBall` | `0` | 全部（捕逸只記在 fielding） |
| `allPlays[].result.type` | `'atBat'` | 30,127/30,127 |
| `metaData.wait` | `10` | 392/392 |

> 「恆定」不等於「死」：`gameData.flags.noHitter`、`batting.groundIntoTriplePlay`、
> `gameData.game.type='R'` 在樣本裡也恆定，但那是因為 392 場剛好沒抽到無安打比賽／
> 三殺／季後賽。上表只列**結構上就不會變**的。

### D. 存在但極稀有

| 欄位 | 實測量 | 說明 |
|---|---|---|
| `matchup.batterHotColdZones[]` | 78 個元素，全在 **2026 MLB**（= 6 個打席） | 轉播用熱區圖素材（9 宮格＋角落），只掛在全場最後一個打席，值是球員生涯／近況數字而非本場算出，**不能當統計來源** |
| `matchup.batterHotColdZoneStats` | 6 筆，全在 2026 MLB | 同上的結構化版本 |
| `contextMetrics.averagePitchSpeedLeague` / `maxPitchSpeedLeague` | 各 40 筆，**只有 2023 年的 A 級** | 等同不存在 |
| `playEvents[].umpire` | 21 筆 / 109,151 | 裁判換人之類的特殊事件 |
| `playEvents[].credits[]` | 9 筆，全是 `f_foul_error` | 跟 `runners[].credits[]` 是不同東西 |
| `playEvents[].injuryType` | 22 筆（`shoulder`/`hand`/`head`/`ankle`…） | 當場受傷退場才有 |
| `playEvents[].pfxId` | 16,306 筆，**只有 2007–2016 MLB** | PITCHf/x 時代舊 ID，2017 起消失 |
| `playEvents[].details.violation` | 44 筆（2023 起） | 投球計時器／脫離投手板／打者暫停違規 |
| `allPlays[].reviewDetails` | 54 個打席（0.2%），MLB／AAA | 重播挑戰 |
| `gameData.absChallenges` | 19 場（2023 起，A／AAA／MLB） | 機器好球帶挑戰制度 |
| `playEvents[].offense.postOnFirst` | 34 筆 | 先前文件說「沒有這個欄位」是錯的，只是極少 |
| `gameData.secondaryDatacaster` | 18 場 | 幾乎都缺 |

### E. 陷阱欄位（有值，直接用會算錯）

| 欄位 | 陷阱 |
|---|---|
| `allPlays[].contextMetrics.xWoba` | 單位是 **wOBA × 100**（全壘打實測最高 201.8、出局 0.0），但**保送與觸身球恆為 `0.7`**——那是未乘 100 的原始權重，MLB 自己單位不一致。另外只有約 77% 的 MLB 打席有值（三振等沒有擊球資料的打席沒有） |
| `playEvents[].homeTeamWinProbability` / `.homeTeamWinProbabilityAdded` / `.leverageIndex` / `.dramaIndex` | **只有 `isBaseRunningPlay=True` 的跑壘事件才有**（1,440 筆 / 109,151），投球事件根本沒有這些 key。實測值是真的（例：牽制成功 WPA=+9.8、LI=2.43、drama=126），**不是**先前文件寫的「恆為 0」——那是把「key 不存在」誤讀成 0。**這是取得盜壘／牽制／暴投等跑壘事件 WPA 的唯一管道** |
| `allPlays[].dramaIndex` | 實測範圍 **5 ~ 687**，不是 0–100 |
| `playEvents[].pitchNumber` | 是**該打席內第幾球**（值分布 1×28,325 ≈ 打席數），不是投手單場累計球數 |
| `pitchData.strikeZoneInfo.widthInches` / `.depthInches` | 有 4,335 筆是 `0.0`（壞值），用之前先濾掉 0 |
| `hitData.hardness` | 20,600 筆裡 19,218 筆是 `'medium'`（93%），沒有鑑別度；要判斷強擊球請用 `launchSpeed` |
| `pitchData.coordinates.y0` | 不是第三個座標軸，是 `x0`/`z0` 所在平面距本壘板幾呎（2008 起恆為 50，PITCHf/x 早期有 40/45/50/55，2007 年還會場中切換） |
| `details.type.code` | 球種代碼在 `details.type` 存在時仍有約 28% 缺席（`description` 會是 `'Unknown'`），一律用 `.get("code","")` |
| `isBaseRunningPlay` / `isSubstitution` / `details.runnerGoing` | 「存在即為真」的旗標（值恆為 `True`），**key 不存在 = False**，不能用 `.get(k) == False` 判斷 |
| `allPlays[].matchup.batter` / `.pitcher` | 是「打席**結束時**」的打者／投手。中途換投或代打時前面幾球其實是別人的——投手可用每球的 `playEvents[].defense.pitcher.id` 校正，打者沒有逐球欄位，只能靠 `offensive_substitution` 事件的位置切割（`extract.py` 已處理） |
| `liveData.leaders` | 見死資料 B，永遠空，別在這裡找單場最速球 |

---

## 五、打席層級欄位（`allPlays[]`）

樣本 30,127 個打席。

| 欄位 | 型別 | 出現率 | 起始年／層級 | 說明 | extract.py |
|---|---|---|---|---|---|
| `result` | dict | 100% | 全 | 打席最終結果（見 5.1） | ✅ `.eventType`/`.event` |
| `about` | dict | 100% | 全 | 局數／時間／旗標（見 5.2） | ✅ `.inning` |
| `count` | dict | 100% | 全 | 打席**結束當下**的 balls/strikes/outs | ✅ `pa_final_*` |
| `matchup` | dict | 100% | 全 | 投打對戰（見 5.3） | ✅ 部分 |
| `runners[]` | list | 平均 1.41 筆/打席 | 全 | 跑壘與守備 credit（見 5.4） | ✅ `_extract_runners()` |
| `playEvents[]` | list | 平均 3.62 筆/打席 | 全 | 逐球／逐動作（見第六節） | ✅ 主來源 |
| `pitchIndex[]` | list[int] | 100% | 全 | `playEvents` 中投球事件的索引 | ❌ |
| `actionIndex[]` | list[int] | 100%（22% 非空） | 全 | 動作事件的索引 | ❌ |
| `runnerIndex[]` | list[int] | 100% | 全 | `runners[]` 對應索引 | ❌ |
| `atBatIndex` | int | 100% | 全 | 該打席在全場的序號（0 起算） | ❌ |
| `playEndTime` | str | 73% | **2010 起** | 打席結束時間戳 | ❌ |
| `credits[]` | list | 平均 3.75 筆 | 全 | `b_pa`／`p_pa`／`b_ab`／`p_ab`，資訊量低於 `result.eventType` | ❌ |
| `flags[]` | list | 7.5% 非空 | 全 | `t_double_play`／`b_gnd_into_dp`／`b_foul_out`／`b_sac_fly`／`b_sac_bunt`／`b_gnd_rule_double` 等，**判斷雙殺與犧牲打最乾淨的來源** | ❌ |
| `homeTeamWinProbability` | float 0–100 | 100% | **2002 起全層級** | 打席結束當下主隊勝率（%） | ✅ `home_wp` |
| `awayTeamWinProbability` | float | 100% | 全 | 恆等於 `100 − home_wp` | ❌（可反推） |
| `homeTeamWinProbabilityAdded` | float | 100% | 全 | 這個打席讓主隊勝率增減幾個百分點（WPA，主隊視角，實測 −64.4 ~ +75.8） | ✅ `wpa` |
| `leverageIndex` | float | 98.7% | 全 | 局勢緊張度（1.0 = 平均，實測 0 ~ 9.25） | ✅ `leverage_index` |
| `dramaIndex` | float | 98.7% | 全 | MLB 的精彩度指標，**實測 5 ~ 687** | ✅ `drama_index` |
| `contextMetrics.xWoba` | float | MLB 約 77% | **2015 起**，MLB 為主 | 期望 wOBA × 100，**BB/HBP 恆 0.7**（見陷阱欄位） | ✅ `pa_xwoba` |
| `reviewDetails` | dict | 0.2% | 2011 起，MLB／AAA | `isOverturned`／`reviewType`（`MJ`/`MF`/`MA`/`NH`…）／`challengeTeamId`／`player`（2026 新增，ABS 挑戰發起者）／`additionalReviews[]` | ❌ |

### 5.1 `result`

| 欄位 | 說明 |
|---|---|
| `type` | 恆為 `'atBat'`（死欄位） |
| `event` | 人類可讀：`Strikeout`／`Groundout`／`Single`… |
| `eventType` | 機器可讀：`field_out`(39%)／`strikeout`(21%)／`single`(15%)／`walk`(9%)… |
| `description` | 完整播報文字 |
| `rbi` | 打點 0~4 |
| `awayScore`／`homeScore` | 打席後比分 |
| `isOut` | 打者是否出局 |

### 5.2 `about`

| 欄位 | 出現率 | 說明 |
|---|---|---|
| `atBatIndex`／`halfInning`／`isTopInning`／`inning` | 100% | 局數資訊 |
| `isComplete`／`isScoringPlay`／`hasOut`／`hasReview` | 100% | 打席狀態旗標 |
| `captivatingIndex` | 100% | 舊版精彩度（0~95，52% 是 0），`dramaIndex` 是進階版 |
| `startTime`／`endTime` | 73%（**2010 起**） | 打席起訖時間戳 |

### 5.3 `matchup`

| 欄位 | 出現率 | 說明 |
|---|---|---|
| `batter`／`pitcher` | 100% | `{id, fullName, link}`，**打席結束時的人**（見陷阱欄位） |
| `batSide`／`pitchHand` | 100% | `{code:'R'/'L', description}` |
| `splits` | 100% | `{batter:'vs_RHP'/'vs_LHP', pitcher:'vs_RHB'/'vs_LHB', menOnBase:'Empty'/'Men_On'/'RISP'/'Loaded'}`——**分項統計的分組鍵直接給你，不用自己算** |
| `postOnFirst`／`postOnSecond`／`postOnThird` | 34%／20%／11% | 打席**結束後**壘上跑者（沒人就沒有 key） |
| `batterHotColdZones` | 99.7% 是空的 | 見死資料 D |
| `pitcherHotColdZones` | **永遠空** | 見死資料 B |

### 5.4 `runners[]`（42,411 筆）

跑壘與守備 credit 的唯一來源。`extract.py` 只在打席最後一球掛上這份資料。

| 欄位 | 說明 |
|---|---|
| `movement.originBase`／`.start`／`.end`／`.outBase` | 起始壘包／本次移動起點／終點（`1B`/`2B`/`3B`/`score`）／被觸殺在哪個壘（null = 沒有該狀態） |
| `movement.isOut`／`.outNumber` | 是否出局、是該半局第幾個出局數 |
| `details.event`／`.eventType` | 造成這次跑壘的事件 |
| `details.movementReason` | 移動原因：`r_adv_force`／`r_adv_play`／`r_force_out`／`r_stolen_base_2b`…**算盜壘與推進最準的欄位** |
| `details.isScoringEvent`／`.rbi`／`.earned`／`.teamUnearned` | 是否得分／算打點／自責分／球隊非自責 |
| `details.responsiblePitcher` | 該得分算在哪個投手頭上（換投後繼承跑者的歸屬，只在得分時有值） |
| `details.playIndex` | ★ **這次跑壘發生在 `playEvents[]` 的哪個 index**，可把跑壘精準對到某一顆球 |
| `details.runner` | `{id, fullName, link}` |
| `credits[]` | 守備 credit：`f_putout`／`f_assist`／`f_fielded_ball`／`f_throwing_error` ＋ 該野手的 `player` 與 `position`，**自算守備數據的原始素材** |

### 5.5 完整欄位總表（打席層級，134 條路徑）

涵蓋 `allPlays[]` 底下所有偵測到的欄位路徑，含結構節點（parent dict／list 本身，
「節點」欄標「容器」）。「已抓」對照 `site_builder/sync/extract.py` 目前實作，
「否」不代表建議補抓，實際優先順序見第八節 8.3。

| 路徑 | 節點 | 型別 | 覆蓋率 | 年份範圍 | 層級 | 狀態 | 已抓 (extract.py) | 備註／值域 |
|---|---|---|---|---|---|---|---|---|
| `about` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `about.atBatIndex` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 值域 0 ~ 124 |
| `about.captivatingIndex` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 舊版精彩度 0–95（52% 是 0），dramaIndex 是進階版 |
| `about.endTime` | 欄位 | str | 72.3% | 2010–2026 | 全層級 | 受年份／層級限制 | 否 | 打席結束時間戳，2010 年起才有 |
| `about.halfInning` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 上／下半局 |
| `about.hasOut` | 欄位 | bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 常見值：True(20037)、False(10090) |
| `about.hasReview` | 欄位 | bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 常見值：False(30071)、True(54) |
| `about.inning` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 第幾局 |
| `about.isComplete` | 欄位 | bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 常見值：True(30125)、False(2) |
| `about.isScoringPlay` | 欄位 | bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 這個打席是否有得分 |
| `about.isTopInning` | 欄位 | bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 常見值：True(15330)、False(14797) |
| `about.startTime` | 欄位 | str | 72.3% | 2010–2026 | 全層級 | 受年份／層級限制 | 否 | 打席開始時間戳，2010 年起才有 |
| `actionIndex` | 容器 | list | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `actionIndex[]` | 欄位 | int | 21.9% | 2002–2026 | 全層級 | 全年可用 | 否 | playEvents 中動作事件的索引 |
| `atBatIndex` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 該打席在全場的序號（0 起算） |
| `awayTeamWinProbability` | 欄位 | float | 100.0% | 2002–2026 | 全層級 | 陷阱 | 否 | 恆等於 100 − 主隊勝率，不必另存 |
| `contextMetrics` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `contextMetrics.xWoba` | 欄位 | float | 14.5% | 2015–2026 | MLB、AAA、A | 陷阱 | 是 | 期望 wOBA × 100（HR 最高 201.8），但保送與觸身球恆為 0.7，單位不一致 |
| `count` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `count.balls` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 打席結束當下的壞球數 |
| `count.outs` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 打席結束當下的出局數 |
| `count.strikes` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 打席結束當下的好球數 |
| `credits` | 容器 | list | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `credits[]` | 容器 | dict | 374.7% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `credits[].credit` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | b_pa／p_pa／b_ab／p_ab，資訊量低於 result.eventType |
| `credits[].player` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `credits[].player.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 值域 110029 ~ 837088 |
| `dramaIndex` | 欄位 | float | 98.7% | 2002–2026 | 全層級 | 陷阱 | 是 | MLB 的精彩度指標，實測範圍 5 ~ 687，不是 0–100 |
| `flags` | 容器 | list | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `flags[]` | 容器 | dict | 7.4% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `flags[].credit` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 特殊計分旗標：t_double_play／b_gnd_into_dp／b_foul_out／b_sac_fly／b_sac_bunt，判斷犧牲打與雙殺最乾淨 |
| `homeTeamWinProbability` | 欄位 | float | 100.0% | 2002–2026 | 全層級 | 陷阱 | 是 | 打席結束當下主隊勝率（%），2002 年起連小聯盟都有 |
| `homeTeamWinProbabilityAdded` | 欄位 | float | 100.0% | 2002–2026 | 全層級 | 陷阱 | 是 | WPA：這個打席讓主隊勝率增減幾個百分點（實測 −64.4 ~ +75.8） |
| `leverageIndex` | 欄位 | float | 98.7% | 2002–2026 | 全層級 | 陷阱 | 是 | 局勢緊張度 LI，1.0 為平均（實測 0 ~ 9.25） |
| `matchup` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `matchup.batSide` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `matchup.batSide.code` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 打者左右打（R／L） |
| `matchup.batter` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `matchup.batter.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 陷阱 | 是 | 打席「結束時」的打者，中途代打時前面幾球其實是別人的 |
| `matchup.batterHotColdZoneStats` | 容器 | dict | 0.0% | 2026–2026 | MLB | 稀有 | 否 |  |
| `matchup.batterHotColdZoneStats.stats` | 容器 | list | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 |  |
| `matchup.batterHotColdZoneStats.stats[]` | 容器 | dict | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 |  |
| `matchup.batterHotColdZoneStats.stats[].exemptions` | 容器 | list | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 |  |
| `matchup.batterHotColdZoneStats.stats[].group` | 容器 | dict | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 |  |
| `matchup.batterHotColdZoneStats.stats[].group.displayName` | 欄位 | str | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 | 常見值：hitting(6) |
| `matchup.batterHotColdZoneStats.stats[].splits` | 容器 | list | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 |  |
| `matchup.batterHotColdZoneStats.stats[].splits[]` | 容器 | dict | 300.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 |  |
| `matchup.batterHotColdZoneStats.stats[].splits[].stat` | 容器 | dict | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 |  |
| `matchup.batterHotColdZoneStats.stats[].splits[].stat.name` | 欄位 | str | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 | 常見值：battingAverage(6)、onBasePlusSlugging(6)、exitVelocity(6) |
| `matchup.batterHotColdZoneStats.stats[].splits[].stat.zones` | 容器 | list | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 |  |
| `matchup.batterHotColdZoneStats.stats[].splits[].stat.zones[]` | 容器 | dict | 1300.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 |  |
| `matchup.batterHotColdZoneStats.stats[].splits[].stat.zones[].color` | 欄位 | str | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 | 常見值：rgba(214, 41, 52, .55)(91)、rgba(6, 90, 238, .55)(81)、rgba(255, 255, 255, 0.55)(25) |
| `matchup.batterHotColdZoneStats.stats[].splits[].stat.zones[].temp` | 欄位 | str | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 | 常見值：hot(91)、cold(81)、lukewarm(25) |
| `matchup.batterHotColdZoneStats.stats[].splits[].stat.zones[].value` | 欄位 | str | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 | 常見值：.429(9)、.333(8)、.250(8) |
| `matchup.batterHotColdZoneStats.stats[].splits[].stat.zones[].zone` | 欄位 | str | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 | 常見值：01(18)、02(18)、03(18) |
| `matchup.batterHotColdZoneStats.stats[].type` | 容器 | dict | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 |  |
| `matchup.batterHotColdZoneStats.stats[].type.displayName` | 欄位 | str | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 | 常見值：hotColdZones(6) |
| `matchup.batterHotColdZones` | 欄位 | list | 100.0% | 2002–2026 | 全層級 | 死欄位 | 否 | 99.7% 是空的；有值的 78 筆全在 2026 MLB，且是轉播用的生涯熱區素材，不是本場資料 |
| `matchup.batterHotColdZones[]` | 容器 | dict | 0.3% | 2026–2026 | MLB | 稀有 | 否 |  |
| `matchup.batterHotColdZones[].color` | 欄位 | str | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 | 常見值：rgba(6, 90, 238, .55)(31)、rgba(214, 41, 52, .55)(29)、rgba(150, 188, 255, .55)(8) |
| `matchup.batterHotColdZones[].temp` | 欄位 | str | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 | 常見值：cold(31)、hot(29)、cool(8) |
| `matchup.batterHotColdZones[].value` | 欄位 | str | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 | 熱區格的數值（字串），是球員生涯／近況數字 |
| `matchup.batterHotColdZones[].zone` | 欄位 | str | 100.0% | 2026–2026 | MLB | 受年份／層級限制 | 否 | 常見值：01(6)、02(6)、03(6) |
| `matchup.pitchHand` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `matchup.pitchHand.code` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 投手左右投（R／L） |
| `matchup.pitcher` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `matchup.pitcher.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 陷阱 | 是 | 打席「結束時」的投手，中途換投時要改用每球的 defense.pitcher.id |
| `matchup.pitcherHotColdZones` | 欄位 | list | 100.0% | 2002–2026 | 全層級 | 死欄位 | 否 | 永遠是空陣列，30,127 個打席都沒有內容 |
| `matchup.postOnFirst` | 容器 | dict | 34.2% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `matchup.postOnFirst.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 打席結束後一壘的跑者 |
| `matchup.postOnSecond` | 容器 | dict | 20.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `matchup.postOnSecond.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 打席結束後二壘的跑者 |
| `matchup.postOnThird` | 容器 | dict | 11.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `matchup.postOnThird.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 打席結束後三壘的跑者 |
| `matchup.splits` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `matchup.splits.batter` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | vs_RHP／vs_LHP，分項統計的分組鍵直接給你 |
| `matchup.splits.menOnBase` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | Empty／Men_On／RISP／Loaded，得點圈情境直接給你 |
| `matchup.splits.pitcher` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | vs_RHB／vs_LHB |
| `pitchIndex` | 容器 | list | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `pitchIndex[]` | 欄位 | int | 336.4% | 2002–2026 | 全層級 | 全年可用 | 否 | playEvents 中投球事件的索引 |
| `playEndTime` | 欄位 | str | 72.3% | 2010–2026 | 全層級 | 受年份／層級限制 | 否 | 打席結束時間戳，2010 年起 |
| `result` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `result.awayScore` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 常見值：0(8765)、1(5146)、2(3908) |
| `result.description` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 完整播報文字 |
| `result.event` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 打席結果的人類可讀名稱 |
| `result.eventType` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 打席結果代碼（field_out 39%／strikeout 21%／single 15%／walk 9%…），分析主鍵 |
| `result.homeScore` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 常見值：0(9783)、1(4902)、2(3837) |
| `result.isOut` | 欄位 | bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 打者是否出局 |
| `result.rbi` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 這個打席的打點（0–4） |
| `result.type` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 死欄位 | 否 | 恆為 atBat，沒有資訊量 |
| `reviewDetails` | 容器 | dict | 0.2% | 2011–2026 | MLB、AAA | 稀有 | 否 |  |
| `reviewDetails.additionalReviews` | 容器 | list | 3.7% | 2021–2023 | MLB、AAA | 受年份／層級限制 | 否 |  |
| `reviewDetails.additionalReviews[]` | 容器 | dict | 100.0% | 2021–2023 | MLB、AAA | 受年份／層級限制 | 否 |  |
| `reviewDetails.additionalReviews[].challengeTeamId` | 欄位 | int | 100.0% | 2021–2023 | MLB、AAA | 受年份／層級限制 | 否 | 常見值：114(1)、533(1) |
| `reviewDetails.additionalReviews[].inProgress` | 欄位 | bool | 100.0% | 2021–2023 | MLB、AAA | 受年份／層級限制 | 否 | 常見值：False(2) |
| `reviewDetails.additionalReviews[].isOverturned` | 欄位 | bool | 100.0% | 2021–2023 | MLB、AAA | 受年份／層級限制 | 否 | 常見值：False(2) |
| `reviewDetails.additionalReviews[].reviewType` | 欄位 | str | 100.0% | 2021–2023 | MLB、AAA | 受年份／層級限制 | 否 | 常見值：MC(1)、MJ(1) |
| `reviewDetails.challengeTeamId` | 欄位 | int | 87.0% | 2014–2026 | MLB、AAA | 受年份／層級限制 | 否 | 常見值：116(9)、114(5)、110(3) |
| `reviewDetails.inProgress` | 欄位 | bool | 100.0% | 2011–2026 | MLB、AAA | 受年份／層級限制 | 否 | 常見值：False(54) |
| `reviewDetails.isOverturned` | 欄位 | bool | 100.0% | 2011–2026 | MLB、AAA | 受年份／層級限制 | 否 | 重播後是否改判（樣本 54 次挑戰中 22 次改判） |
| `reviewDetails.player` | 容器 | dict | 9.3% | 2026–2026 | MLB、AAA | 受年份／層級限制 | 否 |  |
| `reviewDetails.player.id` | 欄位 | int | 100.0% | 2026–2026 | MLB、AAA | 受年份／層級限制 | 否 | 2026 新增，ABS 挑戰的發起球員 |
| `reviewDetails.reviewType` | 欄位 | str | 100.0% | 2011–2026 | MLB、AAA | 受年份／層級限制 | 否 | 重播類型代碼 MJ／MF／MA／NH… |
| `runnerIndex` | 容器 | list | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `runnerIndex[]` | 欄位 | int | 140.8% | 2002–2026 | 全層級 | 全年可用 | 否 | runners 對應的索引 |
| `runners` | 容器 | list | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `runners[]` | 容器 | dict | 140.8% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `runners[].credits` | 容器 | list | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `runners[].credits[]` | 容器 | dict | 84.2% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `runners[].credits[].credit` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 守備 credit：f_putout／f_assist／f_fielded_ball／f_throwing_error，自算守備數據的素材 |
| `runners[].credits[].player` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `runners[].credits[].player.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 值域 110029 ~ 836582 |
| `runners[].credits[].position` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `runners[].credits[].position.abbreviation` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 該守備 credit 的守位 |
| `runners[].details` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `runners[].details.earned` | 欄位 | bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 是否為投手自責分 |
| `runners[].details.event` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 常見值：Single(8228)、Strikeout(6217)、Groundout(6126) |
| `runners[].details.eventType` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 常見值：field_out(12622)、single(8228)、strikeout(6217) |
| `runners[].details.isScoringEvent` | 欄位 | bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 這次跑壘是否得分 |
| `runners[].details.movementReason` | 欄位 | NoneType/str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 移動原因：r_adv_force／r_adv_play／r_force_out／r_stolen_base_2b…算盜壘與推進最準 |
| `runners[].details.playIndex` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 這次跑壘發生在 playEvents 的哪個 index，可精準對到某一顆球 |
| `runners[].details.rbi` | 欄位 | bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 這次得分是否算打點 |
| `runners[].details.responsiblePitcher` | 欄位 | NoneType/dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `runners[].details.responsiblePitcher.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 這分算在哪個投手頭上（繼承跑者的歸屬） |
| `runners[].details.runner` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `runners[].details.runner.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 跑者 |
| `runners[].details.teamUnearned` | 欄位 | bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 是否為球隊非自責分 |
| `runners[].movement` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `runners[].movement.end` | 欄位 | NoneType/str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 本次移動的終點：1B／2B／3B／score |
| `runners[].movement.isOut` | 欄位 | NoneType/bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 這次跑壘是否出局 |
| `runners[].movement.originBase` | 欄位 | NoneType/str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 這名跑者這個打席的起始壘包 |
| `runners[].movement.outBase` | 欄位 | NoneType/str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 在哪個壘包被觸殺 |
| `runners[].movement.outNumber` | 欄位 | NoneType/int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 是該半局第幾個出局數 |
| `runners[].movement.start` | 欄位 | NoneType/str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 本次移動的起點（null = 打者從打擊區出發） |

---

## 六、逐球／事件層級欄位（`playEvents[]`）

樣本 109,151 個事件。`type` 的分布：
`pitch` 98,850（90.6%）／`action` 7,813／`pickoff` 2,135／`no_pitch` 236／`stepoff` 117。
`isPitch=True` 完全等同 `type=='pitch'`。

### 6.1 事件頂層

| 欄位 | 型別 | 出現率 | 起始年 | 說明 | extract.py |
|---|---|---|---|---|---|
| `type` | str | 100% | 全 | 見上 | ✅（`pickoff`/`stepoff` 存入 `events_json`） |
| `isPitch` | bool | 100% | 全 | 篩選投球 | ✅ |
| `index` | int | 100% | 全 | 事件在 `playEvents[]` 的序號 | ✅（非投球事件） |
| `details` | dict | 100% | 全 | 結果細節（見 6.2） | ✅ 部分 |
| `count` | dict | 100% | 全 | 這球**投完之後**的 balls/strikes/outs | ✅ |
| `preCount` | dict | **100%，2002 起全層級** | 全 | 這球**投出之前**的 balls/strikes/**outs**。實測 109,151/109,151 全部都有——`extract.py` 裡「缺 `preCount` 時手動累加」的 fallback 實際上永遠不會觸發 | ✅ |
| `contextMetrics` | dict | 100%（內容多半空） | 全 | 只可能有 `homeRunBallparks` | ✅ |
| `defense` | dict | 98.6% | 全 | 這球當下 9 個守備位置的球員（`pitcher` 另含 `pitchHand`）。**`defense.pitcher.id` 是逐球校正投手身分的唯一依據** | ✅ 濃縮 |
| `offense` | dict | 98.6% | 全 | 這球當下的打者（含 `batSide`）、`batterPosition`、投球**前**壘上跑者 `first`/`second`/`third`，以及 `postOnFirst`(34 筆)/`postOnSecond`/`postOnThird` | ✅ 濃縮 |
| `officials[]` | list | 98.6%（平均 3.13 位） | 全 | 該球場上裁判：`Home Plate`／`First Base`／`Third Base`／`Second Base`（小聯盟常只有 2–3 位） | ❌ |
| `playId` | str(UUID) | 92.7%（投球事件 ~100%） | **2005 起** | 該球的全域唯一 ID，可對應外部資料 | ✅ |
| `pitchNumber` | int | 90.7% | 全 | **該打席內第幾球**（含界外） | ✅ |
| `pitchData` | dict | 90.6% | 全（物理量另計） | 見 6.3 | ✅ |
| `hitData` | dict | 24.7% | 全 | 見 6.4。⚠️ **2024 起揮空的球也會有 `hitData`**（只帶 `batSpeed`/`isSwordSwing`），26,938 筆裡只有 20,600 筆是真的擊球進場——判斷是否擊球要用 `details.isInPlay` 或 `hitData.trajectory` | ✅ |
| `startTime`／`endTime` | str | 75.6% | **2010 起** | 事件起訖時間戳 | ❌ |
| `player` | dict | 6.8% | 全 | 非投球事件的當事球員 | ❌ |
| `isSubstitution`／`position`／`battingOrder`／`replacedPlayer` | — | 3.3%／3.3%／1.6%／1.4% | 全 | 換人事件：換上誰、守什麼位置、打序、換下誰。**`replacedPlayer` 是判斷代打／中途換人的關鍵**（`extract.py` 已用） | 部分（打者切割邏輯） |
| `isBaseRunningPlay` | bool | 1.3%（恆 True） | 全 | 跑壘事件旗標 | ❌ |
| `homeTeamWinProbability`／`awayTeamWinProbability`／`homeTeamWinProbabilityAdded`／`leverageIndex`／`dramaIndex` | float | 1.3% | 全 | **只有跑壘事件才有**（與 `isBaseRunningPlay` 完全同步，1,440 筆），值是真的。**盜壘／牽制／暴投的 WPA 只能從這裡拿** | ❌ ← 建議補抓 |
| `actionPlayId` | str | 1.4% | 全 | 動作事件的 ID | ❌ |
| `base` | int | 0.1% | 全 | 跑壘事件的目標壘包（1/2/3） | ❌ |
| `reviewDetails` | dict | 0.1% | 2017 起 | 事件層級的重播挑戰 | ❌ |
| `pfxId` | str | 14.9% | **2007–2016 MLB only** | PITCHf/x 舊 ID | ❌ |
| `umpire`／`injuryType`／`credits[]` | — | 各 ~20 筆 | — | 見死資料 D | ❌ |

### 6.2 `details`

| 欄位 | 出現率 | 說明 | extract.py |
|---|---|---|---|
| `description` | 99.9% | 這球／這個動作的播報文字 | ✅ `result_desc` |
| `isOut`／`hasReview` | 100% | 是否造成出局、是否申請重播 | 部分 |
| `code` | 92.8% | 結果代碼：`B`(壞球)／`C`(看見好球)／`F`(界外)／`X`(擊出出局)／`S`(揮空)／`D`(擊出安打)… | ✅ `result_code` |
| `call` | 90.7% | `{code, description}`，與 `code` 同義的裁判判決 | ❌ |
| `isStrike`／`isBall`／`isInPlay` | 90.7%（= 投球事件） | 好球／壞球／擊入場 | ✅ |
| `type` | 51.1%（**2007 起**） | `{code, description}` 球種。**`code` 在 `type` 存在時仍有 28% 缺席**（`description='Unknown'`） | ✅ `pitch_type`/`pitch_name` |
| `ballColor`／`trailColor` | 85.9%／51.1% | 轉播動畫顏色，無分析價值 | ❌ |
| `event`／`eventType` | 7.2% | **非投球動作**的分類：`pitching_substitution`(2,257)／`game_advisory`(1,524)／`offensive_substitution`(551)／`stolen_base_2b`／`defensive_switch`／`wild_pitch`… | ❌ |
| `awayScore`／`homeScore`／`isScoringPlay` | 7.2% | 動作事件當下的比分 | ❌ |
| `disengagementNum` | 4.4%（**2023 起**） | 該打席第幾次脫離投手板（牽制次數限制規則） | ✅（牽制事件） |
| `fromCatcher` | 2.1% | 牽制是否由捕手發動 | ✅ |
| `runnerGoing` | 1.5%（恆 True） | 跑者起跑中（盜壘） | ✅ |
| `violation` | 44 筆（**2023 起**） | `{type, description, player}`：`pitcher_pitch_timer`(29)／`batter_pitch_timer`(10)／`pitcher_disengagement`(4)／`batter_timeout`(1) | ❌ |

### 6.3 `pitchData`（分母 = 98,850 顆投球）

`strikeZoneTop`／`strikeZoneBottom` 是**唯二 100% 全年全層級都有**的欄位
（來自打者身高的估算，不需要追蹤系統）。其他物理量都受 2.1 的覆蓋限制。

| 欄位 | 出現率 | 起始年 | 說明 | extract.py |
|---|---|---|---|---|
| `strikeZoneTop`／`strikeZoneBottom` | **100%** | 2002 | 該打者的好球帶上下緣（呎） | ✅ |
| `startSpeed`／`endSpeed` | 40.3% | 2007 | 出手／過壘速度（mph，實測 37.2–101.7） | ✅ |
| `zone` | 40.3% | 2007 | 好球帶分區代碼 1–14 | ✅ |
| `typeConfidence` | 39.9% | 2007 | 球種分類信心值（0–2） | ✅ |
| `coordinates.pX`／`pZ` | 40.3% | 2007 | 過本壘板的水平／垂直座標 | ✅ |
| `coordinates.pfxX`／`pfxZ` | 40.3% | 2007 | 水平／垂直位移（含重力，英吋） | ✅ |
| `coordinates.x0`／`y0`／`z0` | 40.3% | 2007 | 出手點座標（`y0` 是量測平面，見陷阱欄位） | ✅ |
| `coordinates.vX0`／`vY0`／`vZ0`／`aX`／`aY`／`aZ` | 40.3% | 2007 | 三軸初速與加速度（可自行重算完整彈道） | ✅ |
| `coordinates.x`／`y` | 96.0% | 2005 | **轉播圖表用的螢幕座標**，不是物理量，別拿來算東西 | ❌（正確） |
| `breaks.breakAngle`／`breakLength`／`breakY` | 40.3% | 2007 | 舊版位移描述（`breakY` 恆為 24.0，死） | ✅ |
| `breaks.spinRate`／`spinDirection` | 40.1% | 2007 | 轉速（9–3630 rpm）／轉軸方向（0–359°） | ✅ |
| `breaks.breakVerticalInduced`（IVB） | 23.8% | **2017** | 誘導垂直位移（扣掉重力，−22.6 ~ +30.1） | ✅ `ivb` |
| `breaks.breakHorizontal`（HB） | 23.8% | **2017** | 水平位移（−31.8 ~ +25.0） | ✅ `hb` |
| `breaks.breakVertical` | 23.8% | **2017** | 含重力的垂直位移 | ✅ |
| `extension` | 23.8% | **2017** | 出手延伸（3.1–8.0 呎） | ✅ |
| `plateTime` | 23.8% | **2017** | 出手到過壘的時間（0.37–1.05 秒） | ✅ |
| `strikeZoneWidth`／`strikeZoneDepth` | 8.7% | **AAA 2023／MLB 2025** | ABS 用的好球帶寬（17/20 吋）與深（8.5/17 吋） | ❌ ← 可補 |
| `strikeZoneInfo` | 18.1% | **2020** | 3D 好球帶模型（見下） | ✅ |

`pitchData.strikeZoneInfo`：

| 欄位 | 出現率 | 起始年 | 說明 |
|---|---|---|---|
| `isStrike` | 18.1% | 2020 | **模型判定**這球是不是好球——跟 `details.isStrike`（裁判實判）比對就能算好球帶誤判率 |
| `strikeZoneTop`／`strikeZoneBottom` | 18.1% | 2020 | 模型版好球帶上下緣（與 `pitchData.strikeZoneTop` 是不同管線，數值略有差異） |
| `strikeZoneFlat` | 18.1% | 2020 | 是否套用平面版邊界（71% True） |
| `strikeZoneRounded`／`strikeZoneCornerRadiusInches` | 18.1% | 2020 | **恆為 False / 0.0（死）** |
| `plateX`／`plateY`／`plateZ` | 14.1% | **2022** | 模型版通過本壘板的三維座標 |
| `widthInches`／`depthInches` | 16.2% | 2021 | 好球帶寬／深，**有 4,335 筆 0.0 壞值** |
| `edgeDistance` | 9.0% | **2024** | 球心到好球帶邊緣的最短距離（負值＝在帶內），量化「差一點點的好壞球」 |
| `edgePositionBall`／`edgePositionZone` | 3.9% | **2025** | 球心／好球帶邊緣最近點的 3D 座標 `{x,y,z}` |
| `baseballDiameterInches` | 3.9% | 2025 | 恆為 2.9（常數，死） |

### 6.4 `hitData`（分母 = 26,938 個 hitData，其中 20,600 是真正擊球進場）

| 欄位 | 出現率（相對 hitData） | 起始年 | 說明 | extract.py |
|---|---|---|---|---|
| `trajectory` | 76.5% | 2002 | `ground_ball`(9,129)／`fly_ball`(5,702)／`line_drive`(3,879)／`popup`(1,453)／`bunt_grounder`／`bunt_popup`。**出現次數精準等於 `isInPlay=True` 的數量，是判斷「有沒有真的擊球」最可靠的鍵** | ✅ |
| `location` | 76.3% | 2002 | 落點守備位置代碼（`8`/`7`/`9`/`6`…） | ✅ |
| `hardness` | 76.5% | 2002 | 93% 是 `medium`，沒有鑑別度（見陷阱欄位） | ✅ |
| `coordinates.coordX`／`coordY` | 72.3% | **2005** | 球場示意圖落點座標，**2005 起全層級 ~100%，是最古老也最全面的落點資料**（畫落點圖／算噴射角靠它） | ✅ |
| `launchSpeed`（EV） | 16.7% | **2015** | 擊球初速（14.0–114.7 mph） | ✅ `ev` |
| `launchAngle`（LA） | 16.7% | **2015** | 擊球仰角（−88 ~ +89°） | ✅ `la` |
| `totalDistance` | 16.6% | **2015** | 落點總距離（1–462 呎） | ✅ `hit_distance` |
| `hitProbability` | 14.1% | **2015，只有 MLB 穩定** | 該 EV+LA 組合的聯盟平均安打機率（0–100） | ✅ |
| `batSpeed` | 8.0% | **2024** | 揮棒最大棒速（1.2–86.8 mph）。**沒揮棒的球本來就沒有，不是缺資料** | ✅ |
| `isSwordSwing` | 1.9% | **2024** | 是否為「劍擊」揮棒（樣本中 42 次 True） | ✅ |

### 6.5 `contextMetrics`（事件層級）

| 欄位 | 出現率 | 起始年 | 說明 |
|---|---|---|---|
| `homeRunBallparks` | 3.6%（MLB 約 15%） | 2015 | 這球若是全壘打，30 座球場中有幾座會出牆（0–30） |
| 其他四個 speed 相關欄位 | **0 筆** | — | 見死資料 A |

### 6.6 完整欄位總表（逐球／事件層級，196 條路徑）

涵蓋 `playEvents[]` 底下所有偵測到的欄位路徑，含結構節點。

| 路徑 | 節點 | 型別 | 覆蓋率 | 年份範圍 | 層級 | 狀態 | 已抓 (extract.py) | 備註／值域 |
|---|---|---|---|---|---|---|---|---|
| `actionPlayId` | 欄位 | str | 1.4% | 2002–2026 | 全層級 | 稀有 | 否 | 動作事件的 ID |
| `awayTeamWinProbability` | 欄位 | float | 1.3% | 2002–2026 | 全層級 | 陷阱 | 否 | 恆等於 100 − 主隊勝率，不必另存 |
| `base` | 欄位 | int | 0.1% | 2002–2026 | 全層級 | 稀有 | 否 | 跑壘事件的目標壘包 |
| `battingOrder` | 欄位 | str | 1.6% | 2002–2026 | 全層級 | 稀有 | 否 | 換人後的打序碼 |
| `contextMetrics` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `contextMetrics.averagePitchSpeedLeague` | 欄位 | float | 0.0% | 2023–2023 | A | 死欄位 | 否 | 只有 2023 年 A 級的 40 筆，等同不存在 |
| `contextMetrics.homeRunBallparks` | 欄位 | int | 3.5% | 2015–2026 | MLB、AAA、A | 受年份／層級限制 | 是 | 這球若是全壘打，30 座球場中有幾座會出牆 |
| `contextMetrics.maxPitchSpeedLeague` | 欄位 | float | 0.0% | 2023–2023 | A | 死欄位 | 否 | 只有 2023 年 A 級的 40 筆，等同不存在 |
| `count` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `count.balls` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 打席結束當下的壞球數 |
| `count.outs` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 打席結束當下的出局數 |
| `count.strikes` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 打席結束當下的好球數 |
| `credits` | 容器 | list | 0.0% | 2005–2021 | MLB、AAA、A+、A(Short) | 稀有 | 否 |  |
| `credits[]` | 容器 | dict | 100.0% | 2005–2021 | MLB、AAA、A+、A(Short) | 受年份／層級限制 | 否 |  |
| `credits[].credit` | 欄位 | str | 100.0% | 2005–2021 | MLB、AAA、A+、A(Short) | 受年份／層級限制 | 否 | b_pa／p_pa／b_ab／p_ab，資訊量低於 result.eventType |
| `credits[].player` | 容器 | dict | 100.0% | 2005–2021 | MLB、AAA、A+、A(Short) | 受年份／層級限制 | 否 |  |
| `credits[].player.id` | 欄位 | int | 100.0% | 2005–2021 | MLB、AAA、A+、A(Short) | 受年份／層級限制 | 否 | 常見值：430261(1)、425429(1)、134265(1) |
| `credits[].position` | 容器 | dict | 100.0% | 2005–2021 | MLB、AAA、A+、A(Short) | 受年份／層級限制 | 否 |  |
| `credits[].position.abbreviation` | 欄位 | str | 100.0% | 2005–2021 | MLB、AAA、A+、A(Short) | 受年份／層級限制 | 否 | 常見值：C(4)、1B(3)、RF(1) |
| `defense` | 容器 | dict | 98.6% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `defense.catcher` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `defense.catcher.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 這球的捕手 |
| `defense.center` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `defense.center.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 值域 111742 ~ 834240 |
| `defense.first` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `defense.first.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 值域 110432 ~ 832212 |
| `defense.left` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `defense.left.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 值域 110236 ~ 836173 |
| `defense.pitcher` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `defense.pitcher.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 這球實際由誰投出，逐球校正投手身分的唯一依據 |
| `defense.pitcher.pitchHand` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `defense.pitcher.pitchHand.code` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 常見值：R(77884)、L(29700) |
| `defense.right` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `defense.right.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 值域 110029 ~ 836061 |
| `defense.second` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `defense.second.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 值域 110840 ~ 829905 |
| `defense.shortstop` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `defense.shortstop.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 值域 111851 ~ 836582 |
| `defense.third` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `defense.third.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 值域 110135 ~ 836055 |
| `details` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `details.awayScore` | 欄位 | int | 7.2% | 2002–2026 | 全層級 | 全年可用 | 否 | 動作事件當下的客隊比分 |
| `details.ballColor` | 欄位 | str | 85.9% | 2002–2026 | 全層級 | 死欄位 | 否 | 轉播動畫顏色，無分析價值 |
| `details.call` | 容器 | dict | 90.7% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `details.call.code` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 裁判判決，與 details.code 同義 |
| `details.code` | 欄位 | str | 92.8% | 2002–2026 | 全層級 | 全年可用 | 是 | 結果代碼：B 壞球／C 看見好球／F 界外／X 擊出出局／S 揮空／D 擊出安打 |
| `details.description` | 欄位 | str | 99.9% | 2002–2026 | 全層級 | 全年可用 | 是 | 這球的播報文字 |
| `details.disengagementNum` | 欄位 | int | 4.4% | 2002–2026 | 全層級 | 全年可用 | 是 | 該打席第幾次脫離投手板（2023 年牽制限制規則） |
| `details.event` | 欄位 | str | 7.2% | 2002–2026 | 全層級 | 全年可用 | 否 | 非投球動作的人類可讀名稱 |
| `details.eventType` | 欄位 | str | 7.2% | 2002–2026 | 全層級 | 全年可用 | 否 | 非投球動作的分類：pitching_substitution／game_advisory／offensive_substitution／stolen_base_2b／wild_pitch… |
| `details.fromCatcher` | 欄位 | bool | 2.1% | 2002–2026 | 全層級 | 全年可用 | 是 | 牽制是否由捕手發動 |
| `details.hasReview` | 欄位 | bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 這個事件是否被申請重播 |
| `details.homeScore` | 欄位 | int | 7.2% | 2002–2026 | 全層級 | 全年可用 | 否 | 動作事件當下的主隊比分 |
| `details.isBall` | 欄位 | bool | 90.7% | 2002–2026 | 全層級 | 全年可用 | 是 | 裁判實際判定的壞球 |
| `details.isInPlay` | 欄位 | bool | 90.7% | 2002–2026 | 全層級 | 全年可用 | 是 | 是否擊入場內（20,600 次） |
| `details.isOut` | 欄位 | bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 這個事件是否造成出局 |
| `details.isScoringPlay` | 欄位 | bool | 7.2% | 2002–2026 | 全層級 | 全年可用 | 否 | 常見值：False(7668)、True(145) |
| `details.isStrike` | 欄位 | bool | 90.7% | 2002–2026 | 全層級 | 全年可用 | 是 | 裁判實際判定的好球 |
| `details.runnerGoing` | 欄位 | bool | 1.5% | 2003–2026 | 全層級 | 陷阱 | 是 | 跑者起跑中（盜壘），恆為 True |
| `details.trailColor` | 欄位 | str | 51.1% | 2007–2026 | 全層級 | 死欄位 | 否 | 轉播動畫軌跡顏色，無分析價值 |
| `details.type` | 容器 | dict | 51.1% | 2007–2026 | 全層級 | 受年份／層級限制 | 否 |  |
| `details.type.code` | 欄位 | str | 71.4% | 2007–2026 | MLB、AAA、A、ROK | 陷阱 | 是 | 球種代碼 FF／SI／SL／CH／CU／FC…；type 存在時仍有 28% 缺 code（描述會是 Unknown） |
| `details.type.description` | 欄位 | str | 100.0% | 2007–2026 | 全層級 | 受年份／層級限制 | 是 | 球種名稱，未知時為 Unknown（15,050 次） |
| `details.violation` | 容器 | dict | 0.0% | 2023–2026 | MLB、AAA、AA、A+、A、ROK | 稀有 | 否 |  |
| `details.violation.description` | 欄位 | str | 100.0% | 2023–2026 | MLB、AAA、AA、A+、A、ROK | 受年份／層級限制 | 否 | 常見值：Pitcher Pitch Timer Violation(29)、Batter Pitch Timer Violation(10)、Pitcher Disengagement Violation(4) |
| `details.violation.player` | 容器 | dict | 100.0% | 2023–2026 | MLB、AAA、AA、A+、A、ROK | 受年份／層級限制 | 否 |  |
| `details.violation.player.id` | 欄位 | int | 100.0% | 2023–2026 | MLB、AAA、AA、A+、A、ROK | 受年份／層級限制 | 否 | 值域 543548 ~ 831951 |
| `details.violation.type` | 欄位 | str | 100.0% | 2023–2026 | MLB、AAA、AA、A+、A、ROK | 受年份／層級限制 | 否 | 投球計時器違規：pitcher_pitch_timer(29)／batter_pitch_timer(10)／pitcher_disengagement(4)／batter_timeout(1) |
| `dramaIndex` | 欄位 | float | 1.3% | 2002–2026 | 全層級 | 陷阱 | 是 | MLB 的精彩度指標，實測範圍 5 ~ 687，不是 0–100 |
| `endTime` | 欄位 | str | 75.6% | 2010–2026 | 全層級 | 受年份／層級限制 | 否 | 事件結束時間戳，2010 年起 |
| `hitData` | 容器 | dict | 24.7% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `hitData.batSpeed` | 欄位 | float | 8.0% | 2024–2026 | MLB、ROK | 受年份／層級限制 | 是 | 揮棒最大棒速（1.2–86.8 mph），2024 年起；沒揮棒的球本來就沒有 |
| `hitData.coordinates` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `hitData.coordinates.coordX` | 欄位 | float | 72.3% | 2005–2026 | 全層級 | 受年份／層級限制 | 是 | 球場示意圖落點 X；2005 年起全層級都有，是最全面的落點資料 |
| `hitData.coordinates.coordY` | 欄位 | float | 72.4% | 2005–2026 | 全層級 | 受年份／層級限制 | 是 | 球場示意圖落點 Y |
| `hitData.hardness` | 欄位 | str | 76.5% | 2002–2026 | 全層級 | 陷阱 | 是 | 93% 是 medium，沒有鑑別度，要判斷強擊球請用 launchSpeed |
| `hitData.hitProbability` | 欄位 | float | 14.1% | 2015–2026 | MLB、AAA、A | 受年份／層級限制 | 是 | 該 EV+LA 組合的聯盟平均安打機率 0–100，只有 MLB 穩定 |
| `hitData.isSwordSwing` | 欄位 | bool | 1.9% | 2024–2026 | MLB、ROK | 稀有 | 是 | 是否為「劍擊」揮棒（樣本 42 次 True），2024 年起 |
| `hitData.launchAngle` | 欄位 | float | 16.7% | 2015–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 擊球仰角 LA（−88 ~ +89 度），2015 年起 |
| `hitData.launchSpeed` | 欄位 | float | 16.7% | 2015–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 擊球初速 EV（14.0–114.7 mph），2015 年起 |
| `hitData.location` | 欄位 | str | 76.3% | 2002–2026 | 全層級 | 全年可用 | 是 | 落點守備位置代碼 |
| `hitData.totalDistance` | 欄位 | float | 16.6% | 2015–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 落點總距離（1–462 呎），2015 年起 |
| `hitData.trajectory` | 欄位 | str | 76.5% | 2002–2026 | 全層級 | 全年可用 | 是 | ground_ball 9,129／fly_ball 5,702／line_drive 3,879／popup 1,453；出現次數精準等於擊入場內的球數，判斷「有沒有真的擊球」用這個 |
| `homeTeamWinProbability` | 欄位 | float | 1.3% | 2002–2026 | 全層級 | 陷阱 | 是 | 打席結束當下主隊勝率（%），2002 年起連小聯盟都有 |
| `homeTeamWinProbabilityAdded` | 欄位 | float | 1.3% | 2002–2026 | 全層級 | 陷阱 | 是 | WPA：這個打席讓主隊勝率增減幾個百分點（實測 −64.4 ~ +75.8） |
| `index` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 事件在 playEvents 中的序號 |
| `injuryType` | 欄位 | str | 0.0% | 2009–2024 | MLB、A+、ROK | 稀有 | 否 | 當場受傷部位（22 筆：shoulder／hand／head／ankle…） |
| `isBaseRunningPlay` | 欄位 | bool | 1.3% | 2002–2026 | 全層級 | 陷阱 | 否 | 跑壘事件旗標，恆為 True（key 不存在就是 False） |
| `isPitch` | 欄位 | bool | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 是否為真正的一次投球，等同 type=='pitch' |
| `isSubstitution` | 欄位 | bool | 3.3% | 2002–2026 | 全層級 | 陷阱 | 否 | 換人事件旗標，恆為 True |
| `leverageIndex` | 欄位 | float | 1.3% | 2002–2026 | 全層級 | 陷阱 | 是 | 局勢緊張度 LI，1.0 為平均（實測 0 ~ 9.25） |
| `offense` | 容器 | dict | 98.6% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `offense.batter` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `offense.batter.batSide` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `offense.batter.batSide.code` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 常見值：R(63821)、L(43763) |
| `offense.batter.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 這球當下的打者 |
| `offense.batterPosition` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `offense.batterPosition.abbreviation` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 打者的守備位置（代打／代跑辨識） |
| `offense.first` | 容器 | dict | 32.5% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `offense.first.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 投球前一壘跑者 |
| `offense.postOnFirst` | 容器 | dict | 0.0% | 2002–2026 | 全層級 | 稀有 | 否 |  |
| `offense.postOnFirst.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 投球後推進到一壘的跑者（僅 34 筆） |
| `offense.postOnSecond` | 容器 | dict | 0.9% | 2002–2026 | 全層級 | 稀有 | 否 |  |
| `offense.postOnSecond.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 投球後推進到二壘的跑者 |
| `offense.postOnThird` | 容器 | dict | 0.5% | 2002–2026 | 全層級 | 稀有 | 否 |  |
| `offense.postOnThird.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 投球後推進到三壘的跑者 |
| `offense.second` | 容器 | dict | 20.9% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `offense.second.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 投球前二壘跑者 |
| `offense.third` | 容器 | dict | 11.1% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `offense.third.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 投球前三壘跑者 |
| `officials` | 容器 | list | 98.6% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `officials[]` | 容器 | dict | 313.4% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `officials[].official` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `officials[].officialType` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 崗位：Home Plate／First Base／Third Base／Second Base（小聯盟常只有 2–3 位） |
| `pfxId` | 欄位 | str | 14.9% | 2007–2016 | MLB | 受年份／層級限制 | 否 | PITCHf/x 時代的舊 ID，只有 2007–2016 的 MLB |
| `pitchData` | 容器 | dict | 90.6% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `pitchData.breaks` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `pitchData.breaks.breakAngle` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 舊版位移角度 |
| `pitchData.breaks.breakHorizontal` | 欄位 | float | 23.8% | 2017–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | HB 水平位移（−31.8 ~ +25.0），2017 年起 |
| `pitchData.breaks.breakLength` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 舊版最大位移量 |
| `pitchData.breaks.breakVertical` | 欄位 | float | 23.8% | 2017–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 含重力的垂直位移，2017 年起 |
| `pitchData.breaks.breakVerticalInduced` | 欄位 | float | 23.8% | 2017–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | IVB 誘導垂直位移，扣掉重力（−22.6 ~ +30.1），2017 年起 |
| `pitchData.breaks.breakY` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 死欄位 | 是 | 只有 24.0／19.2 兩個值，沒有資訊量 |
| `pitchData.breaks.spinDirection` | 欄位 | int | 40.2% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 轉軸方向（0–359 度） |
| `pitchData.breaks.spinRate` | 欄位 | int | 40.1% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 轉速（9–3630 rpm） |
| `pitchData.coordinates` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `pitchData.coordinates.aX` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | x 軸加速度 |
| `pitchData.coordinates.aY` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | y 軸加速度 |
| `pitchData.coordinates.aZ` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | z 軸加速度 |
| `pitchData.coordinates.pX` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 過本壘板的水平座標 |
| `pitchData.coordinates.pZ` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 過本壘板的垂直座標 |
| `pitchData.coordinates.pfxX` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 水平位移（含重力，英吋） |
| `pitchData.coordinates.pfxZ` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 垂直位移（含重力，英吋） |
| `pitchData.coordinates.vX0` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 出手點 x 軸速度分量 |
| `pitchData.coordinates.vY0` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 出手點 y 軸速度分量 |
| `pitchData.coordinates.vZ0` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 出手點 z 軸速度分量 |
| `pitchData.coordinates.x` | 欄位 | float | 96.0% | 2005–2026 | 全層級 | 死欄位 | 否 | 轉播圖表用的螢幕座標，不是物理量 |
| `pitchData.coordinates.x0` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 出手點水平座標 |
| `pitchData.coordinates.y` | 欄位 | float | 96.0% | 2005–2026 | 全層級 | 死欄位 | 否 | 轉播圖表用的螢幕座標，不是物理量 |
| `pitchData.coordinates.y0` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 陷阱 | 是 | 不是座標軸，是 x0/z0 的量測平面距本壘板幾呎（2008 起恆為 50） |
| `pitchData.coordinates.z0` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 出手點高度 |
| `pitchData.endSpeed` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 過本壘板球速 |
| `pitchData.extension` | 欄位 | float | 23.8% | 2017–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 出手延伸距離（3.1–8.0 呎），2017 年起 |
| `pitchData.plateTime` | 欄位 | float | 23.8% | 2017–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 出手到過壘所需時間（0.37–1.05 秒），2017 年起 |
| `pitchData.startSpeed` | 欄位 | float | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 出手球速（mph，實測 37.2–101.7） |
| `pitchData.strikeZoneBottom` | 欄位 | float | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 該打者好球帶下緣（呎）；2002 年起 100% 都有 |
| `pitchData.strikeZoneDepth` | 欄位 | float | 8.7% | 2021–2026 | MLB、AAA、A | 受年份／層級限制 | 否 | ABS 用的好球帶深（8.5／17 吋） |
| `pitchData.strikeZoneInfo` | 容器 | dict | 18.1% | 2020–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 否 |  |
| `pitchData.strikeZoneInfo.baseballDiameterInches` | 欄位 | float | 21.8% | 2025–2026 | MLB、AAA、ROK | 死欄位 | 否 | 恆為 2.9，是棒球直徑常數 |
| `pitchData.strikeZoneInfo.depthInches` | 欄位 | float | 89.6% | 2021–2026 | MLB、AAA、A、ROK | 陷阱 | 是 | 好球帶深，同樣有 0.0 壞值 |
| `pitchData.strikeZoneInfo.edgeDistance` | 欄位 | float | 49.6% | 2024–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 球心到好球帶邊緣的最短距離，量化「差一點點」，2024 年起 |
| `pitchData.strikeZoneInfo.edgePositionBall` | 容器 | dict | 21.8% | 2025–2026 | MLB、AAA、ROK | 受年份／層級限制 | 否 |  |
| `pitchData.strikeZoneInfo.edgePositionBall.x` | 欄位 | float | 100.0% | 2025–2026 | MLB、AAA、ROK | 受年份／層級限制 | 否 | 球心最近點的 3D 座標，2025 年起 |
| `pitchData.strikeZoneInfo.edgePositionBall.y` | 欄位 | float | 100.0% | 2025–2026 | MLB、AAA、ROK | 受年份／層級限制 | 否 | 常見值：0.7083333333333334(2520)、1.4166666666666667(690)、0.7083333333333337(340) |
| `pitchData.strikeZoneInfo.edgePositionBall.z` | 欄位 | float | 100.0% | 2025–2026 | MLB、AAA、ROK | 受年份／層級限制 | 否 | 值域 -2.3156969954513342 ~ 6.013519630595507 |
| `pitchData.strikeZoneInfo.edgePositionZone` | 容器 | dict | 21.8% | 2025–2026 | MLB、AAA、ROK | 受年份／層級限制 | 否 |  |
| `pitchData.strikeZoneInfo.edgePositionZone.x` | 欄位 | float | 100.0% | 2025–2026 | MLB、AAA、ROK | 受年份／層級限制 | 否 | 值域 -0.7083333333333334 ~ 0.7083333333333334 |
| `pitchData.strikeZoneInfo.edgePositionZone.y` | 欄位 | float | 100.0% | 2025–2026 | MLB、AAA、ROK | 受年份／層級限制 | 否 | 常見值：0.7083333333333334(2520)、1.4166666666666667(690)、0.7083333333333337(340) |
| `pitchData.strikeZoneInfo.edgePositionZone.z` | 欄位 | float | 100.0% | 2025–2026 | MLB、AAA、ROK | 受年份／層級限制 | 否 | 值域 1.44 ~ 3.95 |
| `pitchData.strikeZoneInfo.isStrike` | 欄位 | bool | 100.0% | 2020–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 模型判定的好球；跟 details.isStrike（裁判實判）比對可算好球帶誤判率 |
| `pitchData.strikeZoneInfo.plateX` | 欄位 | float | 78.1% | 2022–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 模型版通過本壘板的 x 座標，2022 年起 |
| `pitchData.strikeZoneInfo.plateY` | 欄位 | float | 78.1% | 2022–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 模型版通過本壘板的 y 座標 |
| `pitchData.strikeZoneInfo.plateZ` | 欄位 | float | 78.1% | 2022–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 模型版通過本壘板的 z 座標 |
| `pitchData.strikeZoneInfo.strikeZoneBottom` | 欄位 | float | 100.0% | 2020–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 模型版好球帶下緣 |
| `pitchData.strikeZoneInfo.strikeZoneCornerRadiusInches` | 欄位 | float | 100.0% | 2020–2026 | MLB、AAA、A、ROK | 死欄位 | 是 | 恆為 0.0 |
| `pitchData.strikeZoneInfo.strikeZoneFlat` | 欄位 | bool | 100.0% | 2020–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 是否套用平面版邊界（71% True） |
| `pitchData.strikeZoneInfo.strikeZoneRounded` | 欄位 | bool | 100.0% | 2020–2026 | MLB、AAA、A、ROK | 死欄位 | 是 | 恆為 False，圓角好球帶從未啟用 |
| `pitchData.strikeZoneInfo.strikeZoneTop` | 欄位 | float | 100.0% | 2020–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 模型版好球帶上緣（與 pitchData.strikeZoneTop 不同管線） |
| `pitchData.strikeZoneInfo.widthInches` | 欄位 | float | 89.6% | 2021–2026 | MLB、AAA、A、ROK | 陷阱 | 是 | 好球帶寬，有 4,335 筆是 0.0 壞值 |
| `pitchData.strikeZoneTop` | 欄位 | float | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 該打者好球帶上緣（呎）；2002 年起 100% 都有，不需追蹤系統 |
| `pitchData.strikeZoneWidth` | 欄位 | float | 8.7% | 2021–2026 | MLB、AAA、A | 受年份／層級限制 | 否 | ABS 用的好球帶寬（17／20 吋），AAA 2023 起、MLB 2025 起 |
| `pitchData.typeConfidence` | 欄位 | float | 39.9% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 球種分類信心值 0–2 |
| `pitchData.zone` | 欄位 | int | 40.3% | 2007–2026 | MLB、AAA、A、ROK | 受年份／層級限制 | 是 | 好球帶分區代碼 1–14 |
| `pitchNumber` | 欄位 | int | 90.7% | 2002–2026 | 全層級 | 陷阱 | 是 | 該「打席內」第幾球，不是投手單場累計球數 |
| `playId` | 欄位 | str | 92.7% | 2002–2026 | 全層級 | 全年可用 | 是 | 該球的全域唯一 ID，2005 年起，可對應外部資料 |
| `player` | 容器 | dict | 6.8% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `player.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 非投球事件的當事球員 |
| `position` | 容器 | dict | 3.3% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `position.abbreviation` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 換上場後的守位（P 2,135／PH 439／PR 92…） |
| `preCount` | 容器 | dict | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 |  |
| `preCount.balls` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 這球投出前的壞球數，2002 年起 100% 都有 |
| `preCount.outs` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 這球投出前的出局數，2002 年起 100% 都有 |
| `preCount.strikes` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | 這球投出前的好球數，2002 年起 100% 都有 |
| `replacedPlayer` | 容器 | dict | 1.4% | 2002–2026 | 全層級 | 稀有 | 否 |  |
| `replacedPlayer.id` | 欄位 | int | 100.0% | 2002–2026 | 全層級 | 全年可用 | 否 | 被換下場的球員，判斷代打／中途換人的關鍵 |
| `reviewDetails` | 容器 | dict | 0.1% | 2017–2026 | MLB、AAA、A | 稀有 | 否 |  |
| `reviewDetails.challengeTeamId` | 欄位 | int | 97.7% | 2017–2026 | MLB、AAA、A | 受年份／層級限制 | 否 | 值域 105 ~ 1960 |
| `reviewDetails.inProgress` | 欄位 | bool | 100.0% | 2017–2026 | MLB、AAA、A | 受年份／層級限制 | 否 | 常見值：False(88) |
| `reviewDetails.isOverturned` | 欄位 | bool | 100.0% | 2017–2026 | MLB、AAA、A | 受年份／層級限制 | 否 | 重播後是否改判（樣本 54 次挑戰中 22 次改判） |
| `reviewDetails.player` | 容器 | dict | 31.8% | 2026–2026 | MLB、AAA | 受年份／層級限制 | 否 |  |
| `reviewDetails.player.id` | 欄位 | int | 100.0% | 2026–2026 | MLB、AAA | 受年份／層級限制 | 否 | 2026 新增，ABS 挑戰的發起球員 |
| `reviewDetails.reviewType` | 欄位 | str | 100.0% | 2017–2026 | MLB、AAA、A | 受年份／層級限制 | 否 | 重播類型代碼 MJ／MF／MA／NH… |
| `startTime` | 欄位 | str | 75.6% | 2010–2026 | 全層級 | 受年份／層級限制 | 否 | 事件開始時間戳，2010 年起 |
| `type` | 欄位 | str | 100.0% | 2002–2026 | 全層級 | 全年可用 | 是 | pitch 98,850／action 7,813／pickoff 2,135／no_pitch 236／stepoff 117 |
| `umpire` | 容器 | dict | 0.0% | 2006–2025 | MLB、AAA、AA、A+、A | 稀有 | 否 |  |
| `umpire.id` | 欄位 | int | 100.0% | 2006–2025 | MLB、AAA、AA、A+、A | 受年份／層級限制 | 否 | 裁判換人等特殊事件（21 筆） |

---

## 七、boxscore／gameData／metaData

這兩塊跟逐球資料無關，但常被忽略——**很多不用自己從逐球資料重算的東西就在這裡**。

### 7.1 `liveData.boxscore`

`teams.{home,away}` 底下：

| 欄位 | 說明 |
|---|---|
| `players.{id}` | ★ 每位出賽球員一筆（平均 24.1 位/隊） |
| `players.{id}.stats.{batting,pitching,fielding}` | **該場**的完整數據 |
| `players.{id}.seasonStats.{batting,pitching,fielding}` | ★ **該球員到這場為止的球季累計**——不用另外打 API 就能重建球季進程 |
| `players.{id}.gameStatus` | `isCurrentBatter`／`isCurrentPitcher`／`isOnBench`／`isSubstitute` |
| `players.{id}.position`／`allPositions[]` | 主守位置／本場守過的所有位置 |
| `players.{id}.battingOrder` | 打序碼（`'100'`=第一棒先發、`'901'`=第九棒的第一位替補） |
| `players.{id}.status` | `Active`／`Rehab Assignment`（復健賽出賽可從這裡認出來） |
| `players.{id}.parentTeamId`／`jerseyNumber` | 母隊 ID／背號 |
| `batters[]`／`pitchers[]`／`bench[]`／`bullpen[]`／`battingOrder[]` | 各類球員 ID 清單 |
| `teamStats.{batting,pitching,fielding}` | 該隊全隊單場數據 |
| `info[]`／`note[]` | 官方 box score 附註（`BATTING`／`FIELDING`／`BASERUNNING` 分段的文字說明、代打註記） |

`stats.batting` 有 32 個欄位：`atBats`／`hits`／`doubles`／`triples`／`homeRuns`／`rbi`／
`runs`／`baseOnBalls`／`intentionalWalks`／`strikeOuts`／`hitByPitch`／`sacBunts`／`sacFlies`／
`stolenBases`／`caughtStealing`／`groundIntoDoublePlay`／`leftOnBase`／`totalBases`／
`plateAppearances`／`groundOuts`／`flyOuts`／`lineOuts`／`popOuts`／`airOuts`／`pickoffs`／
`catchersInterference`／`summary`… **`groundOuts`/`flyOuts`/`lineOuts`/`popOuts` 這組
出局型態的細分是 season stats 端點沒有的**。

`stats.pitching` 有 50 個欄位，除了常規項目外值得注意的：`battersFaced`、`numberOfPitches`／
`pitchesThrown`、`strikes`／`balls`／`strikePercentage`、`inheritedRunners`／
`inheritedRunnersScored`（繼承跑者，算後援投手真實表現用）、`holds`／`blownSaves`、
`outs`（可直接算局數，不用解析 `inningsPitched` 的 `'1.1'` 格式）。

`stats.fielding`：`assists`／`putOuts`／`errors`／`chances`／`passedBall`／`pickoffs`／
`stolenBases`／`caughtStealing`（**`fielding` 與 `caughtStealingPercentage` 是死欄位**）。

其他：

| 欄位 | 說明 |
|---|---|
| `boxscore.topPerformers[]` | 本場最佳（平均 3 位）：`type`（`hitter`／`starter`／`reliever`／`twoWayReliever`）、`gameScore`、`hittingGameScore`、`pitchingGameScore`（Bill James Game Score，49–96） |
| `boxscore.officials[]` | 該場裁判名單 |
| `boxscore.info[]` | 全場資訊：`Weather`／`Wind`／`Umpires`／`Batters faced`／`Groundouts-flyouts`／`First pitch`… |
| `boxscore.pitchingNotes[]` | 「X 在第 N 局面對 M 位打者」之類的註記 |

### 7.2 `gameData`

| 欄位 | 出現率 | 說明 |
|---|---|---|
| `players.{id}` | 100%（平均 48.4 位/場） | ★ 每位球員的完整檔案：`birthCountry`（**找台灣出身球員就靠這個**）／`birthCity`／`birthDate`／`currentAge`／`height`／`weight`／`batSide`／`pitchHand`／`primaryPosition`／`mlbDebutDate`／`draftYear`／`nickName`／`pronunciation`／`strikeZoneTop`／`strikeZoneBottom`（該球員的標準好球帶） |
| `venue` | 100% | `name`／`location`／`timeZone`／`fieldInfo`（`capacity`／`turfType`／`roofType`／各方向全壘打牆距離 `leftLine`/`leftCenter`/`center`/`rightCenter`/`rightLine`）——**算球場因子的原始素材** |
| `weather` | 100% | `condition`／`temp`（℉，字串）／`wind`（如 `'12 mph, R To L'`；1.4% 缺） |
| `gameInfo` | 100% | `attendance`／`gameDurationMinutes`／`firstPitch`／`delayDurationMinutes`(7%) |
| `datetime` | 100% | `officialDate`／`originalDate`／`dayNight`／`time`／`ampm`；`resumeDate` 系列（0.5%，保留比賽） |
| `teams.{home,away}` | 100% | 球隊檔案＋`record`（勝敗、勝率）＋`league`／`division`／`sport`／`parentOrgId`（**小聯盟球隊的母隊**）／`springLeague`／`springVenue` |
| `status` | 100% | `detailedState`（`Final`／`Completed Early: Rain`…）／`statusCode`／`reason` |
| `ruleSettings[]` | 100%（平均 5.7 條/場） | ★ **`withMetrics` 才有**。該場生效的規則：`baseSize`／`defensiveShiftBanned`／`moundVisitRule`／`secondBaseDistanceFromHome`／`extraInningsRunnerOnSecond`／`designatedHitter`… 每條含 `settingValue` 與 `valueType`。要跨年比較時，這是判斷「這場適用什麼規則」最直接的來源 |
| `flags` | 100% | `noHitter`／`perfectGame`／各隊版本 |
| `review` | 100% | 雙方剩餘／已用的挑戰次數 |
| `moundVisits` | 27.9%（**2018 起**） | 雙方投手丘訪問 `used`／`remaining` |
| `absChallenges` | 5.1%（**2023 起**） | ABS 挑戰 `remaining`／`usedSuccessful`／`usedFailed` |
| `probablePitchers` | 80% | 雙方預告先發 |
| `officialScorer`／`primaryDatacaster` | 96.5%（2005 起） | 官方記錄員／資料記錄員 |

### 7.3 `metaData`

| 欄位 | 說明 |
|---|---|
| `timeStamp` | 這份 JSON 的產生時間（`YYYYMMDD_HHMMSS`） |
| `gameEvents[]`／`logicalEvents[]` | 最後一次更新觸發的事件標記（即時比賽用，回溯分析沒價值） |
| `wait` | 恆為 10（死） |

---

## 八、`extract.py` 現況對照與補抓建議

### 8.1 `pitches_json` 每球一筆的欄位來源

| 欄位 | 來源路徑 |
|---|---|
| `game_pk` | `gamePk` |
| `inning` | `play.about.inning` |
| `pitch_type`／`pitch_name` | `event.details.type.code`／`.description` |
| `result_code`／`result_desc` | `event.details.code`／`.description` |
| `is_strike`／`is_ball`／`is_in_play` | `event.details.isStrike`／`.isBall`／`.isInPlay` |
| `zone`／`start_speed`／`end_speed`／`extension`／`plate_time`／`type_confidence` | `event.pitchData.*` |
| `strike_zone_top`／`strike_zone_bottom` | `event.pitchData.strikeZoneTop`／`.strikeZoneBottom` |
| `pfx_x`／`pfx_z`／`px`／`pz`／`x0`／`y0`／`z0`／`vx0`／`vy0`／`vz0`／`ax`／`ay`／`az` | `event.pitchData.coordinates.*` |
| `ivb`／`hb`／`spin_rate`／`spin_dir`／`break_angle`／`break_length`／`break_y`／`break_vertical` | `event.pitchData.breaks.*` |
| `ev`／`la`／`hit_distance`／`trajectory`／`hit_location`／`hardness`／`hit_probability`／`bat_speed`／`is_sword_swing` | `event.hitData.*` |
| `hit_coord_x`／`hit_coord_y` | `event.hitData.coordinates.coordX`／`coordY` |
| `balls`／`strikes`／`outs` | `event.count.*`（投球**後**） |
| `pre_balls`／`pre_strikes`／`pre_outs` | `event.preCount.*`（投球**前**；實測 100% 都有，fallback 用不到） |
| `batter_id` | `play.matchup.batter.id` |
| `pitcher_id` | `event.defense.pitcher.id`（缺值退回 `play.matchup.pitcher.id`） |
| `bat_side`／`pitch_hand` | `play.matchup.batSide.code`／`.pitchHand.code` |
| `is_pa_final` | 程式自算（該打席最後一顆 `isPitch`），**非 API 欄位** |
| `pa_event`／`pa_event_desc` | `play.result.eventType`／`.event`（僅最後一球） |
| `runners` | `play.runners[]`（僅最後一球，見 `_extract_runners()`） |
| `play_id`／`pitch_number` | `event.playId`／`.pitchNumber` |
| `sz_plate_x/y/z`／`sz_top`／`sz_bottom`／`sz_flat`／`sz_rounded`／`sz_corner_radius`／`sz_width_in`／`sz_depth_in`／`sz_edge_distance`／`sz_is_strike` | `event.pitchData.strikeZoneInfo.*` |
| `hr_ballparks` | `event.contextMetrics.homeRunBallparks` |
| `defense`／`offense` | `event.defense`／`.offense`（經 `_condense_defense()`／`_condense_offense()` 濃縮） |
| `pa_final_balls/strikes/outs`／`home_wp`／`wpa`／`leverage_index`／`drama_index`／`pa_xwoba` | `play.count.*`／`play.homeTeamWinProbability` 等（經 `_pa_context()`，僅最後一球） |

`events_json`（目前只收 `pickoff`／`stepoff` 兩種事件）：
`type`／`index`／`play_id`／`inning`／`pre_*`／`balls`/`strikes`/`outs`／`result_code`／
`result_desc`／`disengagement_num`／`from_catcher`／`runner_going`／`is_out`／
`pitcher_id`／`batter_id`。

### 8.2 已經在抓、但實測沒有資訊量的欄位

| 欄位 | 狀況 |
|---|---|
| `sz_rounded` | 恆為 `False`（17,878/17,878） |
| `sz_corner_radius` | 恆為 `0.0` |
| `break_y` | 只有 24.0／19.2 兩個值 |
| `hardness` | 93% 是 `medium` |

留著不會錯（未來 MLB 可能啟用圓角好球帶），但別在這幾個欄位上建分析。

### 8.3 值得補抓的欄位（按價值排序）

| 優先 | 欄位 | 理由 |
|---|---|---|
| 高 | `playEvents[].officials[]`（至少主審 `Home Plate` 的 id） | 有了主審 ID＋已在抓的 `sz_is_strike`（模型判定）＋`details.isStrike`（實判），就能算**主審好球帶偏差**，這是自算指標、完全符合資料政策 |
| 高 | 跑壘事件的 `homeTeamWinProbabilityAdded`／`leverageIndex`／`dramaIndex` | 盜壘、牽制、暴投的 WPA 只能從這裡取得（1.3% 的事件），目前完全沒收 |
| 高 | `runners[].details.playIndex` | 能把每次跑壘精準對到 `playEvents[]` 的某一顆球，目前 `runners` 只整包掛在最後一球上 |
| 中 | `action` 事件的 `details.eventType` | 目前 `action` 事件整批略過，`wild_pitch`／`passed_ball`／`stolen_base_2b`／`pickoff_error` 等要靠 `runners[].movementReason` 間接還原 |
| 中 | `allPlays[].flags[]` | `b_sac_fly`／`b_sac_bunt`／`t_double_play`／`b_gnd_into_dp` 直接標好，比從 `eventType` 反推乾淨 |
| 中 | `pitchData.strikeZoneWidth`／`strikeZoneDepth` | ABS 時代（AAA 2023／MLB 2025 起）的好球帶尺寸，跟 `sz_width_in` 的 0.0 壞值可以互補 |
| 中 | `allPlays[].atBatIndex` | 目前打席順序靠陣列位置，存下來對 debug 與外部比對都方便 |
| 低 | `offense.postOnFirst` | `_condense_offense()` 少抓的一個（只有 34 筆，但為了一致性） |
| 低 | `details.violation` | 投球計時器違規（2023 起，44 筆） |
| 低 | `about.captivatingIndex` | 舊版精彩度，已有 `drama_index` |

### 8.4 明確不建議抓

`details.ballColor`／`trailColor`（轉播動畫顏色）、`pitchData.coordinates.x`／`y`
（螢幕座標）、`credits[]`（`b_pa`/`p_pa` 資訊量低於 `result.eventType`）、
`metaData.gameEvents`／`logicalEvents`（即時推播用）、以及第四節列出的所有死欄位。

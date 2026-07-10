# MLB Stats API: High/Low 與 Home Run Derby 端點探索

調查時間：2026-07-10 Asia/Taipei。  
依據來源：

- 本機 OpenAPI spec：[MLB-StatsAPI-Spec.json](MLB-StatsAPI-Spec.json)
- 實測只讀請求：`https://statsapi.mlb.com/api/v1/highLow/types`
- 實測只讀請求：`/api/v1/highLow/player?season=2026&sportId=1&statGroup=hitting&sortStat=homeRuns&limit=5`
- 實測只讀請求：`/api/v1/highLow/player?season=2026&sportId=1&statGroup=pitching&sortStat=strikeOuts&limit=5`
- 實測只讀請求：`/api/v1/highLow/team?season=2026&sportId=1&statGroup=hitting&sortStat=homeRuns&limit=5`
- 實測只讀請求：`/api/v1/highLow/game?season=2026&sportId=1&sortStat=runs&limit=5`
- 實測只讀請求：`/api/v1/homeRunDerby/{gamePk}/*`，以 2024/2025 All-Star Game `gamePk` 驗證皆 404。

## 結論摘要

`highLow` 對本專案有中等價值：它不是查單一球員生涯或單場 box score，而是查「某季某項數據的單場最高/最低排行榜」。最有用的地方是做球員頁的「本季 MLB 單場最佳在聯盟排名」或首頁的「台灣球員單場表現是否進入聯盟 leaderboard」。

`homeRunDerby` 對本專案目前價值很低：它只服務全壘打大賽，不服務一般 MLB/MiLB 比賽，也不服務投手。現有 DB 的 `game_logs.game_id` 是一般比賽 `gamePk`，可拿來打 `/game/{gamePk}`、`/feed/live`、`/content`，但不能期待可直接打 Home Run Derby。以 2025 All-Star Game `gamePk=778566` 和 2024 All-Star Game `gamePk=747298` 測試 Derby endpoint 均回 404。

## `GET /api/v1/highLow/types`

用途：列出可用的 high/low 統計類型，以及每個統計可用於 player/team/game 哪種 leaderboard。

回傳型態：array of `BaseballStatsTypeRestObject`。

| 欄位 | 型態 | 意義 | 專案價值 |
|---|---:|---|---|
| `name` | string | API 內部統計名稱，通常是 snake_case，例如 `home_runs`、`strikeouts`。 | 可做文件或 debug 顯示。 |
| `lookupParam` | string | 查詢 `sortStat` 時實際使用的參數值，例如 `homeRuns`、`strikeouts`。 | 高，呼叫 `/highLow/{type}` 時應使用此值。 |
| `isCounting` | boolean | 是否為累計型數據。 | 中，可判斷排序值是否為 counting stat。 |
| `label` | string | 英文顯示名稱，例如 `Home runs`。 | 中，可直接做 UI label。 |
| `statGroups[]` | array | 可用 stat group；元素常見欄位為 `displayName`，例如 `hitting`、`pitching`。 | 高，用來分打者/投手。 |
| `orgTypes[]` | array | 可用組織類型，例如 `PLAYER`、`TEAM`。 | 高，用來過濾是否能打 `/player` 或 `/team`。 |
| `highLowTypes[]` | array | 可用 highLow type，例如 `PLAYER`、`TEAM`、`GAME`。 | 高，用來驗證 path 的 `player/team/game`。 |
| `streakLevels[]` | array | streak 類型使用的層級；多數一般統計為空陣列。 | 低，除非要做連續場次紀錄。 |

實測第一筆範例：`at_bats`，`lookupParam=atBats`，可用於 `PLAYER`、`TEAM`、`GAME`，stat group 包含 `hitting` 與 `pitching`。

## `GET /api/v1/highLow/{highLowType}`

用途：查 player/team/game 的單場 high/low leaderboard。實測 path 使用小寫 `player`、`team`、`game` 可正常回 200；OpenAPI enum 寫的是 `PLAYER`、`TEAM`、`GAME`。

### 參數

| 參數 | 位置 | 型態 | 意義 |
|---|---|---:|---|
| `highLowType` | path | enum | `player`、`team`、`game`。無效值回 400，屬參數問題非權限問題。 |
| `statGroup` | query | array/string | `hitting`、`pitching`、`fielding` 等。建議指定，避免回傳不符合預期的 group。 |
| `sortStat` | query | array/string | 統計排序欄位，應使用 `/highLow/types` 的 `lookupParam`。 |
| `season` | query | array/string | 球季，例如 `2026`。 |
| `gameType` | query | array/string | 比賽類型，常用 `R` regular season。未指定時實測回 regular season。 |
| `teamId` | query | integer | 限定球隊。 |
| `leagueId` | query | integer | 限定聯盟。 |
| `sportId` | query | integer | 限定層級，MLB 為 `1`。 |
| `offset` | query | integer | 分頁起點。 |
| `limit` | query | integer | 回傳筆數。注意同名次 tie 可能另外進 `splitsTiedWithLimit`。 |
| `fields` | query | array/string | Stats API 欄位裁切參數。 |

### 回傳 wrapper 欄位

| 欄位 | 型態 | 意義 |
|---|---:|---|
| `copyright` | string | MLBAM 版權聲明。 |
| `highLowResults[]` | array | 一個或多個 leaderboard container。`team` 查詢可能回兩組：單隊單場與雙隊整場合計。 |

### `highLowResults[]` container 欄位

| 欄位 | 型態 | 意義 |
|---|---:|---|
| `group.displayName` | string | 統計群組，例如 `hitting`、`pitching`。 |
| `totalSplits` | integer | 符合條件的總筆數，不只是本次 `limit` 回來的筆數。 |
| `exemptions[]` | array | 例外/排除規則；實測樣本為空。 |
| `splits[]` | array | 主要排行榜結果。 |
| `splitsTiedWithOffset[]` | array | 因 offset 邊界同名次而額外列出的結果。 |
| `splitsTiedWithLimit[]` | array | 因 limit 邊界同名次而額外列出的結果。若第 5 名多人並列，這裡會補同名次資料。 |
| `season` | string | 球季。 |
| `gameType.id` | string | 比賽類型代碼，例如 `R`。 |
| `gameType.description` | string | 比賽類型文字，例如 `Regular Season`。 |
| `sortStat` | object | 本次排序統計，結構同 `/highLow/types` 的單筆 stat type。 |
| `combinedStats` | boolean | 是否為合併統計。實測 high/low 一般為 `false`。 |
| `disclaimers[]` | array | OpenAPI schema 欄位；實測未出現。 |
| `parameters` | object | OpenAPI schema 欄位；實測未出現。可能回顯查詢參數。 |
| `type` | object/string | OpenAPI schema 欄位；實測未出現。 |
| `stats` | object | OpenAPI schema 欄位；實測未出現。 |
| `player` | object | OpenAPI schema 欄位；container 層級球員，實測未出現。 |
| `team` | object | OpenAPI schema 欄位；container 層級球隊，實測未出現。 |
| `sport` | object | OpenAPI schema 欄位；container 層級 sport，實測未出現。 |
| `playerPool` | string/object | OpenAPI schema 欄位；實測未出現。 |

### `splits[]` / tie split 欄位

| 欄位 | 型態 | 意義 |
|---|---:|---|
| `season` | string | 該筆所屬球季。 |
| `stat` | object | 排名統計值。key 會依 `sortStat` 改變，例如 `{"homeRuns": 3}`、`{"strikeOuts": 15}`、`{"runs": 32}`。 |
| `team.id` | integer | 球員或單隊紀錄的球隊 id。 |
| `team.name` | string | 球隊名稱。 |
| `team.link` | string | Stats API team link。 |
| `player.id` | integer | 球員 id；只在 `highLowType=player` 出現。 |
| `player.fullName` | string | 球員全名。 |
| `player.link` | string | Stats API people link。 |
| `player.firstName` | string | 名。 |
| `player.lastName` | string | 姓。 |
| `opponent.id` | integer | 對手球隊 id；player 與單隊 team leaderboard 常見。 |
| `opponent.name` | string | 對手球隊名稱。 |
| `opponent.link` | string | Stats API team link。 |
| `homeTeam.id/name/link` | object | 整場 game leaderboard 或 team 的整場合計 container 使用。 |
| `awayTeam.id/name/link` | object | 整場 game leaderboard 或 team 的整場合計 container 使用。 |
| `date` | string | 比賽日期，`YYYY-MM-DD`。 |
| `gameType` | string | split 層級比賽類型代碼；打者 HR 樣本出現 `R`，投手 K 樣本未出現但 container 有。 |
| `isHome` | boolean | 對該筆主體而言是否主場。`game` 整場合計時此值語意較弱，實測可能為 `false`。 |
| `rank` | integer | 名次；並列會共用名次。 |
| `gameInnings` | integer | 該場總局數。 |
| `game.gamePk` | integer | 比賽 `gamePk`。可接 `/api/v1.1/game/{gamePk}/feed/live` 或 `/api/v1/game/{gamePk}/content`。 |
| `game.link` | string | live feed link。 |
| `game.content.link` | string | content/highlights link。 |
| `game.gameNumber` | integer | 雙重賽場次序號。 |
| `game.dayNight` | string | `day` 或 `night`。 |

### 打者範例

請求：

```text
GET /api/v1/highLow/player?season=2026&sportId=1&statGroup=hitting&sortStat=homeRuns&limit=5
```

實測第一名 split：

| 欄位 | 值 | 意義 |
|---|---:|---|
| `player.fullName` | `Junior Caminero` | 球員。 |
| `stat.homeRuns` | `3` | 單場 3 HR。 |
| `team.name` | `Tampa Bay Rays` | 所屬球隊。 |
| `opponent.name` | `Kansas City Royals` | 對手。 |
| `date` | `2026-06-25` | 比賽日期。 |
| `rank` | `1` | 本季 MLB 單場 HR 並列第一。 |
| `game.gamePk` | `822961` | 可接 live/content API。 |

若要套到本專案打者，例如 DB 內 `Hao-Yu Lee` (`player_mlb_id=701678`) 或 `Tsung-Che Cheng` (`691907`)，此端點不能直接用 `playerId` 查個人；做法是抓 leaderboard 後用 `player.id` 比對台灣球員清單。

### 投手範例

請求：

```text
GET /api/v1/highLow/player?season=2026&sportId=1&statGroup=pitching&sortStat=strikeOuts&limit=5
```

實測第一名 split：

| 欄位 | 值 | 意義 |
|---|---:|---|
| `player.fullName` | `Jacob Misiorowski` | 球員。 |
| `stat.strikeOuts` | `15` | 單場 15 K。 |
| `team.name` | `Milwaukee Brewers` | 所屬球隊。 |
| `opponent.name` | `Philadelphia Phillies` | 對手。 |
| `date` | `2026-06-12` | 比賽日期。 |
| `rank` | `1` | 本季 MLB 單場 K 第一。 |
| `game.gamePk` | `823778` | 可接 live/content API。 |

若要套到本專案投手，例如 DB 內 `Kai-Wei Teng` (`678906`) 或 `Yu-Min Lin` (`801179`)，同樣需抓 leaderboard 後以 `player.id` 比對。

### Team 與 Game 差異

`/highLow/team?...sortStat=homeRuns` 實測回兩個 container：

- 第一組是單隊單場，例如 Cubs 單場 8 HR。
- 第二組是整場雙隊合計，例如 Athletics vs Brewers 合計 11 HR；split 使用 `homeTeam`/`awayTeam`，不使用 `team`/`opponent`。

`/highLow/game?...sortStat=runs` 實測回整場紀錄，例如 Athletics vs Rockies 合計 32 runs，split 使用 `homeTeam`/`awayTeam`。

## Home Run Derby endpoints

這組端點共用同一種 response schema：`HomeRunDerbyRestObject`。差別在於模式：

| Method | Path | 實測/推定用途 |
|---|---|---|
| GET | `/api/v1/homeRunDerby/{gamePk}/pool` | Pool format Derby。 |
| GET | `/api/v1/homeRunDerby/pool` | Spec 內列出，但實測 `?gamePk=778566` 仍 500；不建議使用。 |
| GET | `/api/v1/homeRunDerby/{gamePk}/mixed` | Bracket/Pool mixed mode。 |
| GET | `/api/v1/homeRunDerby/mixed` | Spec 內列出，但實測 `?gamePk=778566` 仍 500；不建議使用。 |
| GET | `/api/v1/homeRunDerby/{gamePk}` | Bracket 預設模式。 |
| GET | `/api/v1/homeRunDerby` | Spec 內列出，但實測 `?gamePk=778566` 仍 500；不建議使用。 |
| GET | `/api/v1/homeRunDerby/{gamePk}/bracket` | Bracket mode，語意最明確。 |
| GET | `/api/v1/homeRunDerby/bracket` | Spec 內列出，但實測 `?gamePk=778566` 仍 500；不建議使用。 |

注意：`778566` 是 2025 MLB All-Star Game，不是 Home Run Derby；回 404 `Game data couldn't be found` 屬正常。一般 All-Star Game `gamePk` 不等於 Derby endpoint 的有效 `gamePk`。

### HomeRunDerbyRestObject 欄位

| 欄位 | 型態 | 意義 | 專案價值 |
|---|---:|---|---|
| `copyright` | string | MLBAM 版權聲明。 | 低。 |
| `info` | object | Derby event/schedule 資訊，schema 為 `ScheduleEventRestObject`。 | 低到中，只在做 Derby 專頁有用。 |
| `status` | object | Derby 即時狀態，schema 為 `HomeRunDerbyStatusRestObject`。 | 低，只有 live Derby 有用。 |
| `rounds[]` | array | 每輪資料，schema 為 `HomeRunDerbyRoundRestObject`。 | 中，若做 Derby 視覺化才有用。 |
| `players[]` | array | 參賽球員，schema 為 `BaseballPersonRestObject`。 | 低，本專案追台灣球員時幾乎不會用到。 |

### `info` 欄位

`info` 是 schedule event。OpenAPI schema 包含：

| 欄位 | 意義 |
|---|---|
| `id` | event id。 |
| `nonGameGuid` | 非正式比賽事件 GUID。 |
| `name` | 活動名稱。 |
| `link` | Stats API event link。 |
| `eventType` | 活動類型。 |
| `eventDate` | 開始時間。 |
| `endDateTime` | 結束時間。 |
| `images[]` | 活動圖片。 |
| `venue` | 場地。 |
| `sports[]` | 關聯 sport。 |
| `leagues[]` | 關聯 league。 |
| `divisions[]` | 關聯 division。 |
| `game` | 若活動連到 game，這裡放 game schedule item。 |
| `content` | CMS/content 資訊。 |
| `timeZone` | 時區。 |
| `designations[]` | 活動標籤/指定分類。 |
| `tickets[]` | 票務資訊。 |
| `promotions[]` | 促銷資訊。 |
| `eventStatus` | 活動狀態。 |
| `isMultiDay` | 是否跨日。 |
| `isPrimaryCalendar` | 是否主要 calendario event。 |
| `fileCode` | MLB 內部 file code。 |
| `eventNumber` | 活動序號。 |
| `publicFacing` | 是否公開面向。 |
| `teams[]` | 關聯球隊。 |
| `trackingVersion` | tracking data version。 |
| `coachingVideo[]` | coaching video media source type。 |
| `ruleSettings[]` | 規則設定。 |
| `broadcasts[]` | 轉播資訊。 |

### `status` 欄位

| 欄位 | 意義 |
|---|---|
| `regulationRoundLenth` | 拼字錯誤的舊欄位，正規輪時間長度。 |
| `regulationRoundLength` | 正規輪時間長度。 |
| `state` | Derby 狀態。 |
| `currentRound` | 目前第幾輪。 |
| `currentRoundInProgress` | 該輪是否進行中。 |
| `currentRoundTimeLeft` | 該輪剩餘時間文字。 |
| `scheduledRounds` | 預定總輪數。 |
| `inTieBreaker` | 是否在 tie-breaker。 |
| `tieBreakerNum` | 第幾個 tie-breaker。 |
| `currentBatter` | 目前打者，`BaseballPersonRestObject`。 |
| `clockStopped` | 計時是否暫停。 |
| `bonusTime` | 是否在 bonus time。 |
| `bonusDistanceNeededPerRound` | 每輪觸發 bonus 所需距離。 |
| `bonusCountNeededPerRound` | 每輪觸發 bonus 所需次數。 |
| `pitchesInRound` | 本輪已投球數。 |
| `pitchesRemaining` | 剩餘投球數。 |
| `bonusOutsCurrent` | bonus out 目前數。 |
| `bonusOutsTotal` | bonus out 總數。 |
| `bonusTypeOuts` | bonus 是否採 outs 制。 |

### `rounds[]` 欄位

| 欄位 | 意義 |
|---|---|
| `round` | 第幾輪。 |
| `numBatters` | 該輪打者數。 |
| `type` | 輪次模式，例如 bracket/pool 類型。 |
| `roundTime` | 該輪時間長度。 |
| `numberOfPitches` | 該輪投球數。 |
| `matchups[]` | bracket 對戰組合。 |
| `batters[]` | pool 或該輪打者清單。 |

### `matchups[]` 欄位

| 欄位 | 意義 |
|---|---|
| `topSeed` | 高種子/上方打者，結構同 `HomeRunDerbyRoundBatterRestObject`。 |
| `bottomSeed` | 低種子/下方打者，結構同 `HomeRunDerbyRoundBatterRestObject`。 |

### Round batter 欄位

| 欄位 | 意義 |
|---|---|
| `started` / `isStarted` | 是否已開始。 |
| `complete` / `isComplete` | 是否已完成。 |
| `winner` / `isWinner` | 是否勝者。 |
| `player` | 球員資料，`BaseballPersonRestObject`。 |
| `topDerbyHitData` | 該打者最佳擊球資料，`BaseballHitDataRestObject`。 |
| `hits[]` | 每次擊球資料。 |
| `seed` | 種子序。 |
| `order` | 出場順序。 |
| `numHomeRuns` | 該輪全壘打數。 |

### `hits[]` 欄位

| 欄位 | 意義 |
|---|---|
| `bonusTime` / `isBonusTime` | 是否 bonus time。 |
| `tieBreaker` / `isTieBreaker` | 是否 tie-breaker。 |
| `homeRun` / `isHomeRun` | 是否全壘打。 |
| `hitData` | 擊球資料，`HitSegmentRestObject`。通常包含擊球軌跡/距離等 Statcast 類資料，但實際欄位須以有效 Derby gamePk payload 為準。 |
| `time` | 該次擊球時間。 |
| `playId` | 該次擊球 play id。 |
| `timeRemaining` | 剩餘時間文字。 |
| `timeRemainingSeconds` | 剩餘秒數。 |
| `bonusOutsCurrent` | bonus out 目前數。 |
| `bonusOutsTotal` | bonus out 總數。 |
| `tieBreakerNum` | 第幾個 tie-breaker。 |

### `players[]` / `player` 常見欄位

`BaseballPersonRestObject` schema 很大，Derby 回傳未必全部填值。對本專案可能有用的是：

| 欄位 | 意義 |
|---|---|
| `id` | MLB player id。 |
| `fullName` | 球員全名。 |
| `link` | `/api/v1/people/{id}`。 |
| `firstName` / `lastName` | 名/姓。 |
| `primaryNumber` | 背號。 |
| `birthDate` / `currentAge` | 生日/年齡。 |
| `birthCity` / `birthStateProvince` / `birthCountry` / `nationality` | 出生地與國籍。 |
| `height` / `weight` | 身高體重。 |
| `active` | 是否現役。 |
| `currentTeam` | 目前球隊。 |
| `primaryPosition` | 主要守位。 |
| `batSide` / `pitchHand` | 打擊/投球慣用手。 |
| `mlbDebutDate` | MLB 初登場日期。 |
| `nameSlug` | MLB slug。 |
| `strikeZoneTop` / `strikeZoneBottom` | 好球帶上下緣。 |

其他 schema 欄位包含 `social`、`education`、`photos`、`stats`、`awards`、`draft`、`transactions`、`articles`、`videos`、`relatives`、`xrefIds`、`depthCharts` 等，Derby 場景通常不是主要價值來源。

## 對本專案的建議

1. 可以加一個 optional 的 `highLow` fetcher，但只針對 MLB 層級與少數有價值統計，例如打者 `homeRuns`、`hits`、`rbi`，投手 `strikeouts`、`inningsPitched`。
2. 儲存方式建議不要塞進現有 `game_logs`，而是另建 cache，例如 `leaderboards_json` 或 build-time only cache。`highLow` 是 league leaderboard，不是球員原始比賽紀錄。
3. 若只想顯示台灣球員是否上榜，抓 `limit=100` 或分頁後以 `player.id` 比對 `players.mlb_id` 即可。
4. `homeRunDerby` 暫不建議納入 pipeline。除非未來有台灣球員參加 Derby，否則與投手、MiLB、日常追蹤沒有直接關係。
5. 現有 DB 的 `game_logs.game_id` 可用於 `/game/{gamePk}/content` 和 `/api/v1.1/game/{gamePk}/feed/live`，但不能當作 Home Run Derby gamePk 使用，除非該 row 本身就是 Derby 事件；目前資料庫看起來都是一般例行賽/小聯盟比賽。

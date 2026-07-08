# MLB Stats API Endpoint 總覽

本文件彙整這個專案對 MLB Stats API endpoint 的調查結果，包含：目前程式碼實際使用哪些 endpoint、官方完整 endpoint 目錄（依 `MLB-StatsAPI-Spec.json` 整理）、以及哪些 endpoint 需要 MLB 內部帳號（Okta SSO）才能存取。

> 標記說明：🟢 公開（不需登入）／🔒 需要 Okta 登入的內部帳號／⚠️ 內部寫入操作（非查詢用途，不應使用）
> 「實測」代表已用 `curl` 對 `https://statsapi.mlb.com` 實際發送請求驗證；「推測」代表未逐一測試，是依據同系列 endpoint 或 tag 的存取模式推斷。
>
> **2026-07-08 更新**：已對第四節目錄中全部 190 個 path 逐一實測（GET 皆已呼叫；POST 寫入操作維持不呼叫，仍標記為「推測」）。測試方式：對每個 path 帶入真實參數（gamePk=822884、personId=691907、teamId=133 等）送出請求，依 HTTP 狀態碼與回應內容（是否為 JSON 資料 vs. 導向 `inside.mlb.com`/`mlb.okta.com` 的 Okta 登入頁）判斷存取狀態。400/404/500 但回應為一般 JSON 錯誤訊息（缺參數、物件不存在等）者，判定為公開但參數需調整，非權限問題。測試結果比原先「推測」多發現數個實際需要 Okta 的 endpoint（詳見第三節）。

---

## 目錄

1. [目前專案使用的 Endpoint](#一目前專案使用的-endpoint)
2. [受限 Endpoint：Bat Tracking 與 Okta 帳號](#二受限-endpoint bat-tracking-與-okta-帳號)
3. [存取權限規律](#三存取權限規律)
4. [完整 Endpoint 目錄（依 tag 分組）](#四完整-endpoint-目錄依-tag-分組)
5. [建議後續評估納入的公開 Endpoint](#五建議後續評估納入的公開-endpoint)
6. [非 MLB Stats API 的輔助資源（實測結果）](#六非-mlb-stats-api-的輔助資源實測結果)

---

## 一、目前專案使用的 Endpoint

| 檔案 | Endpoint | 用途 |
|---|---|---|
| `site_builder/api/players.py:36` | `GET /people/{mlb_id}?hydrate=transactions,rosterEntries,currentTeam` | 球員基本資料、異動紀錄、名單狀態、所屬球隊 |
| `site_builder/api/players.py:81` | `GET /teams/{team_id}` | 依 `team_id` 查 `sportId`，換算層級（MLB/AAA/AA…） |
| `site_builder/api/stats.py:24,31-32` | `GET /people/{mlb_id}/stats?stats=yearByYear&group={groups}`（MLB，另加 `leagueListId=milb_all` 查 MiLB） | 生涯逐季數據 |
| `site_builder/api/stats.py:58,66-67` | `GET /people/{mlb_id}/stats?stats=seasonAdvanced&group={groups}&season={year}` | 進階數據（MLB 限定） |
| `site_builder/api/stats.py:89-99` | `GET /people/{mlb_id}/stats?stats=gameLog...` | 逐場紀錄（MLB + MiLB） |
| `site_builder/api/stats.py:119-120,150-151` | `GET /people/{mlb_id}/stats`（xBA/xSLG/xwOBA 等） | Statcast 期望值數據（MLB 限定） |
| `site_builder/api/games.py:18,35-36` | `GET (v1.1) /game/{game_pk}/feed/live` | 逐球 play-by-play（含 Statcast 打擊資料） |
| `site_builder/api/schedule.py:20-21` | `GET /schedule?teamId=...` | 下一場比賽資訊 |
| `site_builder/api/league_stats.py:20` | `GET /teams?sportId={sport_id}&season={year}` | 全聯盟球隊清單 |
| `site_builder/api/league_stats.py:43-44` | `GET /teams/stats?sportId={sport_id}&stats=season&group=pitching&season={year}` | 全聯盟球隊投手數據（計算 FIP 常數等用） |
| `site_builder/api/tjstats.py:27,61` | `GET https://tjstats.ca/park-factors/...`（非 MLB API） | 球場因子（外部資料源） |

以上全部是**不需登入**的公開 endpoint。

---

## 二、受限 Endpoint：Bat Tracking 與 Okta 帳號

實測 `GET /api/v1/batTracking/game/{gamePk}/{playId}`（用真實 gamePk=822884、playId 皆來自公開 `feed/live` 回應）回傳 **HTTP 401**，導向 `inside.mlb.com` / `mlb.okta.com` 的內部登入頁，而非 JSON 資料。

註冊管道：[`inside.mlb.com/UserRegistrationForm/?GROUP=StatsAPI`](https://inside.mlb.com/UserRegistrationForm/?GROUP=StatsAPI)。但需注意：

- MLB Stats API 大部分公開 endpoint（本專案目前用的都是）本來就不需要帳號，僅商業/大量使用需書面授權。
- `batTracking` 這類走 Okta SSO 的 endpoint，屬於保留給 MLB 內部員工／球隊／媒體合作夥伴的系統，公開註冊表單**不保證**能解鎖此權限；社群維護的 [MLB-StatsAPI wiki](https://github.com/toddrob99/MLB-StatsAPI/wiki/Endpoints) 完全沒有收錄這類 endpoint。
- Bat tracking 的**彙總指標**（bat speed、swing length）已公開在 [Baseball Savant Bat Tracking Leaderboard](https://baseballsavant.mlb.com/leaderboard/bat-tracking)，若需求只是統計數字而非逐球原始追蹤資料，這條路更務實。

---

## 三、存取權限規律

對全部 190 個 path 逐一實測後歸納出的規律（原先的「推測」規律大致成立，但實測揪出了幾個例外）：

**需要 Okta 登入（🔒）的都是 MLB 專屬感測器/衍生模型資料，共 25 個 GET endpoint**：
- Bat Tracking（球棒追蹤）
- Biomechanics、Skeletal（生物力學、骨架動作捕捉）
- Weather（球場感測器天氣資料，4 個全數需登入）
- Predictions（play-level 預測模型，2 個全數需登入）
- `analytics` tag 下的 guid 系列：`contextMetrics`、`contextMetricsAverages`、`analytics`、`guids`、`lastPitch`、`/analytics/guids`、`/analytics/game`
- `Stats` tag 下的 `analytics/*` 子集（`sprayChart`、`stolenBaseProbability`、`outsAboveAverage`）

**實測前未預期、但確認需要 Okta 的 endpoint（原先誤判為公開）**：
- `GET /jobs/umpires/games/{umpireId}`（`Job` tag 下其餘 4 個 endpoint 皆公開，只有這個要登入）
- `GET /people/{personId}/stats/metrics`、`GET /stats/metrics`（帶 `metrics` 參數查詢逐球追蹤指標，皆需登入；但同樣列在 `Misc` tag 的 enum 端點 `GET /stats/search/stats`、`GET /statTypes` 等本身是公開的）
- `GET /stats/search`（需登入；但外觀很像的 enum 端點 `GET /stats/search/stats`、`/stats/search/params`、`/stats/search/groupByTypes`、`/stats/search/config` 全部公開，要特別注意路徑差異）
- `GET /schedule/trackingEvents`（`Schedule` tag 下唯一需要登入的 endpoint，其餘皆公開）
- `GET /streaks`（`Streaks` tag 下需要登入，但 `GET /streaks/types` 公開）

**反例：analytics tag 裡也有公開的 endpoint**：`GET /game/{gamePk}/{guid}/homeRunBallparks` 雖然和同組的 `contextMetrics`、`analytics`、`guids` 共用 `{guid}` 路徑樣式，實測結果卻是公開的（帶錯誤/不存在的 guid 回傳一般 400/404 JSON 錯誤，而非導向 Okta 登入頁）。

**一般參考資料／box score／排行榜類都維持公開（🟢）**：statGroups、pitchTypes、gameTypes、milestones、stats/leaders、broadcast、transactions、`game/{gamePk}/withMetrics`、`game/{gamePk}/contextMetrics`（注意：這個不帶 guid 的版本和上面 analytics tag 帶 guid 的 `contextMetrics` 是不同 endpoint）等，皆實測回傳 200。

**⚠️ 特殊提醒**：spec 中出現 `POST /jobTypes`、`POST /gameStatus`（描述為「Clear all status types」）、`POST /teams/{teamId}/alumni`、`POST /game/{gamePk}/{guid}/contextMetricsAverages`，這些是 MLB 內部後台的寫入操作，與一般開發者可用的查詢 API 無關，本次測試**未呼叫**這些 POST endpoint，不應呼叫。

---

## 四、完整 Endpoint 目錄（依 tag 分組）

來源：`MLB-StatsAPI-Spec.json`（OpenAPI 3.0，190 個 path、33 個 tag）。

### Attendance

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/attendance` | Get team attendance | 🟢 實測公開（400，需帶 teamId/leagueId/leagueListId 其中之一，非權限問題） |

### Awards

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/awards/{awardId}/recipients` | View recipients of an award | 🟢 實測公開 (200) |
| GET | `/api/v1/awards` | View awards info | 🟢 實測公開 (200) |
| GET | `/api/v1/awards/{awardId}` | View awards info | 🟢 實測公開 (200) |

### Bat Tracking

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/batTracking/game/{gamePk}/{playId}` | View Bat Tracking Data by playId and gameId | 🔒 實測需 Okta (401) |

### Biomechanics

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/game/{gamePk}/{playId}/analytics/biomechanics/{positionId}` | View Biomechanical data by playId and gameId filtered by player positionId | 🔒 實測需 Okta (401) |

### Broadcast

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/broadcasters` | Get All Active Broadcasters | 🟢 實測公開 (200) |
| GET | `/api/v1/broadcast` | Get Broadcasters | 🟢 實測公開（400，需帶 broadcasterIds 參數，非權限問題） |

### Conference

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/conferences` | View conference info | 🟢 實測公開 (200) |
| GET | `/api/v1/conferences/{conferenceId}` | View conference info | 🟢 實測公開（用真實 conferenceId=301 測試回傳 200；原測試值 1 不存在故先前誤判為 404） |

### Division

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/divisions` | Get division information | 🟢 實測公開 (200) |
| GET | `/api/v1/divisions/{divisionId}` | Get division information | 🟢 實測公開 (200) |

### Draft

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/draft/{year}/latest` | Get the last drafted player and the next 5 teams up to pick | 🟢 實測公開 (200) |
| GET | `/api/v1/draft/prospects` | View MLB Draft Prospects | 🟢 實測公開 (200) |
| GET | `/api/v1/draft/prospects/{year}` | View MLB Draft Prospects | 🟢 實測公開 (200) |
| GET | `/api/v1/draft` | View MLB Drafted Players | 🟢 實測公開 (200) |
| GET | `/api/v1/draft/{year}` | View MLB Drafted Players | 🟢 實測公開 (200) |

### Game

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/game/{game_pk}/playByPlay` | Get game play By Play | 🟢 實測公開 (200) |
| GET | `/api/v1/game/{game_pk}/linescore` | Get game linescore | 🟢 實測公開 (200) |
| GET | `/api/v1/game/{game_pk}/feed/color` | Get game color feed. | 🟢 實測公開（測試回傳 404，該場比賽無 color feed 資料，非權限問題） |
| GET | `/api/v1/game/{game_pk}/feed/color/timestamps` | Retrieve all of the color timestamps for a game. | 🟢 實測公開（同上，404 為無資料非權限問題） |
| GET | `/api/v1/game/{game_pk}/content` | Retrieve all content for a game. | 🟢 實測公開 (200) |
| GET | `/api/v1/game/{game_pk}/boxscore` | Get game boxscore. | 🟢 實測公開 (200) |
| GET | `/api/v1/game/{gamePk}/withMetrics` | Get game info with metrics | 🟢 實測公開 (200) |
| GET | `/api/v1/game/{gamePk}/winProbability` | Get the win probability for this game | 🟢 實測公開 (200) |
| GET | `/api/v1/game/{gamePk}/contextMetrics` | Get the context metrics for this game based on its current state | 🟢 實測公開 (200)（注意：與下方 analytics tag 的 `/game/{gamePk}/{guid}/contextMetrics` 是不同 endpoint，該帶 guid 版本需 Okta） |
| GET | `/api/v1/game/changes` | View a game change log | 🟢 實測公開 (200) |
| GET | `/api/v1.1/game/{game_pk}/feed/live` | Get live game status. | 🟢 實測公開 (200) |
| GET | `/api/v1.1/game/{game_pk}/feed/live/timestamps` | Retrieve all of the play timestamps for a game. | 🟢 實測公開 (200) |
| GET | `/api/v1.1/game/{game_pk}/feed/live/diffPatch` | Get live game status diffPatch. | 🟢 實測公開 (200) |

### Game Pace

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/gamePace` | View time of game info | 🟢 實測公開 (200，需帶 season 參數) |

### High/Low

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/highLow/{highLowType}` | View high/low stats by player or team | 🟢 實測公開（400，highLowType 需為有效值，非權限問題） |
| GET | `/api/v1/highLow/types` | View high/low stat types | 🟢 實測公開 (200) |

### Homerun Derby

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/homeRunDerby/{gamePk}/pool` | View home run derby pool | 🟢 實測公開（404，該 gamePk 非全壘打大賽場次，非權限問題） |
| GET | `/api/v1/homeRunDerby/pool` | View home run derby pool | 🟢 實測公開（500，缺必要參數，非權限問題） |
| GET | `/api/v1/homeRunDerby/{gamePk}/mixed` | View home run derby mixed mode (Bracket/Pool combo) | 🟢 實測公開（404，同上，非權限問題） |
| GET | `/api/v1/homeRunDerby/mixed` | View home run derby mixed mode (Bracket/Pool combo) | 🟢 實測公開（500，同上，非權限問題） |
| GET | `/api/v1/homeRunDerby/{gamePk}` | View a home run derby object | 🟢 實測公開（404，同上，非權限問題） |
| GET | `/api/v1/homeRunDerby` | View a home run derby object | 🟢 實測公開（500，缺必要參數，非權限問題） |
| GET | `/api/v1/homeRunDerby/{gamePk}/bracket` | View a home run derby object | 🟢 實測公開（404，同上，非權限問題） |
| GET | `/api/v1/homeRunDerby/bracket` | View a home run derby object | 🟢 實測公開（500，同上，非權限問題） |

### Job

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/jobs` | Get jobs by type | 🟢 實測公開 (200) |
| GET | `/api/v1/jobs/umpires` | Get umpires | 🟢 實測公開 (200) |
| GET | `/api/v1/jobs/umpires/games/{umpireId}` | Get umpires and associated game for umpireId | 🔒 實測需 Okta (401，導向登入頁) |
| GET | `/api/v1/jobs/officialScorers` | Get official scorers | 🟢 實測公開 (200) |
| GET | `/api/v1/jobs/datacasters` | Get datacaster jobs | 🟢 實測公開 (200) |

### League

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/league/{leagueId}/allStarWriteIns` | View all star write ins info | 🟢 實測公開 (200) |
| GET | `/api/v1/leagues/{leagueId}/allStarWriteIns` | View all star write ins info | 🟢 實測公開 (200) |
| GET | `/api/v1/league/{leagueId}/allStarFinalVote` | View all star final vote info | 🟢 實測公開 (200) |
| GET | `/api/v1/leagues/{leagueId}/allStarFinalVote` | View all star final vote info | 🟢 實測公開 (200) |
| GET | `/api/v1/league/allStarBallot` | View al star ballot info | 🟢 實測公開（400，需帶 sportId 等參數，非權限問題） |
| GET | `/api/v1/league/{leagueId}/allStarBallot` | View al star ballot info | 🟢 實測公開 (200) |
| GET | `/api/v1/leagues/allStarBallot` | View al star ballot info | 🟢 實測公開（400，同上，非權限問題） |
| GET | `/api/v1/leagues/{leagueId}/allStarBallot` | View al star ballot info | 🟢 實測公開 (200) |
| GET | `/api/v1/league` | View league info | 🟢 實測公開 (200) |
| GET | `/api/v1/league/{leagueId}` | View league info | 🟢 實測公開 (200) |
| GET | `/api/v1/leagues` | View league info | 🟢 實測公開 (200) |
| GET | `/api/v1/leagues/{leagueId}` | View league info | 🟢 實測公開 (200) |

### Milestones

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/milestones` | View pending and achieved milestones. | 🟢 實測公開 (200) |
| GET | `/api/v1/milestoneTypes` | View available milestoneType options | 🟢 實測公開 (200) |
| GET | `/api/v1/milestoneStatistics` | View available milestone statistics options | 🟢 實測公開 (200) |
| GET | `/api/v1/milestoneLookups` | View available milestoneLookup options | 🟢 實測公開 (200) |
| GET | `/api/v1/milestoneDurations` | View available milestoneDurations options | 🟢 實測公開 (200) |
| GET | `/api/v1/achievementStatuses` | View available achievementStatus options | 🟢 實測公開 (200) |

### Misc（設定/對照表用的 enum 端點，共 56 個）

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/jobTypes` | List all job types | 🟢 實測公開 (200) |
| POST | `/api/v1/jobTypes` | （無描述） | ⚠️ 內部寫入操作（非查詢用途） |
| GET | `/api/v1/gameStatus` | List all status types | 🟢 實測公開 (200) |
| POST | `/api/v1/gameStatus` | Clear all status types | ⚠️ 內部寫入操作（非查詢用途） |
| GET | `/api/v1/windDirection` | List all wind direction options | 🟢 實測公開 (200) |
| GET | `/api/v1/weatherTrajectoryConfidences` | List all weather trajectories | 🟢 實測公開 (200) |
| GET | `/api/v1/violationTypes` | View available violationType options | 🟢 實測公開 (200) |
| GET | `/api/v1/videoResolutionTypes` | View video resolution options | 🟢 實測公開 (200) |
| GET | `/api/v1/transactionTypes` | List all transaction types | 🟢 實測公開 (200) |
| GET | `/api/v1/trackingVersions` | List all tracking versions | 🟢 實測公開 (200) |
| GET | `/api/v1/trackingVendors` | List all tracking vendors | 🟢 實測公開 (200) |
| GET | `/api/v1/trackingSystemOwners` | List all tracking system owners | 🟢 實測公開 (200) |
| GET | `/api/v1/trackingSoftwareVersions` | List the tracking software versions and notes | 🟢 實測公開 (200) |
| GET | `/api/v1/stats/search/stats` | List stat search stats | 🟢 實測公開 (200) |
| GET | `/api/v1/stats/search/params` | List stat search parameters | 🟢 實測公開 (200) |
| GET | `/api/v1/stats/search/groupByTypes` | List groupBy types | 🟢 實測公開 (200) |
| GET | `/api/v1/stats/search/config` | Stats Search Config Endpoint | 🟢 實測公開 (200) |
| GET | `/api/v1/statcastPositionTypes` | List all statcast position types | 🟢 實測公開 (200) |
| GET | `/api/v1/statTypes` | List all stat types | 🟢 實測公開 (200) |
| GET | `/api/v1/statGroups` | List all stat groups | 🟢 實測公開 (200) |
| GET | `/api/v1/statFields` | List all stat fields | 🟢 實測公開 (200) |
| GET | `/api/v1/standingsTypes` | List all standings types | 🟢 實測公開 (200) |
| GET | `/api/v1/sortModifiers` | List all stat fields | 🟢 實測公開 (200) |
| GET | `/api/v1/sky` | List all sky options | 🟢 實測公開 (200) |
| GET | `/api/v1/situationCodes` | List all situation codes | 🟢 實測公開 (200) |
| GET | `/api/v1/scheduleTypes` | List all possible schedule types | 🟢 實測公開 (200) |
| GET | `/api/v1/scheduleEventTypes` | List all schedule event types | 🟢 實測公開 (200) |
| GET | `/api/v1/runnerDetailTypes` | List runner detail types | 🟢 實測公開 (200) |
| GET | `/api/v1/ruleSettings` | List all ruleSettings | 🟢 實測公開 (200) |
| GET | `/api/v1/rosterTypes` | List all possible roster types | 🟢 實測公開 (200) |
| GET | `/api/v1/roofTypes` | List all roof types | 🟢 實測公開 (200) |
| GET | `/api/v1/reviewReasons` | List all replay review reasons | 🟢 實測公開 (200) |
| GET | `/api/v1/positions` | List all possible positions | 🟢 實測公開 (200) |
| GET | `/api/v1/playerStatusCodes` | List all player status codes | 🟢 實測公開 (200) |
| GET | `/api/v1/platforms` | List all possible platforms | 🟢 實測公開 (200) |
| GET | `/api/v1/pitchTypes` | List all pitch classification types | 🟢 實測公開 (200) |
| GET | `/api/v1/pitchCodes` | List all pitch codes | 🟢 實測公開 (200) |
| GET | `/api/v1/performerTypes` | List all possible performer types | 🟢 實測公開 (200) |
| GET | `/api/v1/moundVisitTypes` | List all mound visit types | 🟢 實測公開 (200) |
| GET | `/api/v1/metrics` | List all possible metrics | 🟢 實測公開 (200) |
| GET | `/api/v1/mediaState` | View media state options | 🟢 實測公開 (200) |
| GET | `/api/v1/lookup/values/all` | View all lookup values | 🟢 實測公開 (200) |
| GET | `/api/v1/logicalEvents` | List all logical event types | 🟢 實測公開 (200) |
| GET | `/api/v1/leagueLeaderTypes` | List all possible player league leader types | 🟢 實測公開 (200) |
| GET | `/api/v1/languages` | List all support languages | 🟢 實測公開 (200) |
| GET | `/api/v1/hitTrajectories` | List all hit trajectories | 🟢 實測公開 (200) |
| GET | `/api/v1/groupByTypes` | List groupBy types | 🟢 實測公開 (200) |
| GET | `/api/v1/gamedayTypes` | List all gameday types | 🟢 實測公開 (200) |
| GET | `/api/v1/gameTypes` | List all game types | 🟢 實測公開 (200) |
| GET | `/api/v1/freeGameTypes` | View free game types | 🟢 實測公開 (200) |
| GET | `/api/v1/fielderDetailTypes` | List fielder detail types | 🟢 實測公開 (200) |
| GET | `/api/v1/eventTypes` | List all event types | 🟢 實測公開 (200) |
| GET | `/api/v1/eventStatus` | List all possible event status types | 🟢 實測公開 (200) |
| GET | `/api/v1/coachingVideoTypes` | List all coaching video types | 🟢 實測公開 (200) |
| GET | `/api/v1/broadcastAvailability` | View broadcast availability options | 🟢 實測公開 (200) |
| GET | `/api/v1/baseballStats` | List all baseball stats | 🟢 實測公開 (200) |

### Person

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/people/{personId}/stats` | View a players stats | 🟢 實測公開 (200) |
| GET | `/api/v1/people/{personId}/stats/metrics` | View a player's stat metrics | 🔒 實測需 Okta (401，導向登入頁) |
| GET | `/api/v1/people/{personId}/stats/game/{gamePk}` | View a player's game stats | 🟢 實測公開 (200) |
| GET | `/api/v1/people/{personId}/awards` | View a player's awards | 🟢 實測公開 (200) |
| GET | `/api/v1/people/{personId}` | View a player | 🟢 實測公開 (200) |
| GET | `/api/v1/people` | View a player | 🟢 實測公開 (200，需帶 personIds 參數) |
| GET | `/api/v1/people/search` | Search for a player by name | 🟢 實測公開 (200) |
| GET | `/api/v1/people/freeAgents` | Get free agents | 🟢 實測公開 (200，需帶 season 參數) |
| GET | `/api/v1/people/changes` | View a player's change log | 🟢 實測公開 (200，需帶 updatedSince 參數) |

### Predictions

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/props/play/predictions` | Get play-level predictions based on input scenarios | 🔒 實測需 Okta (401) |
| GET | `/api/v1/props/play/predictions/adjust` | Get play-level predictions based on input scenarios | 🔒 實測需 Okta (401) |

### Reviews

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/review` | Get review info | 🟢 實測公開（400/500，缺必要參數，非權限問題；正確用法未知） |

### Schedule

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/schedule/trackingEvents` | Get tracking event schedules | 🔒 實測需 Okta (401，導向登入頁) |
| GET | `/api/v1/schedule/postseason` | Get postseason schedule | 🟢 實測公開 (200) |
| GET | `/api/v1/schedule/postseason/tuneIn` | Get postseason TuneIn schedules | 🟢 實測公開 (200) |
| GET | `/api/v1/schedule/postseason/series` | Get postseason series schedules | 🟢 實測公開 (200) |
| GET | `/api/v1/schedule/games/tied` | Get tied game schedules | 🟢 實測公開 (200，需帶 season 參數) |
| GET | `/api/v1/schedule` | View schedule info based on scheduleType. | 🟢 實測公開 (200，本專案已使用) |
| GET | `/api/v1/schedule/{scheduleType}` | View schedule info based on scheduleType. | 🟢 實測公開 (200) |

### Season

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/seasons/all` | View all seasons | 🟢 實測公開 (200) |
| GET | `/api/v1/seasons` | View season info | 🟢 實測公開 (200) |
| GET | `/api/v1/seasons/{seasonId}` | View season info | 🟢 實測公開 (200) |

### Skeletal

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/game/{gamePk}/{playId}/analytics/skeletalData/files` | View Skeletal Data by playId and gameId files | 🔒 實測需 Okta (401) |
| GET | `/api/v1/game/{gamePk}/{playId}/analytics/skeletalData/chunked` | View Skeletal Data by playId and gameId chunked | 🔒 實測需 Okta (401) |

### Sports

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/sports/{sportId}/players` | Get all players for a sport level | 🟢 實測公開 (200) |
| GET | `/api/v1/sports/{sportId}/allSportBallot` | Get ALL MLB ballot for sport | 🟢 實測公開 (200，需帶 season 參數) |
| GET | `/api/v1/sports` | Get sports information | 🟢 實測公開 (200) |
| GET | `/api/v1/sports/{sportId}` | Get sports information | 🟢 實測公開 (200) |

### Standings

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/standings/{standingsType}` | View standings for a league | 🟢 實測公開 (200) |
| GET | `/api/v1/standings` | View standings for a league | 🟢 實測公開 (200) |

### Stats

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/stats` | View stats | 🟢 實測公開 (200) |
| GET | `/api/v1/stats/search` | View stats from search | 🔒 實測需 Okta (401，導向登入頁；注意與公開的 `/stats/search/stats` 等 enum 端點不同) |
| GET | `/api/v1/stats/metrics` | View metric stats | 🔒 實測需 Okta (401，導向登入頁) |
| GET | `/api/v1/stats/leaders` | Get leaders for a statistic | 🟢 實測公開 (200) |
| GET | `/api/v1/stats/grouped` | View grouped stats | 🟢 實測公開 (200) |
| GET | `/api/v1/stats/analytics/stolenBaseProbability` | Get the probability of a hit for the given hit data | 🔒 實測需 Okta (401) |
| GET | `/api/v1/stats/analytics/sprayChart` | Get the spray chart info for the current batter | 🔒 實測需 Okta (401) |
| GET | `/api/v1/stats/analytics/outsAboveAverage` | Get outs above average for the current batter | 🔒 實測需 Okta (401) |

### Streaks

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/streaks` | View streaks | 🔒 實測需 Okta (401，導向登入頁) |
| GET | `/api/v1/streaks/types` | View streaks parameter options | 🟢 實測公開 (200) |

### Teams

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/teams/{teamId}/alumni` | View all team alumni | 🟢 實測公開 (200) |
| POST | `/api/v1/teams/{teamId}/alumni` | （無描述） | ⚠️ 內部寫入操作（非查詢用途） |
| GET | `/api/v1/teams/{teamId}/stats` | View a teams stats | 🟢 實測公開 (200) |
| GET | `/api/v1/teams/{teamId}/roster` | View a teams roster | 🟢 實測公開 (200) |
| GET | `/api/v1/teams/{teamId}/roster/{rosterType}` | View a teams roster | 🟢 實測公開 (200) |
| GET | `/api/v1/teams/{teamId}/personnel` | View all coaches for a team | 🟢 實測公開 (200) |
| GET | `/api/v1/teams/{teamId}/leaders` | View team stat leaders | 🟢 實測公開 (200) |
| GET | `/api/v1/teams/{teamId}/history` | View historical records for a list of teams | 🟢 實測公開 (200) |
| GET | `/api/v1/teams/history` | View historical records for a list of teams | 🟢 實測公開 (200) |
| GET | `/api/v1/teams/{teamId}/coaches` | View all coaches for a team | 🟢 實測公開 (200) |
| GET | `/api/v1/teams/{teamId}/affiliates` | View team and affiliate teams | 🟢 實測公開 (200) |
| GET | `/api/v1/teams/affiliates` | View team and affiliate teams | 🟢 實測公開 (200) |
| GET | `/api/v1/teams/stats` | View a teams stats | 🟢 實測公開 (200，本專案已使用) |
| GET | `/api/v1/teams/stats/leaders` | View leaders for team stats | 🟢 實測公開 (200) |
| GET | `/api/v1/teams` | View info for all teams | 🟢 實測公開 (200，本專案已使用) |
| GET | `/api/v1/teams/{teamId}` | View info for all teams | 🟢 實測公開 (200，本專案已使用) |

### Transactions

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/transactions` | View transaction info | 🟢 實測公開 (200) |

### Uniforms

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/uniforms/team` | View Team Uniform info | 🟢 實測公開 (200) |
| GET | `/api/v1/uniforms/game` | View Game Uniform info | 🟢 實測公開 (200) |

### Venues

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/venues` | View venue info | 🟢 實測公開 (200) |
| GET | `/api/v1/venues/{venueId}` | View venue info | 🟢 實測公開 (200) |

### Weather

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/weather/venues/{venueId}/full` | Get full weather for a venue. | 🔒 實測需 Okta (401) |
| GET | `/api/v1/weather/venues/{venueId}/basic` | Get basic weather for a venue. | 🔒 實測需 Okta (401) |
| GET | `/api/v1/weather/game/{gamePk}/{playId}` | Get the raw field weather data. | 🔒 實測需 Okta (401) |
| GET | `/api/v1/weather/game/{gamePk}/forecast/{roofType}` | Get the weather forecast for a game. | 🔒 實測需 Okta (401) |

### analytics

| Method | Path | 說明 | 存取狀態 |
|---|---|---|---|
| GET | `/api/v1/game/{gamePk}/{guid}/contextMetricsAverages` | Get a json file containing raw coordinate data and refined calculated metrics. | 🔒 實測需 Okta (401) |
| POST | `/api/v1/game/{gamePk}/{guid}/contextMetricsAverages` | Get a json file containing raw coordinate data and refined calculated metrics. | 🔒 推測需 Okta（同系列，未逐一實測） |
| GET | `/api/v1/game/{gamePk}/{guid}/homeRunBallparks` | Get if the play is a home run is each park for a specific play. | 🟢 實測公開（400/404，非 Okta 導向頁；與同組其他 analytics 端點不同，實際不需登入） |
| GET | `/api/v1/game/{gamePk}/{guid}/contextMetrics` | Get context metrics for a specific gamePk. | 🔒 實測需 Okta (401)（注意：與上方 Game tag 不帶 guid 的 `/game/{gamePk}/contextMetrics` 是不同 endpoint，該版本公開） |
| GET | `/api/v1/game/{gamePk}/{guid}/analytics` | Get Statcast data for a specific play. | 🔒 實測需 Okta (401) |
| GET | `/api/v1/game/{gamePk}/guids` | Get the GUIDs (plays) for a specific game. | 🔒 實測需 Okta (401) |
| GET | `/api/v1/game/lastPitch` | Get the last pitch for a list of games | 🔒 實測需 Okta (401) |
| GET | `/api/v1/analytics/guids` | Get the GUIDs (plays) for a specific game. | 🔒 實測需 Okta (401) |
| GET | `/api/v1/analytics/game` | Get all games by updated date. | 🔒 實測需 Okta (401) |

---

## 五、建議後續評估納入的公開 Endpoint

以下皆不需 Okta 登入，且目前本專案尚未使用，依相關性排序：

| Endpoint | 可能用途 |
|---|---|
| `GET /game/{gamePk}/withMetrics`（🟢 實測公開） | 目前沒用過，值得研究是否比 `feed/live` 多出有用的 context metrics |
| `GET /people/{personId}/awards` | 直接查球員得獎紀錄，比全聯盟 `/awards` 更精準地標註「本球員拿過什麼獎」 |
| `GET /stats/leaders`（🟢 實測公開） | 可顯示追蹤球員在聯盟排名（如「打擊率排全聯盟第 X」） |
| `GET /transactions`（🟢 實測公開） | 全聯盟交易/名單異動 feed，可查特定日期/球隊範圍，比目前只靠 `hydrate=transactions` 抓單一球員更彈性 |
| `GET /standings` | 加上球員所屬球隊的戰績/排名脈絡 |
| `GET /teams/{teamId}/roster/{rosterType}` | 可指定 `rosterType`（40man/active/fullSeason），判斷球員是否在 40 人名單 |
| `GET /schedule/postseason` 及子項 | 球員晉級季後賽時的賽程/轉播資訊 |
| `GET /game/{gamePk}/content` | 比賽相關媒體（精華片段影片），可在球員頁嵌入代表作影片 |
| `GET /draft`、`/draft/{year}` | 若新增選秀新秀球員，可自動帶出輪次/順位 |
| `GET /people/{personId}/stats/game/{gamePk}` | 單場比賽數據的替代/更直接查詢方式（目前靠 gameLog） |

---

## 六、非 MLB Stats API 的輔助資源（實測結果）

以下資源來自 `Google_Cloud_x_MLB(TM)_Hackathon_Exploring_MLB_Provided_Datasets.ipynb`，皆不屬於 `statsapi.mlb.com`，因此未收錄在上方的 endpoint 目錄中。用 `curl` 逐一實測後歸類如下。

### 可用

| 資源 | URL 樣式 | 說明 | 存取狀態 |
|---|---|---|---|
| 球隊隊徽 SVG | `https://www.mlbstatic.com/team-logos/{teamId}.svg` | 球隊 Logo 向量圖 | 🟢 實測公開 (200) |
| 球員大頭照（舊路徑） | `https://securea.mlb.com/mlb/images/players/head_shot/{mlb_id}.jpg` | 經兩層 301 導向，最終落在 `img.mlbstatic.com/mlb-photos/image/upload/.../people/{mlb_id}/headshot/67/current`——與本專案 `site_builder/render/urls.py` 現用的 headshot CDN 是同一套，只是轉檔參數不同（例如 `w_213,d_people:generic:headshot:silo:current.png` vs 專案的 `w_180,q_auto:best`），故無需另外串接 |
| MLB Film Room 影片搜尋頁 | `https://www.mlb.com/video/search?q=playid="{playId}"` | 用 playId 組出影片搜尋結果頁，回傳給人看的 HTML（非 JSON API），301 導向 `/video/?q=...` | 🟢 實測可用 (301→200) |
| MLB.com 內容連結 | `https://www.mlb.com/news/{slug}` 或 `https://www.mlb.com/video/{slug}` | 用 fan-content 資料的 slug 組出文章/影片頁連結 | 🟢 實測公開 (200) |

### 不可用（Hackathon 專屬資料集，匿名存取已收回）

| 資源 | URL 樣式 | 存取狀態 |
|---|---|---|
| 全壘打影片資料集 CSV（2016 / 2017 / 2024 / 2024 季後賽） | `storage.googleapis.com/gcp-mlb-hackathon-2025/datasets/{year}-mlb-homeruns.csv` | ❌ 實測 403 `AccessDenied` |
| 球迷最愛／追蹤 JSON | `.../datasets/mlb-fan-content-interaction-data/2025-mlb-fan-favs-follows.json` | ❌ 實測 403 `AccessDenied` |
| 球迷內容互動 JSON（多分片） | `.../datasets/mlb-fan-content-interaction-data/mlb-fan-content-interaction-data-*.json` | ❌ 實測 403 `AccessDenied` |
| 轉播字幕 JSON（13 個分片） | `.../datasets/mlb-caption-data/mlb-captions-data-*.json` | ❌ 實測 403 `AccessDenied` |

> 這 4 類資料集原本是 Google Cloud x MLB Hackathon（2025）活動期間提供的公開 GCS bucket（`gcp-mlb-hackathon-2025`），實測回應為 `Anonymous caller does not have storage.objects.get access`，判斷是活動結束後收回了匿名讀取權限。notebook 中對應的範例程式碼目前已無法直接執行，若要使用需另外取得授權存取。

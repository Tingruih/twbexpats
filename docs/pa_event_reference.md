# `pa_event` 所有可能值對照表

## 背景

`pa_event` 是 `site_builder/sync/extract.py` 從 MLB Stats API play-by-play 的
`result.eventType` 欄位擷取而來（見 `extract.py:243`、`extract.py:389`），
只在該球是打席（PA）最後一球（`is_pa_final`）時才寫入，其餘球為空字串。
下游用途：

- `site_builder/stats/core/pa_outcomes.py` — 判斷 wOBA / PA 計數
- `site_builder/stats/batted_ball/hr_fb.py` — 判斷是否為全壘打
- `site_builder/stats/discipline/put_away.py` — 判斷是否為三振
- `site_builder/render/pitch_log.py` — 逐球紀錄頁顯示用（目前直接輸出英文 code 對應的
  `pa_event_desc`，即 `result.event` 的原文描述，尚未做中文化）

程式碼中目前只手動列舉了兩個子集：

- `WOBA_EVENT_MAP`（`site_builder/constants.py:136`）：計入 wOBA 的 6 種打席結果
- `NON_PA_EVENTS`（`site_builder/constants.py:153`）：11 種「跑壘/場上事件」需從打者
  wOBA/AB/PA 中排除

`pa_event` 完整合法值清單並未在本專案中定義，而是 MLB Stats API 的固定 enum。
可透過官方 meta 端點取得權威清單：

```
GET https://statsapi.mlb.com/api/v1/eventTypes
```

以下為 2026-07-30 查詢當下抓到的完整清單（共 74 筆），供之後做 `pa_event_desc`
中文化／pitch log 顯示對照使用。`plateAppearance` 欄位標示該事件是否會結束一個打席
（也就是是否可能出現在 `pa_event`／`pa_event_desc` 欄位）；`baseRunningEvent` 標示
是否為跑壘類事件。

## PA 結束事件（`plateAppearance = true`）

| code | 官方描述 (`description`) | 建議中譯 |
|---|---|---|
| single | Single | 一壘安打 |
| double | Double | 二壘安打 |
| triple | Triple | 三壘安打 |
| home_run | Home Run | 全壘打 |
| walk | Walk | 保送 |
| intent_walk | Intent Walk | 故意四壞保送 |
| hit_by_pitch | Hit By Pitch | 觸身球 |
| field_out | Field Out | 出局（野手處理） |
| force_out | Forceout | 封殺出局 |
| fielders_choice | Fielders Choice | 野手選擇 |
| fielders_choice_out | Fielders Choice Out | 野手選擇出局 |
| double_play | Double Play | 雙殺 |
| grounded_into_double_play | Grounded Into DP | 滾地球雙殺 |
| triple_play | Triple Play | 三殺 |
| strikeout | Strikeout | 三振 |
| strike_out | Strike Out | 三振（同義字，另一種拼法） |
| strikeout_double_play | Strikeout Double Play | 三振雙殺 |
| strikeout_triple_play | Strikeout Triple Play | 三振三殺 |
| sac_fly | Sac Fly | 犧牲高飛球 |
| sac_fly_double_play | Sac Fly Double Play | 犧牲高飛雙殺 |
| sac_bunt | Sac Bunt | 犧牲觸擊 |
| sac_bunt_double_play | Sac Bunt Double Play | 犧牲觸擊雙殺 |
| field_error | Field Error | 守備失誤上壘 |
| catcher_interf | Catcher Interference | 捕手妨礙打擊 |
| batter_interference | Batter Interference | 打者妨礙守備 |
| fan_interference | Fan Interference | 觀眾妨礙比賽 |
| os_ruling_pending_primary | Official Scorer Ruling Pending | 官方記錄官裁決中（打席結果待定） |

## 非打席結束事件（跑壘/場上事件，`plateAppearance = false`）

| code | 官方描述 | 建議中譯 |
|---|---|---|
| pickoff_1b / pickoff_2b / pickoff_3b | Pickoff 1B/2B/3B | 牽制觸殺出局（一/二/三壘） |
| pickoff_error_1b / pickoff_error_2b / pickoff_error_3b | Pickoff Error | 牽制傳球失誤 |
| pickoff_caught_stealing_2b / _3b / _home | Pickoff Caught Stealing | 牽制後盜壘遭觸殺 |
| caught_stealing / caught_stealing_2b / _3b / _home | Caught Stealing | 盜壘遭刺殺（本/二/三壘） |
| cs_double_play | Cs Double Play | 盜壘遭刺殺雙殺 |
| stolen_base / stolen_base_2b / _3b / _home | Stolen Base | 盜壘成功 |
| wild_pitch | Wild Pitch | 暴投 |
| passed_ball | Passed Ball | 捕逸 |
| balk | Balk | 犯規（投手投球違例） |
| forced_balk | Disengagement Violation | 脫離投手板違例（時鐘/牽制次數規則） |
| error | Error | 失誤 |
| defensive_indiff | Defensive Indiff | 防守漠視（不阻止盜壘） |
| other_advance | Other Advance | 其他進壘 |
| other_out | Runner Out | 其他跑者出局 |
| runner_interference | Runner Interference | 跑者妨礙守備 |
| fielder_interference | Fielder Interference | 野手妨礙跑者 |
| runner_double_play | Runner Double Play | 跑者雙殺 |
| runner_placed | Runner Placed On Base | 跑者被安置上壘（延長賽制） |
| grounded_into_triple_play | Grounded Into TP | 滾地球三殺 |

## 場面/行政類事件（非比賽結果）

| code | 官方描述 | 建議中譯 |
|---|---|---|
| at_bat_start | At Bat Start | 打席開始 |
| batter_turn | Batter Turn | 換打者上場 |
| batter_timeout | Batter Timeout | 打者請求暫停 |
| no_pitch | No Pitch | 無投球紀錄 |
| pitcher_step_off | Pitcher Step Off | 投手下投手板 |
| mound_visit | Mound Visit | 投手丘會議 |
| injury | Injury | 傷停 |
| ejection | Ejection | 驅逐出場 |
| game_advisory | Game Advisory | 比賽注意事項（如天候延賽提示） |
| pitching_substitution | Pitching Substitution | 投手替換 |
| pitcher_switch | Pitcher Switch | 投手變更 |
| offensive_substitution | Offensive Substitution | 攻方換人（代打/代跑） |
| defensive_substitution | Defensive Sub | 守方換人 |
| defensive_switch | Defensive Switch | 守備位置調整 |
| umpire_substitution | Umpire Substitution | 裁判替換 |
| os_ruling_pending_prior | Official Scorer Ruling Pending | 官方記錄官裁決中（非打席結束） |

## 注意事項

- `field_out` 等 code 在 API 回應中還有更細的 `description`／`event` 文字（例如
  `Groundout`、`Flyout`、`Lineout`、`Popout`），那些是 `result.event`（本專案存成
  `pa_event_desc`），跟 `pa_event`（`result.eventType`，較粗略的分類 code）是兩個不同
  欄位，中文化時要注意對應到正確的來源欄位。
- 上表為 2026-07-30 對官方 meta 端點的快照，MLB 可能新增/調整 code，日後若要做成
  程式內建常數表，建議實作時重新查詢 `https://statsapi.mlb.com/api/v1/eventTypes`
  以取得最新版本，而非直接照抄本文件。

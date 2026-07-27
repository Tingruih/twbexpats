# MLB Stats API：`GET /stats/leaders` 各聯盟層級可比數據項調查（PR 值功能可行性）

調查時間：2026-07-27 Asia/Taipei。
依據來源：

- 本機 OpenAPI spec：[MLB-StatsAPI-Spec.json](MLB-StatsAPI-Spec.json)（`paths./api/v1/stats/leaders`、`components.schemas.PersonLeadersEnum`/`StatGroup`/`PlayerPoolEnum`/`StatType`/`GameTypeEnum`）
- 實測只讀請求：`https://statsapi.mlb.com/api/v1/stats/leaders?leaderCategories=...&season=2025&sportId={1,11,12,13,14,16}&statGroup={hitting,pitching,fielding}&playerPool=all&limit=1`（70 種 `leaderCategories` 全數批次查詢，逐層級、逐 statGroup 各打一次，取 `totalSplits` 判斷該類別在該層級是否有資料）
- 實測只讀請求：`https://statsapi.mlb.com/api/v1/leagueLeaderTypes`（列出全部合法 `leaderCategories`）
- 實測只讀請求：分頁 `offset`/`limit`、`playerPool=all|qualified`、`statType=career`、`leaderGameTypes=P` 等參數變化
- 對照本專案目前渲染的欄位：`src/templates/tabs/tab_stats.j2`、`tab_advanced.j2`、`tab_fielding.j2`（及 mobile 對應版本）與 `site_builder/stats/**`

## 結論摘要

1. **端點完全公開可行**（🟢 免登入），且官方直接附帶 `rank`（並列名次制）與 `totalSplits`（母體人數），可以不必自己重算排名，直接用 `PR = round((totalSplits - rank + 1) / totalSplits * 100)` 算百分位，口徑與 MLB.com 官方排行榜一致。
2. **6 個追蹤層級（MLB/AAA/AA/High-A/Single-A/Rookie）都支援同一組傳統數據排行榜**，資料量隨層級遞增（層級越低、名單流動越大、母體越大——這是正常現象，不是 bug）。
3. **本專案網站目前顯示的「基礎/傳統」欄位，八成以上可以直接對到這個 endpoint 的 `leaderCategories`**，不需要額外運算就能加 PR 徽章（詳見下方對照表）。
4. **本專案自算的進階/Statcast 指標（FIP、wOBA、xwOBA、wRC+、WAR、Barrel%、EV、LA、Plate Discipline、球種數據等）完全不在這 70 種官方類別裡**——這個 endpoint 幫不上忙，要做這些指標的 PR 值必須自己建立聯盟分佈（且目前 DB 只收錄追蹤的台灣球員，沒有全聯盟 Statcast 母體，等於要另外開一條資料蒐集管線，成本很高，建議先不做）。
5. 已知 API 端瑕疵：`flyouts`／`pickoffs`（hitting group）、`outfieldAssists`（fielding group）三個類別在**所有層級**都回傳 `totalSplits=0`，屬 MLB 官方 API 本身沒有餵資料，非查詢方式問題，應直接排除不用。

---

## 一、端點與關鍵參數（來自 OpenAPI spec + 實測驗證）

`GET /api/v1/stats/leaders`

| 參數 | 型態 | 說明 / 實測結果 |
|---|---|---|
| `leaderCategories` | array（`PersonLeadersEnum`，共 70 個合法值） | 可一次帶多個類別批次查詢（實測 10 個一次成功；70 個一次批次查詢也成功，只是伺服器有時對 `fielding` 的大批次會逾時，需要重試或拆小批次，見「已知限制」）。查詢時對不屬於該 `statGroup` 的類別會被**靜默忽略**（不報錯，回應中就是不出現）。 |
| `statGroup` | enum：`hitting`/`pitching`/`fielding`（另有 `catching`/`running`/`game`/`team`/`streak`，未測試對球員排行是否有效） | 建議明帶，否則同一 category（如 `battingAverage`）會把打者與投手（有打擊紀錄時）兩組排行都回傳，容易誤用。 |
| `sportId` | integer | `1`=MLB、`11`=AAA、`12`=AA、`13`=High-A、`14`=Single-A、`16`=Rookie（含短季/complex 聯盟，母體最大）。實測 6 個層級皆可正常查詢。 |
| `season` | string | 年度篩選，如 `2025`。 |
| `playerPool` | enum：`ALL`/`QUALIFIED`/`ROOKIES`/`QUALIFIED_ROOKIES`/`ORGANIZATION`/`ORGANIZATION_NO_MLB`/`CURRENT`/`ALL_CURRENT`/`QUALIFIED_CURRENT`（其他值回 400） | **對 PR 功能非常關鍵**：率值型類別（打擊率、OBP、ERA、WHIP…）預設走接近 `QUALIFIED` 的門檻（母體小，如 MLB 打擊率僅 145 人），追蹤的台灣球員很多打席/局數不到門檻會查不到。**建議一律明帶 `playerPool=all`**，實測打擊率母體會從 145 人擴大到 765 人（含所有有打席紀錄的球員）。 |
| `limit` / `offset` | integer | 單頁上限固定 **100 筆**（帶再大的 `limit` 也只回 100），但 `offset` 分頁正常運作（實測 `offset=700` 仍能撈到第 765 名），可分頁撈出完整母體或找到特定球員的名次。 |
| `statType` | enum（`StatType`，含 `SEASON`/`CAREER` 等） | 實測 `statType=career` 可正常回傳生涯排行（如 HR 生涯王 Barry Bonds 762 支）。 |
| `leaderGameTypes` | enum（`GameTypeEnum`） | 實測 `leaderGameTypes=P`（季後賽）正常回傳；預設為 `REGULAR_SEASON`。 |
| `teamId`/`teamIds`/`leagueId`/`leagueIds`/`position`/`playerActive` | — | spec 有列，本次未逐一實測，供未來需要「限定球隊/聯盟/守備位置/在役球員」篩選時參考。 |

### 回傳結構重點

- `leagueLeaders[]`：每個 `leaderCategory` 一組，內含：
  - `leaders[]`：每筆含 `rank`（**並列名次制**，同值球員共享名次，如 1,2,2,4）、`value`、`person.id`/`fullName`、`team`、`league`、`sport`
  - `totalSplits`：符合查詢條件（含 `playerPool` 篩選後）的母體總人數——**PR 分母就用這個**
  - `statGroup`：實際所屬群組

---

## 二、各聯盟層級可比數據項總表

以下為 `season=2025`、`playerPool=all` 實測結果。表格數字＝該層級/該群組下的 `totalSplits`（有紀錄的球員數，數字越大代表母體越大，PR 越有統計意義）；`0` 代表 API 本身無資料（不可用）；`⚠️逾時` 代表該格實測多次逾時，需另外重試/拆批。

層級對照：MLB=1｜AAA=11｜AA=12｜High-A=13｜Single-A=14｜Rookie=16（含短季/complex 聯盟，因此母體常常最大）

### Hitting（打擊，共 29 個有效類別，`flyouts`/`pickoffs` 全層級皆 0，已剔除）

| 類別 | MLB | AAA | AA | High-A | Single-A | Rookie |
|---|---:|---:|---:|---:|---:|---:|
| atBats | 673 | 895 | 762 | 778 | 912 | 1546 |
| battingAverage | 765 | 920 | 772 | 789 | 922 | 1579 |
| caughtStealing | 362 | 463 | 452 | 486 | 546 | 986 |
| doubles | 585 | 772 | 655 | 676 | 778 | 1324 |
| extraBaseHits | 602 | 813 | 680 | 711 | 809 | 1389 |
| gamesPlayed | 765 | 920 | 772 | 789 | 922 | 1579 |
| groundIntoDoublePlays | 537 | 659 | 584 | 581 | 640 | 1052 |
| groundOuts | 658 | 863 | 744 | 763 | 901 | 1506 |
| groundoutToFlyoutRatio | 663 | 875 | 758 | 772 | 909 | 1535 |
| hitByPitches | 471 | 588 | 555 | 593 | 671 | 1193 |
| hits | 650 | 864 | 734 | 756 | 888 | 1506 |
| homeRuns | 522 | 710 | 560 | 559 | 578 | 865 |
| intentionalWalks | 197 | 147 | 103 | 106 | 66 | 92 |
| numberOfPitches | 673 | 895 | 762 | 778 | 912 | 1547 |
| onBasePercentage | 765 | 920 | 772 | 789 | 922 | 1579 |
| onBasePlusSlugging | 765 | 920 | 772 | 789 | 922 | 1579 |
| runs | 631 | 842 | 721 | 741 | 878 | 1491 |
| runsBattedIn | 618 | 820 | 698 | 731 | 852 | 1453 |
| sacrificeBunts | 238 | 236 | 240 | 193 | 228 | 290 |
| sacrificeFlies | 435 | 543 | 478 | 480 | 507 | 877 |
| sluggingPercentage | 765 | 920 | 772 | 789 | 922 | 1579 |
| stolenBasePercentage | 505 | 644 | 596 | 634 | 727 | 1274 |
| stolenBases | 469 | 597 | 562 | 597 | 688 | 1187 |
| strikeouts | 666 | 876 | 753 | 772 | 903 | 1507 |
| totalBases | 650 | 864 | 734 | 756 | 888 | 1506 |
| totalPlateAppearances | 673 | 895 | 762 | 778 | 912 | 1547 |
| triples | 289 | 405 | 354 | 379 | 416 | 702 |
| walks | 615 | 818 | 719 | 746 | 866 | 1478 |

### Pitching（投球，共 47 個有效類別）

| 類別 | MLB | AAA | AA | High-A | Single-A | Rookie |
|---|---:|---:|---:|---:|---:|---:|
| airOuts | 866 | 1242 | 998 | 1020 | 1171 | 1901 |
| balk | 134 | 248 | 280 | 365 | 416 | 716 |
| battingAverage（被打擊率） | 873 | 1264 | 1017 | 1040 | 1223 | 1981 |
| blownSaves | 260 | 441 | 356 | 331 | 365 | 543 |
| caughtStealing | 440 | 625 | 578 | 622 | 704 | 1193 |
| completeGames | 26 | 15 | 22 | 19 | 5 | 14 |
| doubles | 777 | 1066 | 853 | 861 | 956 | 1556 |
| earnedRun | 827 | 1172 | 923 | 944 | 1070 | 1756 |
| earnedRunAverage | 873 | 1264 | 1017 | 1040 | 1222 | 1981 |
| gamesFinished | 626 | 778 | 627 | 664 | 740 | 1239 |
| gamesPlayed | 873 | 1264 | 1017 | 1040 | 1223 | 1981 |
| gamesStarted | 369 | 652 | 480 | 471 | 549 | 1040 |
| groundIntoDoublePlays | 651 | 879 | 727 | 697 | 753 | 1168 |
| groundOuts | 850 | 1218 | 989 | 1008 | 1173 | 1895 |
| groundoutToFlyoutRatio | 872 | 1258 | 1015 | 1035 | 1212 | 1963 |
| hitBatsman | 586 | 769 | 663 | 729 | 792 | 1401 |
| hits | 858 | 1236 | 987 | 1007 | 1163 | 1893 |
| hitsPer9Inn | 873 | 1262 | 1016 | 1040 | 1220 | 1978 |
| holds | 364 | 589 | 480 | 442 | 449 | 546 |
| homeRuns | 743 | 981 | 751 | 719 | 725 | 1018 |
| inningsPitched | 873 | 1262 | 1016 | 1040 | 1220 | 1978 |
| intentionalWalks | 305 | 149 | 94 | 107 | 62 | 89 |
| losses | 594 | 822 | 679 | 673 | 735 | 1175 |
| numberOfPitches | 873 | 1264 | 1017 | 1040 | 1223 | 1981 |
| onBasePercentage（被 OBP） | 873 | 1264 | 1017 | 1040 | 1223 | 1981 |
| onBasePlusSlugging（被 OPS） | 873 | 1264 | 1017 | 1040 | 1223 | 1981 |
| pickoffs | 197 | 264 | 278 | 270 | 313 | 453 |
| pitchesPerInning | 873 | 1262 | 1016 | 1040 | 1220 | 1978 |
| runs | 829 | 1184 | 935 | 953 | 1088 | 1792 |
| saveOpportunities | 323 | 568 | 458 | 470 | 520 | 782 |
| saves | 215 | 375 | 329 | 350 | 376 | 510 |
| shutouts | 13 | 6 | 7 | 9 | 2 | 8 |
| sluggingPercentage（被 SLG） | 873 | 1264 | 1017 | 1040 | 1223 | 1981 |
| stolenBasePercentage | 667 | 1006 | 826 | 905 | 996 | 1663 |
| stolenBases | 627 | 960 | 794 | 863 | 955 | 1584 |
| strikeoutWalkRatio | 839 | 1236 | 994 | 1010 | 1193 | 1945 |
| strikeouts | 808 | 1189 | 974 | 994 | 1169 | 1900 |
| strikeoutsPer9Inn | 873 | 1262 | 1016 | 1040 | 1220 | 1978 |
| totalBases | 858 | 1236 | 987 | 1007 | 1163 | 1893 |
| totalBattersFaced | 873 | 1264 | 1017 | 1040 | 1223 | 1981 |
| triples | 344 | 509 | 436 | 433 | 487 | 873 |
| walks | 823 | 1195 | 946 | 967 | 1109 | 1818 |
| walksAndHitsPerInningPitched | 873 | 1264 | 1017 | 1040 | 1223 | 1981 |
| walksPer9Inn | 873 | 1262 | 1016 | 1040 | 1220 | 1978 |
| wildPitch | 534 | 761 | 704 | 750 | 858 | 1528 |
| winPercentage | 660 | 981 | 805 | 836 | 900 | 1522 |
| wins | 558 | 783 | 675 | 689 | 718 | 1133 |

### Fielding（守備，共 20 個有效類別，`outfieldAssists` 全層級皆 0，已剔除）

| 類別 | MLB | AAA | AA | High-A | Single-A | Rookie |
|---|---:|---:|---:|---:|---:|---:|
| assists | 1585 | 2386 | 2017 | 2031 | 2324 | 3722 |
| catcherEarnedRunAverage | 111 | 181 | ⚠️逾時（見下方限制） | 166 | 185 | 352 |
| catchersInterference | 51 | 54 | 65 | 55 | 55 | 49 |
| caughtStealing | 91 | 148 | 139 | 145 | 164 | 308 |
| chances | 2063 | 3122 | 2510 | 2567 | 2957 | 4899 |
| doublePlays | 870 | 1288 | 1045 | 1056 | 1169 | 1862 |
| errors | 885 | 1346 | 1184 | 1254 | 1489 | 2519 |
| fieldingPercentage | 2708 | 4112 | 3310 | 3392 | 3966 | 6721 |
| gamesPlayed | 2708 | 4112 | 3310 | 3392 | 3966 | 6721 |
| gamesStarted | 1911 | 3375 | 2699 | 2745 | 3199 | 5498 |
| innings | 2297 | 3448 | 2725 | 2797 | 3280 | 5551 |
| passedBalls | 70 | 125 | 117 | 121 | 144 | 261 |
| putOuts | 1905 | 2822 | 2278 | 2284 | 2591 | 4241 |
| rangeFactorPer9Inn | 2297 | 3448 | 2725 | 2797 | 3280 | 5551 |
| rangeFactorPerGame | 2708 | 4112 | 3310 | 3392 | 3966 | 6721 |
| stolenBasePercentage | 102 | 171 | 156 | 163 | 185 | 340 |
| stolenBases | 102 | 169 | 155 | 161 | 183 | 337 |
| throwingErrors | 614 | 892 | 813 | 879 | 1075 | 1874 |
| triplePlays | 7 | 12 | 6 | 7 | 8 | 18 |
| wildPitch | 98 | 162 | 149 | 152 | 178 | 338 |

---

## 三、對照本專案網站現有欄位：哪些可以直接套用 PR 值

網站目前欄位盤點依據：`tab_stats.j2`（基本）、`tab_advanced.j2`（進階）、`tab_fielding.j2`（守備），以及 `site_builder/stats/**` 的資料來源判定。

### ✅ 可直接對應、無需額外運算即可加 PR 徽章

| 網站欄位 | 對應 `leaderCategories` | 備註 |
|---|---|---|
| **打擊** PA / AB / R / RBI / H / 2B / 3B / HR / SB / CS / BB / SO | totalPlateAppearances / atBats / runs / runsBattedIn / hits / doubles / triples / homeRuns / stolenBases / caughtStealing / walks / strikeouts | 逐一對應 |
| AVG / OBP / SLG / OPS | battingAverage / onBasePercentage / sluggingPercentage / onBasePlusSlugging | 逐一對應 |
| XBH / GIDP / SF / SH / IBB / HBP | extraBaseHits / groundIntoDoublePlays / sacrificeFlies / sacrificeBunts / intentionalWalks / hitByPitches | 逐一對應 |
| GO/AO | groundoutToFlyoutRatio | 直接就是同一個比率，不用自己除 |
| SB% | stolenBasePercentage | 逐一對應 |
| **投球** W / L / GS / SV / HLD / IP / BF / H / ER / HR / BB / SO | wins / losses / gamesStarted / saves / holds / inningsPitched / totalBattersFaced / hits / earnedRun / homeRuns / walks / strikeouts | 逐一對應 |
| ERA / WHIP / K/9 / BB/9 / H/9 / K/BB | earnedRunAverage / walksAndHitsPerInningPitched / strikeoutsPer9Inn / walksPer9Inn / hitsPer9Inn / strikeoutWalkRatio | 逐一對應 |
| 被 AVG / 被 OBP / 被 SLG / 被 OPS | battingAverage / onBasePercentage / sluggingPercentage / onBasePlusSlugging（`statGroup=pitching`） | 用 pitching group 查同名類別即可 |
| Win% | winPercentage | 逐一對應 |
| IBB（投手） | intentionalWalks（`statGroup=pitching`） | 逐一對應 |
| GO/AO（投手） | groundoutToFlyoutRatio（`statGroup=pitching`） | 逐一對應 |
| **守備** PO / A / E / TC / DP / TP / FLD% / RF/G / RF/9 / TE / GP / GS / INN | putOuts / assists / errors / chances / doublePlays / triplePlays / fieldingPercentage / rangeFactorPerGame / rangeFactorPer9Inn / throwingErrors / gamesPlayed / gamesStarted / innings | 逐一對應 |

**小結**：網站目前顯示的「基礎數據」與大半「進階但仍屬計數/比率型」欄位（約 45 個欄位）都能直接用這個 endpoint 做 PR 值，完全符合「只用 statsapi.mlb.com」的資料來源政策，不需要額外運算或另建母體。

### 🟡 endpoint 有提供、但網站目前沒顯示的欄位（可視需求擴充）

`balk`（暴投犯規）、`blownSaves`（救援失敗）、`completeGames`（完投）、`gamesFinished`（終結場次）、`saveOpportunities`（救援機會）、`shutouts`（完封）、`wildPitch`（投手/捕手端暴投）、`passedBalls`（捕手漏接）、`pickoffs`（牽制成功，投手端）、`catchersInterference`（捕手妨礙打擊）——這些若之後想加到球員頁，直接可用。

### ❌ 網站有、但這個 endpoint 完全沒有、無法靠它做 PR 值的欄位

以下都是本專案**自行計算**的進階/Statcast 指標（見 `site_builder/stats/advanced/`、`stats/discipline/`、`stats/batted_ball/`），不在 `leagueLeaderTypes` 的 70 個官方類別內：

- **Sabermetrics**：FIP、wOBA、xwOBA、wRC+、WAR、xWPCT、ISO、BABIP、K%、BB%
- **Statcast 品質**：Barrel%、Hard-Hit%、Avg EV、Max EV、EV90、Avg LA、Avg Extension、HR/FB%
- **Plate Discipline**：Zone%、Z-Swing%、O-Swing%、Z-Contact%、Swing%、Whiff%、CSW%、SwStr%、PutAway%
- **擊球型態**：GB%/LD%/FB%/PU%/Air%/Pull%/Straight%/Oppo%/PullAir%
- **球種數據（Arsenal）**：Velo、iVB、HB、Spin、vRel、hRel 等對球種細分數據

原因：這些是 Statcast 逐球資料聚合出來的自算指標，MLB Stats API 官方排行榜端點只服務傳統 box score 統計，不含這些衍生指標。要做這些指標的 PR 值，必須自己在全聯盟範圍收集同等的 Statcast pitch-level 資料並建立分佈——但本專案 DB 目前只收錄「追蹤的台灣球員」，沒有全聯盟母體，等於要另開一條大型資料蒐集管線（且 MiLB 場次多半沒有 Statcast 覆蓋，`CLAUDE.md` 已註明此限制）。**建議 PR 值功能第一階段只涵蓋上表「✅ 可直接對應」的傳統欄位，進階指標的 PR 值列為之後可評估的獨立專案。**

---

## 四、建議實作方式

1. **批次查詢**：每個 `(sportId, statGroup, season)` 組合用一次多 `leaderCategories` 的批次呼叫（`playerPool=all`），減少 request 數（實測 10～20 個類別一次沒問題；`fielding` 類別較多時偶爾逾時，建議拆成 5 個一批較穩，並加重試邏輯）。
2. **找出追蹤球員的名次**：解析回傳的 `leaders[]`，用 `person.id` 比對追蹤球員的 MLB ID。若球員名次超過第一頁（`limit` 上限 100），用 `offset` 遞增（100, 200, …）續抓，直到在清單裡找到該球員，或抓完 `totalSplits` 頁數仍找不到（代表該球員本季在這個類別完全沒有紀錄，例如投手沒有守備數據）。
3. **PR 值公式**：`PR = round((totalSplits - rank + 1) / totalSplits * 100)`。因為 `rank` 是並列名次制（tie 共享名次），同數值的球員會拿到相同 PR，符合直覺。
4. **`playerPool=all` 是必要條件**：追蹤的台灣球員很多打席/局數不到官方「合格」門檻（如打擊王、防禦率王門檻），不帶 `all` 會直接查不到人。
5. **層級要對齊球員當下所在的層級**：`sportId` 要跟球員該季實際出賽的層級一致（MLB/AAA/AA/High-A/Single-A/Rookie），不要混層級比較，否則 PR 沒有意義。

---

## 五、已知限制 / 注意事項

- **`flyouts`、`pickoffs`（hitting group）、`outfieldAssists`（fielding group）三個類別在全部 6 個層級都回傳 `totalSplits=0`**，屬 MLB 官方 API 本身沒有餵資料（enum 裡列了但沒有實際資料源），應直接排除，不要浪費 request。
- **AA（sportId=12）查 `catcherEarnedRunAverage`（fielding group）多次實測皆逾時**（`messageNumber:13 "Operation taking longer than expected"`），其他層級同一類別都正常。這是個別 (層級, 類別) 組合的伺服器端不穩定案例，不是資料不存在；實作時對這類冷門類別要有 timeout + skip 的容錯機制，不要因單一類別逾時卡住整個批次。
- **單頁 `limit` 上限固定 100**，务必搭配 `offset` 分頁才能拿到完整母體或找到排名較後面的球員。
- **`rank` 是並列名次制**，不是資料列的序號位置——用 `rank` 直接算 PR 比自己數第幾筆位置更準確也更省事。
- **沒有可以「直接查某位球員排第幾名」的參數**（沒有 `playerId` 篩選），只能撈排行榜清單自己比對，找不到球員時代表他在該類別本季沒有累積到任何一筆數據（比較常見於 pitchers 的 hitting 類別，或 hitters 的 fielding 類別）。
- **只有 Regular Season（`R`，預設）與 Postseason（`P`）可選**，無法查特定日期區間或滾動區間（例如「近 30 天」）的排行；若要做「近況 PR」需要另外用 `statType=byDateRange` 之類的 `/people/{id}/stats` 端點自己算，這個 leaders 端點不支援。

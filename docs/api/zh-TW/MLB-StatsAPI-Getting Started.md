## 大小寫敏感性（Case Sensitivity）

Stats API 呼叫對大小寫敏感，錯誤的大小寫可能會導致非預期、不正確或空白的回傳結果。Stats API 採用 Lower Camel Case（小駝峰式）命名慣例，將多個單字連接在一起，字串的第一個字母為小寫，後續每個單字的字首則為大寫。

舉例來說，呼叫 https://statsapi.mlb.com/api/v1/divisions?sportId=1&divisionId=200 會回傳美聯西區（AL West）的資訊。

"divisions": [
    {
        "id": 200,
        "name": "American League West",
        "nameShort": "AL West",
        "link": "/api/v1/divisions/200",
        "abbreviation": "ALW",
        "league": {
            "id": 103,
            "link": "/api/v1/league/103"
        },
        "sport": {
            "id": 1,
            "link": "/api/v1/sports/1"
        },
        "hasWildcard": false
    }
]

然而，看似相同的呼叫 https://statsapi.mlb.com/api/v1/divisions?sportId=1&divisionID=200 卻會回傳所有 MLB 分區的資訊，如同沒有指定任何特定的 divisionId 一般。這個呼叫之所以會與第一個不同，原因在於 divisionID=200 中只有「I」被大寫。division Id 的端點只有透過 divisionId（而非 divisionID）才能正確呼叫。

雖然忽略大小寫敏感性會產生與預期不同的呼叫，但並不會導致錯誤回應。若呼叫中只有一部分是錯誤的，Stats API 會忽略該部分，並回傳一個包含所有正確部分的預設呼叫。舉例來說，在錯誤的 "divisionID" 呼叫 https://statsapi.mlb.com/api/v1/divisions?divisionID=200&sportId=1&leagueId=103 中加入正確的 leagueId 後，Stats API 仍會回傳分區

#### 參數（Parameters）

##### 選填／必填參數（Optional / Required Parameters）

參數是在發出更複雜或更具體的請求時，加到基礎網址／端點組合中的額外資訊。參數有兩種類型：$ \underline{\text{選填（Optional）}} $ 與 $ \underline{\text{必填（Required）}} $。Stats API 文件為每個端點提供了哪些參數為必填、哪些為選填的準則。

舉例來說，在以下的 $ \underline{\text{Game-WinProbability}} $ 端點中，gamePk 參數是必填的，因為若沒有它，就沒有可回傳的資訊。Timecode 則是選填參數，讓使用者可以擷取單一時間點的資料快照，而非整場比賽的資料，但由於若省略此參數，系統會回傳完整比賽的資料，因此它並非必填。

## 提示

•  $ \underline{\text{https://statsapi.mlb.com/api/v1/game/531060/winProbability}} $ - 完整比賽

•  $ \underline{\text{https://statsapi.mlb.com/api/v1/game/531060/winProbability?timecode=20180803_182458}} $ - 快照。若參數旁未標示「required（必填）」，則表示該參數為選填。

##### Query 參數 vs Path 參數

Stats API 呼叫可以由 query 參數與／或 path 參數組成。Path 參數以大括號標示，例如 `{gamePk}`。Stats API 中大多數的 path 參數為 `required`（必填），而大多數的 query 參數則為選填。

以下是 $ \underline{Query} $ 參數與 $ \underline{Path} $ 參數的使用範例。雖然 $ \underline{GamePk} $ 作為 path 參數是 $ \underline{必填} $ 的，才能取得回傳結果，但 query 參數只有在需要呼叫特定 $ \underline{timecode} $ 時才需要。若沒有 timecode，該呼叫依然有效，並會回傳整場比賽的資訊。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Path parameter</td><td style='text-align: center; word-wrap: break-word;'>Query parameter</td><td style='text-align: center; word-wrap: break-word;'>Call with path and query parameters</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>game_pk: 531060</td><td style='text-align: center; word-wrap: break-word;'>timecode: 20180803_182458</td><td style='text-align: center; word-wrap: break-word;'>https://statsapi.mlb.com/api/v1/game/531060/boxscore?timecode=20180803_182458</td></tr></table>

## 請求（Requests）

請求是取得存取權並查詢後端資料庫的過程。Stats API 根據使用者的請求擷取資料，就像顧客在餐廳下單、提出「請求」一樣。使用者透過 URL 提出請求，而在請求有效的情況下，Stats API 會以 JSON 格式回傳資料。

#### 基礎網址（Base URL）

首先，大多數 Stats API 呼叫（包括基本比賽資訊與 Statcast 資料）都會透過基礎網址：https://statsapi.mlb.com/api/v1/ 進行。GUMBO 逐球（play-by-play）資料流則可透過 https://statsapi.mlb.com/api/v1.1/ 取得。然而，為了完成有效的請求，必須在基礎呼叫後面加上端點。

為了示範一個有效的請求，以下是使用 Statcast 資料流與 gameTypes 端點的範例：

Stats API 基礎呼叫 - https://statsapi.mlb.com/api/v1/

• Stats API 端點 - gameTypes

##### 範例

有效請求範例 - 上述端點決定了回傳的具體資訊，而基礎呼叫則決定了資訊的擷取來源。有效的請求 URL 可用於瀏覽器中查詢一次性資訊，或編寫進本地程式軟體中，以自動擷取資訊並確保使用者資料庫持續更新。

#### 速率限制（Rate Limiting）

Stats API 的設計可承受大量請求；然而，請求會被限制在每秒 25 次，任何超過此速率的請求都會回傳 429 回應。此限制以每秒為單位計算，即使先前已達到限制，之後幾秒仍可再次發出請求。429 回應是專門保留給 Stats API 超過速率限制時的例外情況。

依其 id 回傳對應聯盟的資訊。關於 API 呼叫正確大小寫的進一步資訊，請參閱相關的 Configs 章節，以確認每個端點的正確大小寫。

## 欄位、上限與位移量（Fields, Limits, and Offsets）

依據特定的請求，Stats API 可能會回傳大量資料。對於某些端點，使用者可以透過三個參數來調整 Stats API 的回傳內容：fields（欄位）、limits（上限）與 offsets（位移量）。

##### Fields（欄位）

使用者可能只想要或只需要回傳中的特定欄位。Stats API 提供 fields 參數，以縮減酬載（payload）並簡化回傳內容，使其只包含使用者所需的欄位。

$ \underline{fields} $ 參數存在於所有 Stats API 端點中。此參數透過從最上層節點（父節點）往下處理至屬性層級的方式，將龐大的請求整合為包含特定資訊的回傳結果。舉例來說，stats 端點的回傳結果，是以包含所有子節點物件、陣列與字串的 JSON stats 物件作為起始。因此，呼叫中的 $ \underline{fields} $ 參數必須包含 stats。最佳實務是讓 $ \underline{fields} $ 參數以父節點 stats 開頭，接著再列出子節點中的其他屬性，以避免混淆。舉例來說，2022 年 MLB 球員呼叫可以透過 $ \underline{fields} $ 參數指定，讓所有項目只回傳 $ \underline{fullName} $ 與 id：https://statsapi.mlb.com/api/v1/sports/1/players?season=2022&fields=people,id,fullName

若要在回傳中包含一個以上的屬性，須將所有屬性的父節點到子節點路徑都納入。然而，若多個欄位屬性共用同一個父節點，則不需要在呼叫中重複列出父節點，只需在 fields 參數中指定一次即可。舉例來說，由於 id 與 fullName 共用同一個父節點 people，該父節點只需呼叫一次，如下所示：http://statsapi.mlb.com/api/v1/sports/1/players?season=2019&fields=people,id,fullName

##### Limit（上限）

有些端點的回傳結果，每次呼叫會限制在一定數量的項目內，以確保 Stats API 的回傳結果不會過於龐大而導致失敗或逾時。具有此類限制的端點，例如 analytics/game 與 analytics/guids，會在 Stats API 文件中特別標示。為了取得更完整的資料集，使用者可以搭配 limit 與 offset 參數發出多次呼叫。

$ \boxed{limit} $ 參數用於從指定端點回傳一部分的紀錄。若只想從 Statcast 最後更新端點回傳 10 場比賽，可傳入 $ \boxed{limit} $ 值為 10。http://statsapi.mlb.com/api/v1/analytics/game?limit=10。

##### Offset（位移量）

$ \text{fields} $ 參數可縮減回傳的酬載，而 $ \text{offset} $ 參數則可搭配 $ \text{limit} $ 參數使用，以回傳特定的一部分資料。$ \text{offset} $ 參數會將 i+1 作為回傳結果中的第一筆紀錄。舉例來說，若不傳入時間戳記，已更新的 Statcast 比賽端點 http://statsapi.mlb.com/api/v1/analytics/game 預設只會回傳最近更新的 1000 場比賽。若要從此端點取得更長的已更新比賽清單，就必須傳入 $ \text{offset} $。透過將 $ \text{offset} $ 設為 1000（http://statsapi.mlb.com/api/v1/analytics/game?offset=1000），Stats API 呼叫將會回傳接下來的 1000 場比賽（第 1001 到 2000 場）。

##### Limit 與 Offset 併用

資料分頁的最佳實務是同時使用 $ \underline{\text{limit}} $ 與 $ \underline{\text{offset}} $：http://statsapi.mlb.com/api/v1/analytics/game?limit=100&?offset=1000。加入 $ \underline{\text{limit}} $ 可讓使用者將 API 的回傳結果限制在適合其解析器（parser）的範圍內，而 $ \underline{\text{offset}} $ 則可確保使用者最終能取得所有可用的資料。

### 預設回應（Default Responses）

在 Stats API 中產生呼叫時，使用者必須注意預設回應。雖然某個呼叫可能是錯誤的，但在某些情況下，Stats API 不會回傳錯誤，而是回傳一個備援的預設回應。在使用者指南「大小寫敏感性」章節中提到，一個簡單的大小寫錯誤就可能導致預設呼叫。有時候，由於結構的長度或架構過於複雜，可能難以辨識出預設回傳結果。在大多數情況下，一個無效的呼叫只會回傳該呼叫在使用各相關端點必填參數時所產生的資訊。Stats API 文件列出了每個端點的必填參數，是辨識預設回傳情況的實用資源。

## 提示

2000 年球季亞利桑那響尾蛇隊（Arizona Diamondbacks）現役名單

• 正確呼叫：$ \underline{\text{https://statsapi.mlb.com/api/v1/teams/109/roster?rosterType=Active}} $

• 導致回退為預設值的錯誤呼叫：https://statsapi.mlb.com/api/v1/teams/109/roster?rosterType=Active&season=20000

在上述範例中，season 參數值的結尾多加了一個「0」。提交此呼叫後，由於「20000」是無效的年份，回傳結果會回退為目前年度的名單（此端點的預設呼叫）。使用者應確認回傳結果提供的是預期的資訊，而不要預期提交無效呼叫時系統會產生錯誤。

例外情況（產生錯誤訊息而非預設回傳的情況）是指在必填參數中包含無效輸入的情況。由於必填參數是產生預設回傳的依據，這些參數中的無效輸入將使整個呼叫失效並產生錯誤。

## 提示

範例：teams 端點搭配必填參數

- 正確呼叫：$ \underline{\text{https://statsapi.mlb.com/api/v1/teams/147/affiliates}} $

• 錯誤呼叫：https://statsapi.mlb.com/api/v1/teams/affiliates

## Stats API 速率限制

##### 速率限制（Rate Limiting）

MLB 對 Stats API 實施速率限制，以確保高效能並防止濫用。請求限制為每秒 25 次，任何超過此速率的請求都會回傳 429 回應。此限制以每秒為單位計算，即使先前已達到限制，之後幾秒仍可再次發出請求。429 回應是專門保留給 Stats API 超過速率限制時的例外情況。

若使用者因錯誤實作 OAuth2 而重複請求新的存取權杖（access token），其帳號可能會遭 MLB 資訊安全部門暫時封鎖。提醒您，存取權杖會快取 60 分鐘，只有在現有權杖過期時才應請求新的權杖。重新整理權杖（Refresh token）除非連續 14 天未使用，否則不會過期。

如有任何問題或疑慮，請聯絡 VideoStatsSupport@mlb.com。

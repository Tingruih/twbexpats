# 逐球影片嵌入可行性研究

本文件記錄「在球員詳細頁 / 逐球紀錄表格裡，讓使用者直接播放對應那顆球的影片」這個功能的
可行性調查：有哪些資料來源、各自的分層覆蓋率與連結穩定性、可能的風險、以及建議的
fallback 設計。**本文件只記錄調查結果與建議方案，尚未實作。**

> 調查方法：用專案 `src/data/roster.json` 內真實球員（鄧愷威 678906、莊陳仲敖 800018）
> 的真實比賽，對 `statsapi.mlb.com`、`baseballsavant.mlb.com`、`sporty-clips.mlb.com`、
> `mlb-cuts-diamond.mlb.com` 實際發 HTTP 請求驗證，不是查文件或猜測慣例。完整指令與
> 回應細節見文末〈調查方法與佐證〉。

---

## 目錄

1. [背景](#一背景)
2. [兩種影片來源總覽](#二兩種影片來源總覽)
3. [分層覆蓋率（重點：只有 MLB 有影片）](#三分層覆蓋率重點只有-mlb-有影片)
4. [連結延遲與穩定性](#四連結延遲與穩定性)
5. [方案比較](#五方案比較)
6. [風險](#六風險)
7. [Fallback 設計](#七fallback-設計)
8. [建議實作路線](#八建議實作路線)
9. [調查方法與佐證](#九調查方法與佐證)

---

## 一、背景

`playId` 是 MLB Stats API 逐球資料裡的 deterministic UUID（v3），目前已經被
`site_builder/sync/extract.py` 抽取進 `game_logs.pitches_json`（欄位 `play_id`），
涵蓋 `isPitch=true` 的投球事件，也涵蓋 `pickoff`/`stepoff` 等非投球但被追蹤系統記錄的動作。
這個 ID 可以拿去對應到影片來源，是本文件討論「看這球」功能的資料基礎——**這部分資料已經
在資料庫裡，不需要額外抓取**。

## 二、兩種影片來源總覽

| 來源 | 端點 | 網域 | 是否在網路白名單 |
|---|---|---|---|
| **A. statsapi content** | `GET /api/v1/game/{gamePk}/content` 的 `highlights.highlights.items[]`，`guid` 欄位若等於某顆球的 `play_id`，該 item 附 `playbacks[]`（`mp4Avc`/`hlsCloud`） | `statsapi.mlb.com`（端點本身）→ 實際影片檔在 `mlb-cuts-diamond.mlb.com` | 端點本身在白名單；影片檔網域不在 |
| **B. Baseball Savant** | `GET /sporty-videos?playId=<uuid>`，回傳 HTML，內嵌 `<video><source src="https://sporty-clips.mlb.com/<token>.mp4">` | `baseballsavant.mlb.com` → 影片檔在 `sporty-clips.mlb.com` | 都不在，需另外放行 |

兩者的根本差異：**A 只收錄「精華等級」的球（全壘打、三振、關鍵守備等，約 65% 覆蓋率，
以 gamePk 777681 為樣本），B 收錄幾乎每一顆被追蹤到的球**（含普通壞球、觸身球），但**只
存在於 MLB 層級**（見下節）。

## 三、分層覆蓋率（重點：只有 MLB 有影片）

實測三個層級，每層都用網站內真實球員的真實比賽：

| 層級 | 測試對象 | `play_id` 格式 | `pitchData` 完整度 | Savant 影片 | statsapi content 精華片段 |
|---|---|---|---|---|---|
| **MLB** | 鄧愷威 678906，2025-08-02 對 Giants（gamePk 776911） | 正規 UUID v3（如 `b339cea8-e12d-340f-adbc-a655fb63aaed`） | 完整（球速、3D 軌跡、轉速、breaks） | ✅ 有，含一般球（實測一顆壞球 `Kai-Wei Teng Ball to Brandon Nimmo`，非精華球也有影片） | ✅ 有（另以 Machado 全壘打為例，gamePk 777681） |
| **AAA** | 鄧愷威 678906，2025-03-29 Sacramento River Cats（gamePk 779812） | 正規 UUID v3，跟 MLB 同規格 | 完整，跟 MLB 同規格（同樣有 `startSpeed`/`pfxX`/`spinRate` 等） | ❌ `No Video Found` | ❌ 該場 `highlights` 為 `None`，零筆 |
| **AA** | 莊陳仲敖 800018，2025-04-06（gamePk 782173） | **非標準格式**（如 `07821736-0016-0013-000c-f08cd117d70a`，結構疑似內嵌 gamePk，不是真的 name-based UUID） | **極簡**（只有好球帶框線 + 2D 落點座標，無球速/轉速/3D 軌跡） | ❌ `No Video Found` | ❌（未見精華片段） |

**結論**：AAA 明明有跟 MLB 完全同規格的 Trackman/Hawkeye 追蹤資料，Savant 卻依然完全沒有
影片——代表**影片是 MLB 專屬的廣播攝影棚產品，不是「有追蹤資料就有影片」**。AA 以下不只沒
影片，連追蹤資料本身都是陽春版（可能連拿來算進階指標的價值都有限，屬於題外話但值得註記）。

**對這個專案的實務意義**：由於追蹤的球員大多數時間待在 MiLB，逐球影片功能只對球員
**在 MLB 出賽期間**的球有意義。UI 必須依 `sport_level` 做條件顯示，AAA 以下完全不該出現
「看這球」按鈕（顯示了也一定是死連結）。

## 四、連結延遲與穩定性

| 來源 | 是否為永久連結 | 已驗證的穩定性證據 |
|---|---|---|
| A（`mlb-cuts-diamond.mlb.com`） | ✅ 是 | 同一 gamePk 重複呼叫 `/content`，兩次拿到位元組完全相同的 URL；header 帶 `x-goog-generation`（GCS 物件版本號），性質上是靜態物件路徑而非簽名連結；無 UA/Referer 檢查，空 UA 也回 200 |
| B（`sporty-clips.mlb.com`） | ⚠️ 短中期穩定，長期未驗證 | 同一 playId 間隔約 3 分鐘重複呼叫 `/sporty-videos`，兩次拿到的 token **完全相同**；頁面本身回 `cache-control: public, max-age=1200, s-maxage=3600`（邊緣快取 1 小時）。行為比較像「deterministic 映射」而非一次性簽名 URL，但**只做了分鐘等級的觀察，未驗證數天/數週後是否依然有效** |

**索引延遲（B 專屬的額外限制）**：測試剛打完隔天的比賽（2026-07-07 賽事，隔日測試），
**所有 playId（含全壘打等精華球）在 Savant 上一律回傳 `No Video Found`**；反觀一個多月前
的比賽（2026-05-31）則正常有影片。代表 Savant 的逐球影片索引**至少有 1 天以上的延遲**，
不是打完球馬上就能查到，剛更新的比賽必須有 fallback 機制。

## 五、方案比較

| 方案 | 做法 | 覆蓋率 | 過期風險 | 落地複雜度 |
|---|---|---|---|---|
| (a) build 時期寫死 A 的 URL | `python build.py refresh` 時打 `/content`，`guid` 比對後把 mp4/m3u8 存進 DB，模板渲染成站內 `<video>` | 只有精華球（~65%，僅 MLB） | 低（已驗證為永久 CDN 路徑） | 低，不涉及外部依賴的即時可用性 |
| (b) 純外部連結 | `<a href="https://baseballsavant.mlb.com/sporty-videos?playId=...">` 開新分頁 | 幾乎全部 MLB 球 | 無（使用者點擊當下才連線，Savant 自己處理內容是否存在） | 最低 |
| (c) client-side fetch 解析 | 前端 JS `fetch()` Savant 頁面、regex 解析 `<source>` 拿到 `sporty-clips` mp4 網址，自建 `<video>` | 幾乎全部 MLB 球 | 依賴 B 的 token 穩定性（未長期驗證）+ 依賴 Savant HTML 結構不變 | 較高，多一層 DOM 解析、對 Savant 改版更脆弱 |
| (d) client-side iframe 嵌入 | 使用者點擊時動態插入 `<iframe src="https://baseballsavant.mlb.com/sporty-videos?playId=...">` | 幾乎全部 MLB 球 | 交給 Savant 自己處理，不解析內容，比 (c) 穩健 | 中，需處理「查無影片」時的偵測與降級 |

已驗證的關鍵前提（讓 (c)/(d) 可行）：
- `sporty-clips.mlb.com` 只檢查 **User-Agent**（擋掉爬蟲慣用的空/預設 UA），**不檢查
  Referer 或 Origin**——真實瀏覽器發出的請求不會被擋，可以直接站內嵌入 `<video src=...>`
  或 `<iframe>`。
- `baseballsavant.mlb.com/sporty-videos` 這個 HTML 頁面本身**開放 CORS**
  （`access-control-allow-origin: *`，OPTIONS preflight 回 204），理論上允許
  `fetch()` 跨來源讀取。
- 該頁面**沒有** `X-Frame-Options` 也沒有 CSP `frame-ancestors`，代表可以直接
  `<iframe>` 嵌入，不會被瀏覽器擋。

## 六、風險

1. **著作權／使用條款不確定性**：MLB Stats API 每個回應都附註
   `Copyright ... L.P. Use of any content on this page acknowledges agreement to the
   terms posted here http://gdx.mlb.com/components/copyright.txt`。本文件只驗證了
   「技術上連得到、播得動」，**沒有法律面確認這些影片資產是否允許被第三方粉絲網站嵌入/轉播**。
   這是需要人為判斷、不是工程能解決的風險，建議正式上線前另外確認條款（尤其是方案 (a)
   把影片網址寫進自己資料庫、方案 (d) 用 iframe 嵌入整頁 Savant 內容，兩者商業/法律風險
   程度不同，(a) 更接近「引用單一片段」，(d) 更接近「嵌入對方完整頁面」）。
2. **外部依賴不受我們控制**：`sporty-clips.mlb.com` 的 Cloudflare UA 檢查規則、Savant 頁面
   的 CORS/X-Frame-Options 設定，都可能在未來任何時間點被 MLB 一方無預警調整或收緊，導致
   方案 (c)/(d) 突然失效。這類外部行為不受我們版本控制，出問題時很難第一時間察覺。
3. **token 長期穩定性未驗證**：只做了 3 分鐘級別的重複請求比對，不能保證數週/數月後同一個
   `playId` 對應的 `sporty-clips` token 依然有效——**方案 (a) 已避開此風險**（只用已驗證
   為永久連結的 A 來源寫入 DB），但如果未來想把 B 的連結也寫死存 DB，需要更長期的觀察。
4. **索引延遲**：Savant 對新比賽至少有 1 天以上的索引延遲，賽後立刻查詢一定會顯示「查無
   影片」，需要明確的 UI 文案與 fallback，避免使用者誤以為功能壞掉。
5. **iframe 嵌入第三方頁面的隱私/追蹤疑慮**：`baseballsavant.mlb.com` 頁面本身可能載入
   MLB 自己的分析/廣告腳本與 cookies，嵌入後等於讓使用者的瀏覽器對 MLB 網域發出請求，
   若網站有隱私權政策，需要一併揭露此第三方內容行為。
6. **層級誤判風險**：如果 UI 邏輯疏漏、對 AAA 以下的球也顯示「看這球」按鈕，使用者點了
   一定得到空白/錯誤結果（AAA 測試 `highlights` 為 `None`，AA 測試同樣查無），必須嚴格
   依 `sport_level` 過濾。

## 七、Fallback 設計

依照第三節的分層覆蓋率結論，UI 邏輯應該分三層處理：

```
sport_level != MLB
  → 完全不顯示「看這球」按鈕（AAA 以下沒有任何影片來源）

sport_level == MLB 且該球是「精華等級」（build 時期已用 statsapi content 的 guid
比對到 mlb-cuts-diamond 永久連結，存在 DB 裡）
  → 直接渲染站內 <video>，最穩定、無延遲疑慮（來源 A）

sport_level == MLB 且該球是「一般球」（沒有精華片段）
  → 顯示「看這球」按鈕，點擊才動態插入 <iframe src="baseballsavant.mlb.com/sporty-videos?playId=...">（來源 B，避免每列都預先載入未使用的 iframe）
  → 需要偵測「查無影片」的情況（例如 iframe onload 後量測內容高度，或設一個
    timeout），偵測到查無內容時，把 iframe 換成文字提示：
    「這場比賽的影片可能還沒上架（通常需要等待至少一天），可改為
    直接前往 Baseball Savant 查看」，並附上方案 (b) 的外部連結作為保底
```

## 八、建議實作路線

1. **第一階段（低風險，可以先做）**：只做精華球的方案 (a)——build 時期用 `guid` 比對
   statsapi content，把 `mlb-cuts-diamond.mlb.com` 的永久連結存進 DB，模板加站內
   `<video>`。資料來源已驗證穩定，不涉及外部網域即時可用性問題，也不需要放行新網域到
   sandbox/CSP 白名單以外的正式環境設定。
2. **第二階段（中風險，待確認法律面後再做）**：一般球的 iframe 版本（方案 (d)），需要
   額外決定：
   - 是否要正式確認 MLB 影片內容的嵌入授權範圍（本文件風險 1）
   - iframe 的「查無影片」偵測邏輯要多保守（避免誤判成功/失敗）
   - 是否要把 `baseballsavant.mlb.com` 加進正式站台的 CSP `frame-src`（如果有設定 CSP）

## 九、調查方法與佐證

以下為本文件結論所依據的實際測試（環境：`statsapi.mlb.com` 在專案 sandbox 網路白名單內，
`baseballsavant.mlb.com`/`sporty-clips.mlb.com`/`mlb-cuts-diamond.mlb.com` 不在白名單，
以下涉及這三個網域的測試皆需 `dangerouslyDisableSandbox: true` 明確取得授權才能連線）：

- **playId 穩定性**：對 gamePk 777681 的 `/api/v1.1/game/{pk}/feed/live` 間隔重複請求，
  324 個帶 `playId` 的事件兩次結果完全一致（`identical playId set: True`）。
- **跨端點一致性**：同一顆球在 `/feed/live` 與較輕量的 `/playByPlay` 回傳相同 `playId`。
- **精華片段 guid 比對**：gamePk 777681 的 `/content` 端點 26 筆 highlight items 中，
  17 筆（單一play片段）的 `guid` 精確等於某顆球的 `playId`；9 筆（賽事濃縮/訪談等合輯）
  `guid` 為 `null`。以 Manny Machado 全壘打為例，`guid = a00d2214-3658-347f-98fc-24c89abb9d0e`
  與該球 `playId` 完全相符，且附完整可播放的 mp4（`content-type: video/mp4`,
  `content-length: 15569732`）。
- **MLB 層級一般球驗證**：鄧愷威 678906，gamePk 776911（2025-08-02），playId
  `b339cea8-e12d-340f-adbc-a655fb63aaed`（一顆 Hit By Pitch 的球），Savant 頁面標題
  正確顯示「Kai-Wei Teng Ball to Brandon Nimmo」，含 `<source src="sporty-clips.mlb.com/...">`。
- **AAA 層級驗證**：鄧愷威 678906，gamePk 779812（2025-03-29），`pitchData` 與 MLB
  同規格完整（`startSpeed`/`pfxX`/`spinRate` 等），但 Savant 回傳 `No Video Found`；
  `/content` 端點 `highlights` 為 `None`。
- **AA 層級驗證**：莊陳仲敖 800018，gamePk 782173（2025-04-06），`playId` 格式為
  `07821736-0016-0013-000c-f08cd117d70a`（非 v3 UUID 格式），`pitchData` 只有
  `strikeZoneTop`/`strikeZoneBottom`/`coordinates.x,y`，無球速/3D 軌跡；Savant 回傳
  `No Video Found`。
- **Cloudflare UA/Referer 行為**（sporty-clips.mlb.com）：
  ```
  curl（無 UA、無 Referer）                              → HTTP 403
  curl -A "Chrome UA"（無 Referer）                       → HTTP 200
  curl -A "Chrome UA" -e baseballsavant.mlb.com           → HTTP 200
  curl -A "Chrome UA" -e https://tingruih.github.io/...   → HTTP 200
  curl -A "Chrome UA" -H "Origin: tingruih.github.io"     → HTTP 200, access-control-allow-origin: *
  ```
  結論：只檢查 UA，不檢查 Referer/Origin。
- **token 短期穩定性**：同一 playId 間隔約 3 分鐘重複請求 `/sporty-videos`，兩次拿到的
  `sporty-clips` token 完全相同；頁面回應 `cache-control: public, max-age=1200,
  s-maxage=3600`。
- **`mlb-cuts-diamond.mlb.com` 永久性驗證**：同一 gamePk 重複呼叫 `/content`，兩次拿到
  位元組完全相同的 mp4 URL，header 含 `x-goog-generation`（GCS 物件版本號）與比賽日期
  吻合的 `last-modified`。
- **CORS/iframe 可行性驗證**：
  ```
  curl -H "Origin: https://tingruih.github.io" .../sporty-videos?playId=...
    → HTTP 200, access-control-allow-origin: *, access-control-allow-methods: GET, OPTIONS
  OPTIONS preflight → HTTP 204, access-control-allow-origin: *
  ```
  頁面 response header 未見 `X-Frame-Options` 或 CSP `frame-ancestors`。
- **索引延遲驗證**：2026-07-07 賽事於隔日測試，所有 playId（含精華球）在 Savant 上一律
  `No Video Found`；2026-05-31 的比賽（超過一個月前）則正常。

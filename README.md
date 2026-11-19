# TwbExpats
一個追蹤所有台灣旅美棒球員的數據網站，包含曾經旅美的所有球員

## Website
https://tingruih.github.io/twbexpats/

## Demo Video

[![TwbExpats Demo Video](https://img.youtube.com/vi/nTaDnR8jwzA/maxresdefault.jpg)](https://www.youtube.com/watch?v=nTaDnR8jwzA)

## 給 Devin Bot 的實作計畫

每次 GitHub Actions 更新完數據，Cloudflare Worker 就抓取該次更新的資料，產生 X 貼文草稿並寄信給站主。站主確認後，由 Worker 發出信中預覽的同一份貼文。第一版使用現有的台灣旅美球員名單，日韓球員的 MLB ID 由站主另外撰寫腳本取得。

### 1. GitHub Actions 匯出資料並通知 Worker

- 在 [現有的 Pages workflow](.github/workflows/pages.yml) 中，讓 `python build.py refresh` 完成後，從 `data/tracker.sqlite3` 匯出供 Bot 使用的 JSON，並隨 `dist` 部署。第一版包含最近的逐場成績，每筆附上球員 MLB ID、顯示名稱、比賽 ID、日期、投打角色、成績與球員頁連結。用 workflow run ID 和 attempt 組成版本化的 JSON 路徑。
- GitHub Pages 部署成功後，再由 Action 呼叫 Worker 的 `POST /updates`，傳入資料版本。Worker 驗證雙方共用的 webhook secret，從設定好的 Pages 網址抓取對應版本的 JSON。通知失敗時，讓 Action 顯示錯誤並可重送。

### 2. Cloudflare Worker 產生草稿、寄信與發文

- Worker 驗證 JSON 後，用球員 MLB ID、比賽 ID 與投打角色識別逐場紀錄，只為尚未處理的紀錄建立草稿。用 Cloudflare D1 保存草稿、關聯紀錄、寄信狀態和 X 貼文 ID，避免排程重疊或重送通知時重複出稿。沒有新紀錄就跳過寄信。[Cloudflare D1 文件](https://developers.cloudflare.com/d1/)
- 寄給站主的信包含完整貼文預覽和有期限的一次性審核連結。開啟連結只顯示預覽，站主在頁面按下「確認發文」才送出 `POST`，避免郵件掃描器開啟連結就觸發發文。
- 站主確認後，Worker 先鎖定該筆草稿，再以有發文權限的 X 帳號憑證呼叫 `POST /2/tweets`。成功後存下貼文 ID。若逾時且無法判斷 X 是否已收到請求，保留待查狀態，查明結果後再決定是否重試。[X 發文 API 文件](https://docs.x.com/x-api/posts/create-post)
- 共用 webhook secret 分別存入 GitHub Actions Secrets 與 Cloudflare Worker Secrets。寄信服務和 X 帳號憑證存入 Worker Secrets，收件地址由站主設定。[Cloudflare Worker Secrets 文件](https://developers.cloudflare.com/workers/configuration/secrets/)

### 3. 日韓球員 MLB ID 擷取腳本（站主負責）

- 用 Python 的 `mlbstatsapi` 查詢 MLB Stats API 的球員資料。先確認候選名單涵蓋哪些 MLB／MiLB 層級與球季，以及 API 回傳的國名寫法，再用 `birth_country`（原始欄位 `birthCountry`）篩選出生於日本或南韓的球員。[套件方法文件](https://zero-sum-seattle.github.io/python-mlb-statsapi/methods/) · [球員資料模型](https://github.com/zero-sum-seattle/python-mlb-statsapi/blob/main/mlbstatsapi/models/people/people.py)
- 以球員的 `id` 作為 `mlb_id` 去重，輸出 JSON，附上姓名和出生國供人工核對。將出生國缺漏的球員列出供檢查。名單核對後，再決定如何接入現有的 [球員名單](src/data/roster.json)。

### 驗收條件

- 部署成功且有新成績時，Worker 能抓到該版本的資料，並寄出包含完整預覽的審核信。部署失敗或沒有新成績時，不會產生新草稿。
- 重送同一更新或再次提交確認時，不會重複產生草稿或發文。開啟審核連結、略過確認或讓連結過期，都不會發文。
- 站主確認後，X 上的貼文與預覽一致，且能從 D1 查到對應的貼文 ID。
- 日韓球員腳本重跑時，同一球員 ID 只會出現一次，輸出可依出生國核對。

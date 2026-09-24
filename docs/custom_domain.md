# 更換網域（自訂網域）檢查清單

## 網址從哪裡來

| 用途 | 來源 | CI | 本機 build |
|---|---|---|---|
| 對外正式網址（canonical、og:url、sitemap、robots、JSON-LD） | `--site-url` | `actions/configure-pages` 的 `base_url` | `site_builder/constants.py::SITE_URL` |
| 站內連結前綴（`href`、`src`） | `--base-url` | `actions/configure-pages` 的 `base_path` | `/`（配合 `python -m http.server 8000 --directory dist`） |
| 頁面路徑（`player/{id}/`、`retired/`…） | `site_builder/render/urls.py`（`player_page_path`、`RETIRED_INDEX_PATH`） | 同左 | 同左 |

CI 的兩個值都直接讀 GitHub Pages 設定（`.github/workflows/pages.yml` 的 `Setup Pages` step）。
在 GitHub 設好自訂網域後，`base_url` 會變成 `https://<網域>`、`base_path` 變成空字串，
**production 不需要改任何程式碼**。

`tests/test_site_url.py` 會擋兩件事：
- `SITE_URL` 的網域或任何 `*.github.io` 出現在 `constants.py` 以外的程式碼、樣板、workflow、promo、scripts。
- 連結、canonical、寫檔位置不是由同一個頁面路徑推導。

## 購買網域後要做的事

### 在 repo 裡（測試會幫你檢查）

1. 修改 `site_builder/constants.py` 的 `SITE_URL`，例如 `https://www.example.com/`。
   本機 build 的 canonical 和 promo 影片片尾網址（`promo/storyboard.py::OUTRO_URL`）會跟著改。
2. 執行 `python -m pytest tests/`，確認 `test_site_url.py` 通過。
3. 修改 `README.md` 的 Website 連結（文件不在測試掃描範圍內）。

### 在 GitHub 與 DNS（測試擋不到，要手動做）

4. 依 GitHub 文件〈Managing a custom domain for your GitHub Pages site〉設定 DNS 紀錄。
5. repo Settings → Pages → Custom domain 填入網域，DNS 生效後勾選 Enforce HTTPS。
   本站用 GitHub Actions 部署（`actions/deploy-pages`），網域以 repo 設定為準，不需要在 `dist/` 放 `CNAME` 檔。
6. 到 Actions 手動觸發一次 `Deploy to GitHub Pages`，確認以下幾點：
   - 首頁原始碼的 `<link rel="canonical">` 是新網域。
   - `/sitemap.xml` 和 `/robots.txt` 裡的網址是新網域。
   - 點進球員頁和已離隊球員頁都不是 404（`base_path` 從 `/twbexpats` 變成空字串，站內連結會少掉 `/twbexpats` 前綴）。
7. 打開舊網址 `https://tingruih.github.io/twbexpats/`，確認會轉址到新網域。

### 站外服務

8. Cloudflare Web Analytics（`src/templates/base.j2` 的 beacon）：到後台確認新網域的流量有被統計。
9. Google Search Console 等搜尋引擎工具：新增新網域資源，重新提交 `sitemap.xml`。
10. 對外連結：GitHub repo About 的 Website 欄位、Threads 個人檔案、YouTube Demo 影片說明。

`docs/feature/plans/` 內的歷史計畫文件含有舊網址，屬於歷史紀錄，不需要修改。

# TwbExpats 宣傳影片

一鍵產出網站宣傳影片：`promo/out/twbexpats_promo.mp4`（1920×1080 / 30fps / 約 80 秒）。

素材全部在本機生成 —— 畫面來自 `dist/` 的真實網站，配樂用 numpy 合成，沒有任何外部素材或版權疑慮。

## 用法

```bash
python -m promo.build_promo            # 完整建置（約 7 分鐘）
python -m promo.build_promo --reuse    # 沿用既有底片，只重跑合成（調節奏時用）
```

需要 `ffmpeg`、`playwright`、系統 Chromium（見 `config.CHROMIUM_PATH`）。
macOS 沙盒會阻擋 socket bind，若由自動化環境執行需停用沙盒，或先自行啟動：

```bash
python -m http.server 8000 --directory dist
```

## 核心設計：三層渲染

不錄螢幕、也不逐幀截圖整支影片，而是用**虛擬攝影機**模型。

| 層 | 職責 |
|---|---|
| **Plate 底片** | Playwright 以 1600×900 viewport、DPR 2.4 截出 3840×2160 大圖（長頁面則為 3840×N） |
| **Camera 攝影機** | Pillow 在底片上 crop + LANCZOS resize 成 1920×1080，zoom/pan 皆為純數學運算 |
| **Overlay 疊加** | 字卡、說明條、游標、轉場 |

這個架構帶來兩個關鍵性質：

**縮放全程無損。** 底片 3840 寬、輸出 1920 寬，因此 zoom 2.0 時 crop 恰為 1920×1080，是 1:1 像素。1.0–2.0 之間任何鏡位都不會糊，`config.MAX_ZOOM` 即由此而來。

**同頁面內的鏡頭移動不可能卡頓。** A 特寫移到 B 特寫只是同一張底片上取景框的一次連續位移，不涉及截圖、重排或重繪。

只有三處真實互動（首頁排序重排、逐球展開、逐球影片播放）才逐幀截真實 DOM。網站前兩處本身是瞬間切換的（`appendChild` / `display=''`），因此在瀏覽器內注入 FLIP 與高度展開動畫後再逐幀擷取 —— 渲染仍然百分之百真實，只是補上了過渡。

**分頁切換不用轉場特效。** 球員頁的分頁列在每一張底片上的 y 座標都相同，所以游標按下分頁按鈕後，鏡頭停在同一個鏡位（`storyboard.tab_view`），只把底片換成另一個分頁的底片 —— 看起來就是「按下去，內容換了」。全片三次分頁切換（進階數據 / 比賽紀錄 / 數據圖表）都靠這個手法，中間沒有任何章節字卡。逐球影片的開啟與關閉、賽季走勢圖的換數據，用的也是同一個原理。

## 檔案結構

```
build_promo.py     一鍵入口
config.py          解析度、色彩、字體、路徑等常數
storyboard.py      分鏡：段落長度、鏡頭編排、文案、轉場 ← 要改節奏改這裡

capture/
  browser.py       伺服器與 Chromium 管理、底片截圖
  scenes.py        各場景如何把網頁設定到目標狀態

compose/
  easing.py        緩動曲線
  camera.py        虛擬攝影機
  cards.py         全屏字卡（只有開場與結尾）
  lower_third.py   下三分之一說明條
  cursor.py        游標與點擊漣漪
  transitions.py   轉場（刻意每次不同）
  timeline.py      段落組裝與串流輸出

audio/music.py     Lo-fi 配樂合成

work/              中繼檔（底片、幀、wav）
out/               成品
```

## 動畫原則

節制是刻意的設計決定，寫在 `storyboard.py` 開頭：

1. 同一時刻只有一個主動畫。鏡頭移動時說明條不進場，反之亦然。
2. 每次 zoom 之後必接一段 hold，讓觀眾讀得完畫面上的數字。
3. Ken Burns 漂移幅度上限 8%，只提供呼吸感，不搶戲。
4. 鏡頭一律走 cubic ease-in-out；游標沿三次貝茲曲線而非直線移動。

## 注意

- 影片內容是建置當下 `dist/` 的靜態快照。網站資料每日更新，影片不會跟著變。

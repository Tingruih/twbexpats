"""底片擷取的瀏覽器與伺服器管理。

這一層只負責「把網頁變成圖」，不含任何鏡頭或動畫邏輯。
"""
from __future__ import annotations

import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from playwright.sync_api import Page, sync_playwright

from promo import config

# 截圖前注入的樣式。除了隱藏捲軸與焦點外框，關鍵是**全域停用 CSS transition**：
# 網站的 .player-card 等元素帶有 transition，會把我們逐幀寫入的 transform 接管成
# 平滑過渡，導致每一幀都還沒到位就被下一幀覆蓋，畫面錯亂。底片擷取的時間軸完全
# 由 Python 掌控，瀏覽器端不該再自作主張補間。
_CAPTURE_CSS = """
::-webkit-scrollbar { width: 0 !important; height: 0 !important; }
* { scrollbar-width: none !important; }
*:focus, *:focus-visible { outline: none !important; }
*, *::before, *::after { transition: none !important; }
/* 頁尾的外部連結不是要展示的功能，留著只會在長底片底部佔一大塊空白，
   害靠近底部的區域取景時被邊界夾住、構圖偏移。 */
.site-footer { display: none !important; }
"""


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


@contextmanager
def serve_dist(port: int = config.SERVER_PORT) -> Iterator[str]:
    """確保 dist/ 有 HTTP 伺服器可用。

    若該埠已有服務就直接沿用（開發時常已手動啟動），否則自行啟動並在結束時關閉。
    網站的連結是根目錄絕對路徑，且逐球資料需以 fetch 載入，因此不能用 file:// 開啟。
    """
    if _port_open(port):
        yield config.BASE_URL
        return

    if not config.DIST_DIR.exists():
        raise FileNotFoundError(
            f"找不到 {config.DIST_DIR}，請先執行 `python build.py build` 產生網站。"
        )

    proc = subprocess.Popen(
        ["python3", "-m", "http.server", str(port), "--directory", str(config.DIST_DIR)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            if _port_open(port):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError(
                f"無法在埠 {port} 啟動伺服器。macOS 沙盒可能阻擋了 socket bind — "
                "請在停用沙盒的情況下執行，或先手動啟動："
                f"\n  python -m http.server {port} --directory dist"
            )
        yield config.BASE_URL
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@contextmanager
def plate_page() -> Iterator[Page]:
    """開啟一個以底片規格設定的頁面（1600×900 viewport、DPR 2.4 → 3840×2160）。"""
    if not Path(config.CHROMIUM_PATH).exists():
        raise FileNotFoundError(
            f"找不到 Chromium：{config.CHROMIUM_PATH}\n"
            "Playwright 官方瀏覽器未安裝，本專案改用系統 Chromium。"
            "請安裝 Chromium，或執行 `playwright install chromium` 後修改 config.CHROMIUM_PATH。"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=config.CHROMIUM_PATH)
        page = browser.new_page(
            viewport={"width": config.PLATE_VIEWPORT_W, "height": config.PLATE_VIEWPORT_H},
            device_scale_factor=config.PLATE_DPR,
        )
        try:
            yield page
        finally:
            browser.close()


@contextmanager
def card_page() -> Iterator[Page]:
    """開啟供字卡使用的頁面。

    viewport 固定 1920×1080（字卡版面的設計基準），解析度靠 DPR 提升：
    1080p 用 2×、4K 用 4×，兩者都保有 2 倍超取樣。
    """
    from promo.compose.cards import CARD_VIEWPORT_H, CARD_VIEWPORT_W, card_dpr

    if not Path(config.CHROMIUM_PATH).exists():
        raise FileNotFoundError(f"找不到 Chromium：{config.CHROMIUM_PATH}")

    with sync_playwright() as p:
        browser_ = p.chromium.launch(executable_path=config.CHROMIUM_PATH)
        page = browser_.new_page(
            viewport={"width": CARD_VIEWPORT_W, "height": CARD_VIEWPORT_H},
            device_scale_factor=card_dpr(),
        )
        try:
            yield page
        finally:
            browser_.close()


def goto(page: Page, url: str, settle: float = 2.5) -> None:
    """前往頁面並等待內容穩定（字體、頭像、圖表都畫完）。"""
    page.goto(url, wait_until="networkidle")
    page.add_style_tag(content=_CAPTURE_CSS)
    _load_lazy_images(page)
    page.wait_for_timeout(int(settle * 1000))


def _load_lazy_images(page: Page) -> None:
    """觸發分批 lazy-load 的頭像。

    avatar-fallback.js 依可視範圍分批載入，不先捲過整頁的話，
    底片下半部的球員頭像會是空的。
    """
    page.evaluate(
        """() => new Promise(resolve => {
            const step = window.innerHeight * 0.8;
            const max = document.body.scrollHeight;
            let y = 0;
            const tick = () => {
                window.scrollTo(0, y);
                y += step;
                if (y < max + step) { setTimeout(tick, 60); }
                else { window.scrollTo(0, 0); setTimeout(resolve, 250); }
            };
            tick();
        })"""
    )
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass  # 頭像 CDN 偶爾有慢速請求；缺一兩張不值得中斷整個建置


def freeze_animations(page: Page) -> None:
    """把所有進行中的 CSS 動畫與轉場推到結束狀態。

    Chart.js 的進場動畫與 CSS transition 若未結束就截圖，底片會停在動畫中途。
    """
    page.evaluate(
        """() => document.getAnimations().forEach(a => { try { a.finish(); } catch (e) {} })"""
    )
    page.wait_for_timeout(120)


def shoot(page: Page, path: Path, full_page: bool = False) -> Path:
    """截一張底片。`full_page=True` 會產生可供鏡頭垂直遊走的長底片。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    freeze_animations(page)
    page.screenshot(path=str(path), full_page=full_page)
    return path


def element_box(page: Page, selector: str) -> tuple[int, int, int, int] | None:
    """取得元素在**底片座標系**中的位置（CSS 像素 × DPR）。

    回傳 (x, y, w, h)，找不到元素時回傳 None。鏡頭的取景框全部以此為依據，
    所以不能用 CSS 像素直接餵給攝影機。
    """
    box = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {
                x: r.left + window.scrollX,
                y: r.top + window.scrollY,
                w: r.width,
                h: r.height,
            };
        }""",
        selector,
    )
    if not box:
        return None
    d = config.PLATE_DPR
    return (int(box["x"] * d), int(box["y"] * d), int(box["w"] * d), int(box["h"] * d))

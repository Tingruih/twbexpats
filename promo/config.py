"""宣傳影片的全域設定 — 解析度、色彩、字體、路徑。

這裡的常數是整支影片的唯一真實來源；其他模組一律 import 而不自行定義。
"""
from __future__ import annotations

from pathlib import Path

# ── 輸出設定檔 ──────────────────────────────────────────────────
# 底片寬度必須是輸出寬度的兩倍，這是整套架構「縮放無損」的前提：
# zoom 2.0 時 crop 尺寸恰好等於輸出尺寸，是 1:1 像素。
# 兩個設定檔都維持 1600×900 的 viewport，只調整 DPR —— 網站的版面因此完全一致，
# 4K 版得到的是更高的渲染解析度，而不是被放大的 1080p。
PROFILES = {
    "1080p": {"width": 1920, "height": 1080, "plate_dpr": 2.4},   # 底片 3840×2160
    "4k": {"width": 3840, "height": 2160, "plate_dpr": 4.8},      # 底片 7680×4320
}
PROFILE = "1080p"

FPS = 30

# ── 底片（plate）擷取規格 ───────────────────────────────────────
# 用比輸出更窄的 viewport，是為了讓網站置中的 1200px 內容區在畫面中佔比更飽滿。
PLATE_VIEWPORT_W = 1600
PLATE_VIEWPORT_H = 900

# 鏡頭縮放上限。超過 2.0 就會開始放大失真。
MAX_ZOOM = 2.0

# 以下由 set_profile() 設定，預設為 1080p。
WIDTH = HEIGHT = PLATE_DPR = PLATE_W = PLATE_H = UI_SCALE = None  # type: ignore[assignment]

# ── 色彩（取自網站 src/static/css/base.css）────────────────────
BLACK = (0, 0, 0)
TEXT_PRIMARY = (245, 245, 245)
TEXT_SECONDARY = (138, 143, 152)
TEAL = (20, 184, 166)          # --teal: #14b8a6，僅用於游標點擊漣漪
TEAL_HEX = "#14b8a6"
# 字卡的打字游標與說明條左側直條共用這個近白色。原本用 teal，但強調色在
# 這兩處會搶掉數據本身的注意力，改為與主文字同色後畫面更乾淨、也更整體。
ACCENT_LINE_HEX = "#F5F5F5"

# ── 字體（與網站一致：中文 PingFang TC、英數 Inter）────────────
FONT_STACK = "'Inter', 'PingFang TC', 'Helvetica Neue', sans-serif"

# ── 路徑 ────────────────────────────────────────────────────────
PROMO_DIR = Path(__file__).resolve().parent
REPO_DIR = PROMO_DIR.parent
DIST_DIR = REPO_DIR / "dist"
WORK_DIR = PROMO_DIR / "work"
OUT_DIR = PROMO_DIR / "out"
OUT_AUDIO = WORK_DIR / "music.wav"
LOGO_SVG = REPO_DIR / "src" / "static" / "logo.svg"

# 底片與幀依設定檔分開存放 —— 兩種解析度的中繼檔不能互相沿用。
PLATE_DIR = FRAME_DIR = OUT_VIDEO = None  # type: ignore[assignment]

# ── 擷取環境 ────────────────────────────────────────────────────
# Playwright 官方瀏覽器未安裝，改用系統 Chromium。
CHROMIUM_PATH = "/Applications/Chromium.app/Contents/MacOS/Chromium"
SERVER_PORT = 8899
BASE_URL = f"http://localhost:{SERVER_PORT}"

# 取材對象：鄧愷威（太空人隊投手）。MLB 層級、六個 tab 資料齊全、六種球路。
FEATURE_PLAYER = "678906"
PLAYER_URL = f"{BASE_URL}/player/{FEATURE_PLAYER}/"
HOME_URL = f"{BASE_URL}/index.html"

# ── 音訊 ────────────────────────────────────────────────────────
SAMPLE_RATE = 48000
MUSIC_BPM = 90
MUSIC_RMS_DBFS = -33.0         # 明確的「點綴」音量，不喧賓奪主
MUSIC_PEAK_CEILING_DBFS = -15.0  # 壓縮後的峰值上限，避免 kick 竄出來刺耳

# ── 全片總長 ────────────────────────────────────────────────────
TOTAL_SECONDS = 80.0
TOTAL_FRAMES = int(TOTAL_SECONDS * FPS)   # 2400


def set_profile(name: str) -> None:
    """切換輸出設定檔。必須在其他模組使用任何解析度常數之前呼叫。

    模組層級的衍生值（例如 transitions 的黑幀、cards 的 CSS）一律延遲計算，
    就是為了讓這個函式能在 import 之後仍然生效。
    """
    global PROFILE, WIDTH, HEIGHT, PLATE_DPR, PLATE_W, PLATE_H, UI_SCALE
    global PLATE_DIR, FRAME_DIR, OUT_VIDEO

    if name not in PROFILES:
        raise ValueError(f"未知的設定檔 {name!r}，可用：{sorted(PROFILES)}")

    p = PROFILES[name]
    PROFILE = name
    WIDTH, HEIGHT = p["width"], p["height"]
    PLATE_DPR = p["plate_dpr"]
    PLATE_W = int(PLATE_VIEWPORT_W * PLATE_DPR)
    PLATE_H = int(PLATE_VIEWPORT_H * PLATE_DPR)
    # 疊加元素（說明條位置、游標尺寸）以 1080p 為基準設計，依此等比放大
    UI_SCALE = WIDTH / 1920

    suffix = "" if name == "1080p" else f"_{name}"
    PLATE_DIR = WORK_DIR / f"plates{suffix}"
    FRAME_DIR = WORK_DIR / f"frames{suffix}"
    OUT_VIDEO = OUT_DIR / f"twbexpats_promo{suffix}.mp4"

    assert PLATE_W == WIDTH * 2, "底片寬度必須是輸出寬度的兩倍，否則縮放會失真"


def ensure_dirs() -> None:
    """建立所有中繼與輸出目錄。"""
    for d in (WORK_DIR, PLATE_DIR, FRAME_DIR, OUT_DIR):
        d.mkdir(parents=True, exist_ok=True)


set_profile(PROFILE)

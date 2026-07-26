"""下三分之一說明條 —— 疊在網頁畫面上即時解說當前功能。

與全屏章節卡的分工：章節卡負責分隔與情緒（置中、大留白），說明條負責解說
（靠左、資訊密度高）。兩者版式刻意對比，交替出現形成節奏。

說明條只渲染一張靜態圖，進退場的位移與淡化由 Pillow 完成 —— 十條說明條若都
逐幀截圖，光這一項就要多花數分鐘，而它的動畫本來就只是平移與透明度。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page

from promo import config
from promo.compose import easing

# 說明條左下角定位。以 1080p 為設計基準，其他解析度等比換算。
BASE_POS_X = 180
BASE_POS_Y = 852


def position() -> tuple[int, int]:
    return (round(BASE_POS_X * config.UI_SCALE), round(BASE_POS_Y * config.UI_SCALE))

_CSS = f"""
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ background: transparent; }}
body {{ font-family: 'Inter', 'PingFang TC', 'Helvetica Neue', sans-serif;
        -webkit-font-smoothing: antialiased; }}
.lt {{
    display: inline-flex; align-items: stretch; gap: 18px;
    background: rgba(9, 10, 11, 0.82);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 10px;
    padding: 20px 30px 20px 22px;
}}
.bar {{ width: 4px; border-radius: 2px; background: {config.ACCENT_LINE_HEX}; }}
.main {{ font-size: 30px; font-weight: 500; color: #F5F5F5;
         letter-spacing: 0.02em; line-height: 1.25; white-space: nowrap; }}
.sub {{ font-size: 19px; color: #8A8F98; letter-spacing: 0.06em;
        margin-top: 7px; white-space: nowrap; }}
"""


@dataclass(frozen=True)
class Caption:
    """一條說明。`at` 與 `dur` 為相對於所屬段落起點的秒數。"""

    main: str
    sub: str
    at: float
    dur: float


@dataclass
class CaptionAsset:
    """渲染好的說明條圖像。"""

    caption: Caption
    image: Image.Image


def _html(c: Caption) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{_CSS}</style></head><body>"
        f"<div class='lt' id='lt'><div class='bar'></div>"
        f"<div><div class='main'>{c.main}</div><div class='sub'>{c.sub}</div></div>"
        "</div></body></html>"
    )


def render(page: Page, captions: list[Caption], work: Path) -> list[CaptionAsset]:
    """把每條說明渲染成一張透明底圖像。"""
    work.mkdir(parents=True, exist_ok=True)
    assets: list[CaptionAsset] = []
    for i, c in enumerate(captions):
        tmp = work / f"_lt_{i:02d}.html"
        tmp.write_text(_html(c), encoding="utf-8")
        page.goto(tmp.as_uri())
        page.wait_for_timeout(160)
        png = work / f"lt_{i:02d}.png"
        page.locator("#lt").screenshot(path=str(png), omit_background=True)
        with Image.open(png) as im:
            # 截圖帶有 2 倍超取樣，縮回目標尺寸取得乾淨邊緣。
            # 目標尺寸 = CSS 尺寸 × UI_SCALE，因此縮放係數固定為超取樣倍率。
            img = im.convert("RGBA")
            scale = config.UI_SCALE / (page.evaluate("() => window.devicePixelRatio"))
            img = img.resize(
                (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                Image.LANCZOS,
            )
        assets.append(CaptionAsset(c, img))
    return assets


def compose(frame: Image.Image, asset: CaptionAsset, elapsed: float) -> Image.Image:
    """把說明條依進場/停留/退場狀態疊到畫面上。

    `elapsed` 是相對於該說明條 `at` 的秒數；超出顯示區間則原樣返回。
    """
    c = asset.caption
    if elapsed < 0 or elapsed > c.dur:
        return frame

    fade_in, fade_out = 0.45, 0.35
    slide = 24 * config.UI_SCALE
    if elapsed < fade_in:
        p = easing.ease_out_cubic(elapsed / fade_in)
        alpha, dy = p, (1 - p) * slide           # 由下方滑入
    elif elapsed > c.dur - fade_out:
        p = easing.ease_in_cubic((c.dur - elapsed) / fade_out)
        alpha, dy = p, (1 - p) * -slide * 0.5    # 退場時輕微下沉
    else:
        alpha, dy = 1.0, 0.0

    if alpha <= 0.01:
        return frame

    img = asset.image
    if alpha < 1.0:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))

    out = frame.convert("RGBA")
    px, py = position()
    out.alpha_composite(img, (px, py - img.height + int(round(dy))))
    return out.convert("RGB")

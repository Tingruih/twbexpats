"""滑鼠游標與點擊回饋。

全片只在真正需要點擊的地方出現（首頁排序鈕、逐球展開箭頭），其餘時間不顯示 ——
一直掛著一個游標會變成畫面雜訊。

移動路徑走三次貝茲曲線而非直線：真人移動滑鼠不會走直線，這一點對「有人在操作」
的說服力影響很大。
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from promo import config
from promo.compose import easing

_SS = 4               # 繪製時的超取樣倍率，換取乾淨的圓邊
BASE_RADIUS = 11      # 游標本體半徑（以 1080p 為基準）
BASE_RING = 25        # 外環半徑
BASE_RIPPLE = 90      # 點擊漣漪的最大半徑


@dataclass(frozen=True)
class Click:
    """一次點擊：`at` 為相對於段落起點的秒數。"""

    at: float
    duration: float = 0.45


def bezier_path(
    start: tuple[float, float],
    end: tuple[float, float],
    bow: float = 0.22,
) -> tuple[tuple[float, float], ...]:
    """由起點與終點推出一條帶弧度的貝茲路徑控制點。

    `bow` 控制彎曲程度，取垂直於移動方向的偏移量比例。
    """
    x0, y0 = start
    x1, y1 = end
    dx, dy = x1 - x0, y1 - y0
    # 垂直方向偏移，讓路徑鼓起一個自然的弧
    nx, ny = -dy * bow, dx * bow
    p1 = (x0 + dx * 0.35 + nx, y0 + dy * 0.35 + ny)
    p2 = (x0 + dx * 0.70 + nx * 0.5, y0 + dy * 0.70 + ny * 0.5)
    return (x0, y0), p1, p2, (x1, y1)


def position_at(
    start: tuple[float, float],
    end: tuple[float, float],
    t: float,
    bow: float = 0.22,
) -> tuple[float, float]:
    """游標在移動過程中的位置（速度呈 ease-in-out，起步慢、抵達前減速）。"""
    p0, p1, p2, p3 = bezier_path(start, end, bow)
    return easing.bezier_point(p0, p1, p2, p3, easing.ease_in_out_cubic(t))


def draw(
    frame: Image.Image,
    pos: tuple[float, float],
    click_t: float | None = None,
    opacity: float = 1.0,
) -> Image.Image:
    """把游標畫到畫面上。

    `click_t` 若給定（0→1），會同時畫出擴散的 teal 漣漪，並讓游標本體
    先縮小再回彈，模擬按下的手感。
    """
    if opacity <= 0.01:
        return frame

    x, y = pos
    scale = 1.0
    if click_t is not None:
        # 前 30% 壓下、後 70% 帶輕微過衝回彈
        if click_t < 0.3:
            scale = 1.0 - 0.15 * easing.ease_out_cubic(click_t / 0.3)
        else:
            scale = 0.85 + 0.15 * easing.ease_out_back((click_t - 0.3) / 0.7)

    # 尺寸隨輸出解析度等比放大，游標在 4K 下才不會縮成一個小點
    us = config.UI_SCALE
    radius, ring, ripple = BASE_RADIUS * us, BASE_RING * us, BASE_RIPPLE * us

    layer = Image.new("RGBA", (frame.width, frame.height), (0, 0, 0, 0))
    # 只在游標周圍的小塊區域做超取樣繪製，避免整張畫面放大 4 倍的成本
    pad = int(ring * 6)
    box_l, box_t = int(x) - pad, int(y) - pad
    tile = Image.new("RGBA", (pad * 2 * _SS, pad * 2 * _SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    cx = cy = pad * _SS

    def circle(r: float, fill=None, outline=None, width: float = 0) -> None:
        d.ellipse(
            [cx - r * _SS, cy - r * _SS, cx + r * _SS, cy + r * _SS],
            fill=fill, outline=outline, width=max(1, int(width * us * _SS)),
        )

    # 點擊漣漪：由游標大小擴散開並淡出
    if click_t is not None:
        rp = easing.ease_out_cubic(click_t)
        r = radius + (ripple - radius) * rp
        a = int(210 * (1 - rp) ** 1.5 * opacity)
        if a > 2:
            circle(r, outline=(*config.TEAL, a), width=3)

    a_main = int(255 * opacity)
    circle(ring * scale, outline=(255, 255, 255, int(70 * opacity)), width=2)
    circle(radius * scale, fill=(255, 255, 255, a_main))

    tile = tile.resize((pad * 2, pad * 2), Image.LANCZOS)
    layer.alpha_composite(tile, (box_l, box_t))

    out = frame.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")

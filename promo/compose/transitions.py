"""段落之間的轉場。

刻意讓每一次轉場都不同。九次段落切換若都用同一種溶接，觀眾會在第三次之後
開始感到單調；換手法本身就是節奏的一部分。

所有轉場統一介面：`fn(a, b, t) -> Image`，其中 t 由 0 走到 1，
a 是前一段的畫面、b 是後一段的畫面。
"""
from __future__ import annotations

from PIL import Image, ImageFilter

from promo import config
from promo.compose import easing

_BLACK_CACHE: dict[tuple[int, int], Image.Image] = {}


def _black() -> Image.Image:
    """輸出尺寸的黑幀。延遲建立並快取，才能在 set_profile() 後仍然正確。"""
    key = (config.WIDTH, config.HEIGHT)
    img = _BLACK_CACHE.get(key)
    if img is None:
        img = Image.new("RGB", key, (0, 0, 0))
        _BLACK_CACHE[key] = img
    return img


def crossfade(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    return Image.blend(a, b, easing.smoothstep(t))


def dip_to_black(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    """經過純黑再浮出。前半把 a 壓暗，後半把 b 帶出。"""
    if t < 0.5:
        return Image.blend(a, _black(), easing.ease_in_cubic(t * 2))
    return Image.blend(_black(), b, easing.ease_out_cubic((t - 0.5) * 2))


def black_flash(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    """極短促的黑閃，用來製造節奏轉折而非柔和過渡。"""
    if t < 0.42:
        return Image.blend(a, _black(), easing.ease_in_cubic(t / 0.42))
    if t < 0.58:
        return _black()
    return Image.blend(_black(), b, easing.ease_out_quint((t - 0.58) / 0.42))


def _soft_mask(t: float, horizontal: bool, softness: int = 220) -> Image.Image:
    """產生一條帶柔邊的擦除遮罩。"""
    length = config.WIDTH if horizontal else config.HEIGHT
    edge = t * (length + softness) - softness
    # 用單列/單行的漸層再拉伸，比逐像素運算快得多
    strip = Image.new("L", (length, 1))
    px = strip.load()
    for i in range(length):
        v = (i - edge) / softness
        px[i, 0] = 0 if v >= 1 else 255 if v <= 0 else int(255 * (1 - v))
    if horizontal:
        return strip.resize((config.WIDTH, config.HEIGHT))
    return strip.rotate(90, expand=True).resize((config.WIDTH, config.HEIGHT))


def wipe_right(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    """由左向右的柔邊遮罩擦除。"""
    return Image.composite(b, a, _soft_mask(easing.ease_in_out_cubic(t), horizontal=True))


def wipe_up(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    """由下向上的柔邊遮罩擦除。"""
    mask = _soft_mask(easing.ease_in_out_cubic(t), horizontal=False)
    return Image.composite(b, a, mask.transpose(Image.FLIP_TOP_BOTTOM))


def slide_up_soft(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    """a 向上滑出，b 帶著輕微失焦從下方浮入。"""
    p = easing.ease_in_out_cubic(t)
    canvas = Image.new("RGB", (config.WIDTH, config.HEIGHT), (0, 0, 0))

    blur = 7 * (1 - p)
    nb = b.filter(ImageFilter.GaussianBlur(blur)) if blur > 0.4 else b
    if p < 1:
        canvas.paste(a, (0, int(-config.HEIGHT * 0.55 * p)))
    canvas.paste(nb, (0, int(config.HEIGHT * 0.35 * (1 - p))))
    if p < 0.25:   # 起手瞬間讓 b 尚未完全不透明，避免硬邊
        canvas = Image.blend(a, canvas, p / 0.25)
    return canvas


def zoom_out_reveal(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    """從 a 的中心向外拉遠，露出 b。用於字卡標題「退開」讓網頁登場。"""
    p = easing.ease_in_out_cubic(t)
    scale = 1.0 + 0.55 * p
    w, h = int(config.WIDTH * scale), int(config.HEIGHT * scale)
    grown = a.resize((w, h), Image.BILINEAR)
    grown = grown.crop((
        (w - config.WIDTH) // 2, (h - config.HEIGHT) // 2,
        (w - config.WIDTH) // 2 + config.WIDTH, (h - config.HEIGHT) // 2 + config.HEIGHT,
    ))
    return Image.blend(grown, b, easing.ease_in_cubic(t))


def push_in_fade(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    """b 由略微放大收回到正常尺寸並淡入。"""
    p = easing.ease_out_cubic(t)
    scale = 1.06 - 0.06 * p
    w, h = int(config.WIDTH * scale), int(config.HEIGHT * scale)
    zoomed = b.resize((w, h), Image.BILINEAR).crop((
        (w - config.WIDTH) // 2, (h - config.HEIGHT) // 2,
        (w - config.WIDTH) // 2 + config.WIDTH, (h - config.HEIGHT) // 2 + config.HEIGHT,
    ))
    return Image.blend(a, zoomed, p)


def pull_back_blur(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    """a 向後退開並失焦，b 隨後浮現。用於全片收尾。"""
    p = easing.ease_in_out_cubic(t)
    scale = 1.0 - 0.12 * p
    w, h = max(2, int(config.WIDTH * scale)), max(2, int(config.HEIGHT * scale))
    shrunk = Image.new("RGB", (config.WIDTH, config.HEIGHT), (0, 0, 0))
    small = a.resize((w, h), Image.BILINEAR)
    if p > 0.05:
        small = small.filter(ImageFilter.GaussianBlur(10 * p))
    shrunk.paste(small, ((config.WIDTH - w) // 2, (config.HEIGHT - h) // 2))
    shrunk = Image.blend(shrunk, _black(), 0.45 * p)
    return Image.blend(shrunk, b, easing.ease_in_cubic(t))


def fade_from_black(frame: Image.Image, t: float) -> Image.Image:
    return Image.blend(_black(), frame, easing.ease_out_cubic(t))


def fade_to_black(frame: Image.Image, t: float) -> Image.Image:
    return Image.blend(frame, _black(), easing.ease_in_cubic(t))

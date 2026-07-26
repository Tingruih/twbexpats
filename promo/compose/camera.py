"""虛擬攝影機 —— 在底片上取景，產出影片幀。

鏡頭運動是「底片上一個矩形取景框隨時間移動」的純數學問題：不觸發網頁重繪、
不重新截圖，因此同一張底片上的任何移動都必定平滑。

取景框的尺寸由 zoom 決定：
    zoom = 1.0 → 3840×2160（底片全寬，縮小 50% 輸出）
    zoom = 2.0 → 1920×1080（1:1 像素，零損失）
超過 2.0 就開始放大失真，因此 `View` 會強制夾在這個上限內。
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from promo import config
from promo.compose import easing

# 4K 設定檔的長底片可達 7680×19243（約 1.5 億像素），遠超 Pillow 的預設上限。
Image.MAX_IMAGE_PIXELS = None


def aspect() -> float:
    """輸出畫面的高寬比。延遲計算，才能在 set_profile() 後仍然正確。"""
    return config.HEIGHT / config.WIDTH


# 底片很大（1080p 約 110MB、4K 可達 440MB），同一張會被多個鏡頭重複取用，
# 因此快取起來；但必須在段落之間釋放，否則 4K 建置會累積到數 GB。
_PLATE_CACHE: dict[Path, Image.Image] = {}
_CACHE_LIMIT = 3


def load_plate(path: Path) -> Image.Image:
    img = _PLATE_CACHE.get(path)
    if img is None:
        if len(_PLATE_CACHE) >= _CACHE_LIMIT:
            # 互動序列每幀都是不同檔案，沒有上限會把整段序列全留在記憶體裡
            _PLATE_CACHE.pop(next(iter(_PLATE_CACHE)))
        img = Image.open(path).convert("RGB")
        _PLATE_CACHE[path] = img
    return img


def clear_cache() -> None:
    _PLATE_CACHE.clear()


@dataclass(frozen=True)
class View:
    """一個取景位置：底片座標上的中心點與縮放倍率。"""

    cx: float
    cy: float
    zoom: float = 1.0

    def crop_size(self) -> tuple[float, float]:
        w = config.PLATE_W / self.zoom
        return w, w * aspect()


def view_box(
    box: tuple[int, int, int, int],
    plate_size: tuple[int, int],
    padding: float = 1.12,
    max_zoom: float = config.MAX_ZOOM,
    min_zoom: float = 1.0,
    bias_y: float = 0.0,
) -> View:
    """算出「讓某個區域填滿畫面」的取景位置。

    `padding` 是留白倍率（1.12 表示區域四周多留 12%），`bias_y` 以取景框高度為
    單位微調垂直中心，用來把標題或表頭留在畫面裡。
    """
    x, y, w, h = box
    pw, ph = config.PLATE_W, config.PLATE_H
    # 同時滿足寬與高的縮放，取較保守者
    zoom_w = pw / max(1.0, w * padding)
    zoom_h = (pw * aspect()) / max(1.0, h * padding)
    zoom = max(min_zoom, min(max_zoom, min(zoom_w, zoom_h)))
    _, ch = View(0, 0, zoom).crop_size()
    return clamp_view(View(x + w / 2, y + h / 2 + bias_y * ch, zoom), plate_size)


def view_full(plate_size: tuple[int, int], cy: float | None = None) -> View:
    """整幅寬度的全景取景，垂直位置可指定。"""
    _, ph = plate_size
    return clamp_view(View(config.PLATE_W / 2, ph / 2 if cy is None else cy, 1.0), plate_size)


def clamp_view(v: View, plate_size: tuple[int, int]) -> View:
    """把取景框夾回底片範圍內，避免畫面出現底片外的黑邊。"""
    pw, ph = plate_size
    cw, ch = v.crop_size()
    # 底片比取景框還小的方向（長底片不會發生）就置中
    cx = pw / 2 if cw >= pw else min(max(v.cx, cw / 2), pw - cw / 2)
    cy = ph / 2 if ch >= ph else min(max(v.cy, ch / 2), ph - ch / 2)
    return View(cx, cy, v.zoom)


def lerp_view(a: View, b: View, t: float, arc: float = 0.0) -> View:
    """兩個取景位置間的插值。

    `arc > 0` 會讓鏡頭在移動途中先略微拉遠、抵達時再推回 —— 這是真實運鏡的
    習慣（長距離移動時先帶到全局再落點），比等速直線平移自然得多。
    """
    zoom = easing.lerp(a.zoom, b.zoom, t)
    if arc:
        zoom *= 1.0 - arc * math.sin(math.pi * easing.clamp(t))
    return View(
        easing.lerp(a.cx, b.cx, t),
        easing.lerp(a.cy, b.cy, t),
        max(1.0, zoom),
    )


def render(plate: Image.Image, v: View) -> Image.Image:
    """依取景位置從底片裁出一幀並縮放到輸出解析度。"""
    v = clamp_view(v, plate.size)
    pw, ph = plate.size
    cw, ch = v.crop_size()
    # 取景框可能比底片大（短底片被要求全景時），一律夾回實際範圍，
    # 否則 Pillow 會因 box 超出邊界而拒絕。
    cw, ch = min(cw, pw), min(ch, ph)
    left = min(max(0.0, v.cx - cw / 2), pw - cw)
    top = min(max(0.0, v.cy - ch / 2), ph - ch)
    return plate.resize(
        (config.WIDTH, config.HEIGHT),
        resample=Image.LANCZOS,
        box=(left, top, left + cw, top + ch),
    )


# ── 鏡頭：一段連續的取景運動 ───────────────────────────────────

PlateSource = Callable[[float], Image.Image]


def static_source(path: Path) -> PlateSource:
    return lambda _t: load_plate(path)


def sequence_source(paths: list[Path]) -> PlateSource:
    """把一串底片映射到 0→1 的進度，用於捕捉到的互動序列。"""

    def src(t: float) -> Image.Image:
        idx = min(len(paths) - 1, max(0, int(t * len(paths))))
        return load_plate(paths[idx])

    return src


@dataclass
class _Segment:
    frames: int
    start: View
    end: View
    ease: Callable[[float], float]
    arc: float


class Shot:
    """以「時間軸建構器」的方式描述一段鏡頭運動。

        shot = Shot(source, plate_size, start=view_full(size))
        shot.hold(1.0)
        shot.to(view_box(box, size), 1.6, arc=0.12)
        shot.hold(0.9)
    """

    def __init__(
        self,
        source: PlateSource,
        plate_size: tuple[int, int],
        start: View,
        fps: int = config.FPS,
    ) -> None:
        self.source = source
        self.plate_size = plate_size
        self.fps = fps
        self.current = clamp_view(start, plate_size)
        self.segments: list[_Segment] = []

    # ── 建構 ────────────────────────────────────────────────
    def hold(self, seconds: float) -> "Shot":
        """停在目前位置。每次 zoom 之後都應該接一段 hold，讓觀眾讀得完畫面。"""
        n = self._n(seconds)
        self.segments.append(_Segment(n, self.current, self.current, easing.linear, 0.0))
        return self

    def to(
        self,
        target: View,
        seconds: float,
        ease: Callable[[float], float] = easing.ease_in_out_cubic,
        arc: float = 0.0,
    ) -> "Shot":
        """移動到新的取景位置。"""
        target = clamp_view(target, self.plate_size)
        n = self._n(seconds)
        self.segments.append(_Segment(n, self.current, target, ease, arc))
        self.current = target
        return self

    def drift(self, seconds: float, dy: float = 0.0, dx: float = 0.0,
              dzoom: float = 0.0) -> "Shot":
        """Ken Burns 式的緩慢漂移，提供呼吸感而不搶戲。

        位移量以取景框尺寸為單位（dy=0.25 表示移動四分之一個畫面高）。
        """
        cw, ch = self.current.crop_size()
        target = View(
            self.current.cx + dx * cw,
            self.current.cy + dy * ch,
            max(1.0, self.current.zoom + dzoom),
        )
        return self.to(target, seconds, ease=easing.smoothstep)

    def _n(self, seconds: float) -> int:
        return max(1, int(round(seconds * self.fps)))

    # ── 輸出 ────────────────────────────────────────────────
    @property
    def total_frames(self) -> int:
        return sum(s.frames for s in self.segments)

    @property
    def duration(self) -> float:
        return self.total_frames / self.fps

    def frames(self) -> Iterator[tuple[Image.Image, View]]:
        """逐幀產出 (畫面, 取景位置)。

        取景位置一併回傳，是為了讓游標能依底片座標換算出它在畫面上的位置 ——
        鏡頭移動時游標必須跟著貼在按鈕上，否則會穿幫。
        """
        total = self.total_frames
        done = 0
        for seg in self.segments:
            for i in range(seg.frames):
                local = seg.ease(i / seg.frames) if seg.frames > 1 else 1.0
                v = lerp_view(seg.start, seg.end, local, seg.arc)
                plate = self.source((done + i) / max(1, total))
                yield render(plate, clamp_view(v, self.plate_size)), clamp_view(v, self.plate_size)
            done += seg.frames


def plate_to_output(point: tuple[float, float], v: View) -> tuple[float, float]:
    """把底片座標換算成輸出畫面座標，用於把游標定位到畫面上的元素。"""
    cw, ch = v.crop_size()
    sx = config.WIDTH / cw
    sy = config.HEIGHT / ch
    return ((point[0] - (v.cx - cw / 2)) * sx, (point[1] - (v.cy - ch / 2)) * sy)


def box_center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    x, y, w, h = box
    return (x + w / 2, y + h / 2)

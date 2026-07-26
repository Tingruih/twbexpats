"""時間軸組裝 —— 把段落、疊加層與轉場串成完整幀序列。

轉場採用剪輯軟體慣用的**重疊**模型：兩段各讓出 N 幀，混合後取代那 N 幀，
因此全片長度 = 各段長度總和 − 各轉場長度總和。

渲染過程全程串流寫檔。2280 幀若全放記憶體約需 14GB；這裡只保留轉場所需的
少量緩衝（數十幀），峰值記憶體維持在數百 MB。
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from promo import config
from promo.compose import camera, cursor, lower_third
from promo.compose.lower_third import CaptionAsset

TransitionFn = Callable[[Image.Image, Image.Image, float], Image.Image]


@dataclass
class Transition:
    fn: TransitionFn
    seconds: float

    @property
    def frames(self) -> int:
        return max(1, int(round(self.seconds * config.FPS)))


@dataclass
class CursorTrack:
    """一段游標動作：從 A 點移到 B 點，抵達後點擊。

    起點與終點皆為**底片座標**，這樣鏡頭移動時游標仍會貼著目標元素。
    """

    start: tuple[float, float]
    end: tuple[float, float]
    move_at: float
    move_dur: float
    click_at: float
    click_dur: float = 0.45
    fade_in: float = 0.3
    hold_after: float = 0.5
    bow: float = 0.22

    def state(self, t: float) -> tuple[tuple[float, float], float, float | None] | None:
        """回傳 (底片座標, 不透明度, 點擊進度)；不該顯示時回傳 None。"""
        appear = self.move_at - self.fade_in
        vanish = self.click_at + self.click_dur + self.hold_after
        if t < appear or t > vanish:
            return None

        if t < self.move_at:
            pos, opacity = self.start, (t - appear) / max(1e-6, self.fade_in)
        elif t < self.move_at + self.move_dur:
            p = (t - self.move_at) / self.move_dur
            pos, opacity = cursor.position_at(self.start, self.end, p, self.bow), 1.0
        else:
            pos, opacity = self.end, 1.0

        # 退場時淡出
        fade_tail = 0.3
        if t > vanish - fade_tail:
            opacity = min(opacity, (vanish - t) / fade_tail)

        click_t = None
        if self.click_at <= t <= self.click_at + self.click_dur:
            click_t = (t - self.click_at) / self.click_dur
        return pos, max(0.0, min(1.0, opacity)), click_t


class Segment:
    """時間軸上的一段。子類別決定畫面從哪裡來。"""

    name: str
    n_frames: int
    transition_in: Transition | None

    def frames(self) -> Iterator[Image.Image]:
        raise NotImplementedError

    @property
    def seconds(self) -> float:
        return self.n_frames / config.FPS


@dataclass
class ShotSegment(Segment):
    """網頁畫面段落：鏡頭運動 + 說明條 + 游標。"""

    name: str
    shot: camera.Shot
    captions: list[CaptionAsset] = field(default_factory=list)
    cursor_track: CursorTrack | None = None
    transition_in: Transition | None = None

    @property
    def n_frames(self) -> int:
        return self.shot.total_frames

    def frames(self) -> Iterator[Image.Image]:
        for i, (img, view) in enumerate(self.shot.frames()):
            t = i / config.FPS
            for asset in self.captions:
                img = lower_third.compose(img, asset, t - asset.caption.at)
            if self.cursor_track:
                st = self.cursor_track.state(t)
                if st:
                    plate_pt, opacity, click_t = st
                    img = cursor.draw(
                        img, camera.plate_to_output(plate_pt, view), click_t, opacity
                    )
            yield img


@dataclass
class CardSegment(Segment):
    """字卡段落。畫面已由瀏覽器渲染完成，這裡只負責降取樣。"""

    name: str
    paths: list[Path]
    transition_in: Transition | None = None

    @property
    def n_frames(self) -> int:
        return len(self.paths)

    def frames(self) -> Iterator[Image.Image]:
        from promo.compose.cards import downscale

        for p in self.paths:
            yield downscale(p)


def total_frames(segments: list[Segment]) -> int:
    n = sum(s.n_frames for s in segments)
    n -= sum(s.transition_in.frames for s in segments if s.transition_in)
    return n


def render(
    segments: list[Segment],
    out_dir: Path,
    fade_in: float = 0.0,
    fade_out: float = 0.8,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """把所有段落渲染成連號 PNG，回傳實際輸出幀數。"""
    from promo.compose import transitions

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()

    expected = total_frames(segments)
    fade_in_n = int(round(fade_in * config.FPS))
    fade_out_n = int(round(fade_out * config.FPS))
    written = 0

    def write(img: Image.Image) -> None:
        nonlocal written
        # 全片頭尾的統一淡入淡出在此套用，段落本身不需要各自處理
        if fade_in_n and written < fade_in_n:
            img = transitions.fade_from_black(img, (written + 1) / fade_in_n)
        remaining = expected - written
        if fade_out_n and remaining <= fade_out_n:
            img = transitions.fade_to_black(img, 1 - (remaining - 1) / fade_out_n)
        img.save(out_dir / f"f{written:05d}.png")
        written += 1
        if progress:
            progress(written, expected)

    pending: list[Image.Image] = []   # 上一段尾部，保留給下一段的轉場
    for i, seg in enumerate(segments):
        gen = seg.frames()

        if seg.transition_in and pending:
            n = min(seg.transition_in.frames, len(pending))
            head = [next(gen) for _ in range(n)]
            for k, (a, b) in enumerate(zip(pending[-n:], head)):
                write(seg.transition_in.fn(a, b, k / max(1, n - 1)))
            # pending 中未被轉場消耗的部分已無處可去（轉場長度不應超過段落長度）
            pending = []

        # 下一段若要轉場，本段尾部要留給它
        nxt = segments[i + 1] if i + 1 < len(segments) else None
        reserve = nxt.transition_in.frames if nxt and nxt.transition_in else 0

        buf: list[Image.Image] = []
        for img in gen:
            buf.append(img)
            if len(buf) > reserve:
                write(buf.pop(0))
        pending = buf

        # 段落之間釋放底片。4K 的長底片單張就佔上 GB，不釋放會一路累積。
        # 每個段落用的底片各不相同，因此清空沒有任何重載成本。
        camera.clear_cache()

    for img in pending:
        write(img)
    return written

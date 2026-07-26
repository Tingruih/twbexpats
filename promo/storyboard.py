"""分鏡 —— 全片唯一的「劇本」。

要改節奏、改文案、改鏡位，只需要動這個檔案。

時間結構（轉場採重疊模型，最終長度 = 段落總和 − 轉場總和）：

    段落總和 81.1s − 轉場總和 4.7s ≈ 76.4s

三個貫穿全片的節制原則：
  1. 同一時刻只有一個主動畫在跑。鏡頭移動時說明條不進場，反之亦然。
  2. 每次 zoom 之後必接一段 hold，讓觀眾讀得完畫面上的數字。
  3. Ken Burns 漂移幅度極小，只提供呼吸感，不搶戲。
"""
from __future__ import annotations

from dataclasses import dataclass

from promo import config
from promo.compose import easing, transitions
from promo.compose.lower_third import Caption
from promo.compose.timeline import CursorTrack, Transition

# ── 文案 ────────────────────────────────────────────────────────

INTRO_TITLE = "TwbExpats"
INTRO_SUBTITLE = "臺灣旅美棒球員數據網站"

CHAPTER_2 = "每一球都有數據"
CHAPTER_3 = "逐球追蹤"
CHAPTER_4 = "看得見的球路"

OUTRO_URL = "tingruih.github.io/twbexpats"
OUTRO_TAGLINE = "每一位旅美球員的完整數據"

# ── 段落長度（秒）──────────────────────────────────────────────

D_INTRO = 6.0
D_HOME = 7.0
D_HOME_SORT = 7.0
D_CHAPTER2 = 3.4
D_ADVANCED = 22.5      # 進階數據與球種分析共用一張長底片，全程連續運鏡
D_CHAPTER3 = 3.3
D_EXPAND = 6.0
D_PITCHLOG = 7.0
D_CHAPTER4 = 3.4
D_PLOT = 10.0
D_OUTRO = 5.5

# ── 轉場（刻意每一次都不同）────────────────────────────────────

T_HOME = Transition(transitions.slide_up_soft, 0.7)
T_CHAPTER2 = Transition(transitions.dip_to_black, 0.6)
T_ADVANCED = Transition(transitions.wipe_right, 0.5)
T_CHAPTER3 = Transition(transitions.black_flash, 0.3)
T_EXPAND = Transition(transitions.zoom_out_reveal, 0.7)
T_CHAPTER4 = Transition(transitions.wipe_up, 0.5)
T_PLOT = Transition(transitions.push_in_fade, 0.6)
T_OUTRO = Transition(transitions.pull_back_blur, 0.8)

# 首頁的兩個子段與逐球的兩個子段之間不轉場 —— 它們是同一個畫面的延續。

# ── 說明條 ──────────────────────────────────────────────────────

CAPTIONS_HOME = [
    Caption("25 位旅美球員，一頁掌握", "MLB · AAA · AA · A+ · A · ROK", at=1.1, dur=4.4),
]
CAPTIONS_HOME_SORT = [
    Caption("一鍵切換排序", "依層級，或依最近出賽", at=3.9, dur=2.9),
]
CAPTIONS_ADVANCED = [
    Caption("Statcast 進階指標", "FIP · xwOBA · Barrel% · 平均擊球初速", at=1.4, dur=4.4),
    Caption("選球能力全解析", "Chase% · Whiff% · CSW%", at=7.6, dur=4.0),
    Caption("投球球種分析", "每種球的用量、球速、位移、轉速", at=13.2, dur=4.0),
    Caption("各球數配球比例", "領先、落後、兩好球的配球差異", at=18.3, dur=3.8),
]
CAPTIONS_PITCHLOG = [
    Caption("每一球的完整數據", "球種 · 球速 · 進壘區 · 位移 · 轉速", at=0.3, dur=3.0),
    Caption("直接看該球影片", "一鍵跳轉 MLB 官方影片", at=4.0, dur=2.7),
]
CAPTIONS_PLOT = [
    Caption("球種位移圖", "每一球的水平與垂直位移分布", at=0.7, dur=3.6),
    Caption("Pitch Plinko", "球數推進過程中的配球變化", at=5.5, dur=3.8),
]

ALL_CAPTIONS = (
    CAPTIONS_HOME + CAPTIONS_HOME_SORT + CAPTIONS_ADVANCED
    + CAPTIONS_PITCHLOG + CAPTIONS_PLOT
)

# ── 互動時間點 ──────────────────────────────────────────────────

# 首頁排序：游標進場 → 移到「最近出賽」→ 點擊 → 卡片重排
SORT_MOVE_AT = 1.4
SORT_MOVE_DUR = 1.05
SORT_CLICK_AT = 2.45
SORT_ANIM_DUR = 1.2

# 逐球展開：游標移到展開箭頭 → 點擊 → 表格展開
EXPAND_MOVE_AT = 0.75
EXPAND_MOVE_DUR = 1.0
EXPAND_CLICK_AT = 1.95
EXPAND_ANIM_DUR = 1.25


@dataclass(frozen=True)
class SequenceWindow:
    """互動序列在段落中的時間窗。

    序列之外的時間，畫面停在序列的第一幀或最後一幀 —— 游標移動與展開後的
    停留都屬於「靜止」，不需要為它們額外截圖。
    """

    start: float
    end: float
    duration: float

    def source_index(self, t: float, n: int) -> int:
        """把段落進度 t（0→1）映射到序列幀索引。"""
        sec = t * self.duration
        if sec <= self.start:
            return 0
        if sec >= self.end:
            return n - 1
        p = (sec - self.start) / (self.end - self.start)
        return min(n - 1, max(0, int(p * n)))


SORT_WINDOW = SequenceWindow(SORT_CLICK_AT, SORT_CLICK_AT + SORT_ANIM_DUR, D_HOME_SORT)
EXPAND_WINDOW = SequenceWindow(EXPAND_CLICK_AT, EXPAND_CLICK_AT + EXPAND_ANIM_DUR, D_EXPAND)


def sort_cursor(btn_box: tuple[int, int, int, int]) -> CursorTrack:
    """游標從畫面右下方進場，斜向移到「最近出賽」按鈕上並點擊。"""
    bx, by, bw, bh = btn_box
    target = (bx + bw / 2, by + bh / 2)
    start = (target[0] + 1500, target[1] + 1250)
    return CursorTrack(
        start=start, end=target,
        move_at=SORT_MOVE_AT, move_dur=SORT_MOVE_DUR,
        click_at=SORT_CLICK_AT, hold_after=0.9, bow=0.20,
    )


def expand_cursor(arrow_box: tuple[int, int, int, int]) -> CursorTrack:
    """游標移到比賽列的展開箭頭並點擊。"""
    ax, ay, aw, ah = arrow_box
    target = (ax + aw / 2, ay + ah / 2)
    start = (target[0] + 1750, target[1] + 900)
    return CursorTrack(
        start=start, end=target,
        move_at=EXPAND_MOVE_AT, move_dur=EXPAND_MOVE_DUR,
        click_at=EXPAND_CLICK_AT, hold_after=0.8, bow=-0.18,
    )


# ── 鏡頭編排 ────────────────────────────────────────────────────
# 每個函式接收已擷取的底片，回傳排好運動的 Shot。

def shot_home(plate, camera):
    """首頁：頂部全景起手，緩慢下移展示整面卡片牆，最後推近三位 MLB 球員。"""
    size = (plate.width, plate.height)
    start = camera.View(config.PLATE_W / 2, config.PLATE_H / 2 - 60, 1.0)
    shot = camera.Shot(camera.static_source(plate.path), size, start)

    # 只推近前兩張 MLB 卡。三張卡橫跨整個內容區寬度，取景框會被寬度綁死在
    # zoom≈1.13，看起來和全景幾乎沒差別；縮到兩張才有真正的特寫感。
    mlb_pair = _merge(plate.box("card_1"), plate.box("card_2"))
    shot.hold(0.5)
    shot.drift(4.0, dy=0.55, dzoom=0.05)          # Ken Burns：只給呼吸感
    shot.to(camera.view_box(mlb_pair, size, padding=1.16), 1.6, arc=0.10)
    shot.hold(0.9)
    return shot


def shot_home_sort(seq, camera, prev_view):
    """排序切換：先退回看得見排序列的鏡位，點擊後靜靜看著卡片重排。"""
    size = (seq.width, seq.height)
    n = len(seq.paths)

    def source(t: float):
        return camera.load_plate(seq.paths[SORT_WINDOW.source_index(t, n)])

    shot = camera.Shot(source, size, prev_view)
    # 把排序列與前兩列卡片一起納入取景，點擊才有上下文
    frame_box = _merge(seq.boxes["sort_bar"], seq.boxes["card_3"])
    shot.to(camera.view_box(frame_box, size, padding=1.10), 1.2, arc=0.08)
    shot.hold(SORT_CLICK_AT + SORT_ANIM_DUR - 1.2)   # 游標移動 + 點擊 + 重排全程靜止鏡頭
    shot.drift(D_HOME_SORT - SORT_CLICK_AT - SORT_ANIM_DUR, dy=0.05, dzoom=0.02)
    return shot


def shot_advanced(plate, camera):
    """進階數據 → 球種分析：全段落一鏡到底，靠連續平移串起五個區塊。

    這是使用者特別要求「縮放之間必須順暢」的段落 —— 因為全部發生在同一張
    底片上，鏡頭移動不涉及任何重繪，中途不可能卡頓。
    """
    size = (plate.width, plate.height)
    shot = camera.Shot(
        camera.static_source(plate.path), size,
        camera.view_box(plate.box("statcast"), size),
    )
    shot.hold(1.2)
    shot.drift(2.0, dy=0.08)
    shot.to(camera.view_box(plate.box("discipline"), size), 2.2, arc=0.12)
    shot.hold(1.6)
    shot.drift(1.5, dy=0.06)
    # 跨越「擊球型態」區塊的長距離移動：弧度開大一點，先帶出全局再落點
    shot.to(camera.view_box(plate.box("arsenal_pitch"), size), 2.6, arc=0.16)
    shot.hold(1.8)
    shot.to(camera.view_box(plate.box("arsenal_result"), size), 1.8, arc=0.08)
    shot.hold(1.6)
    shot.to(camera.view_box(plate.box("arsenal_count"), size), 1.8, arc=0.08)
    shot.hold(2.0)
    shot.to(camera.view_box(plate.box("arsenal_all"), size, padding=1.06), 1.4)
    shot.hold(1.0)
    return shot


def shot_expand(seq, camera):
    """逐球展開：鏡頭守著比賽列不動，讓展開這件事自己成為主角。"""
    size = (seq.width, seq.height)
    n = len(seq.paths)

    def source(t: float):
        return camera.load_plate(seq.paths[EXPAND_WINDOW.source_index(t, n)])

    table_top = _top_slice(seq.boxes["table"], 1500)
    shot = camera.Shot(source, size, camera.view_box(table_top, size, padding=1.08))
    shot.hold(EXPAND_CLICK_AT)                      # 游標進場並移動到箭頭
    shot.drift(EXPAND_ANIM_DUR + 0.2, dy=0.06, dzoom=-0.03)   # 展開時極輕地讓開
    shot.hold(D_EXPAND - EXPAND_CLICK_AT - EXPAND_ANIM_DUR - 0.2)
    return shot


def shot_pitchlog(plate, camera, prev_view):
    """逐球表：推近看清每一球的數據，再水平移到最右的影片欄。"""
    size = (plate.width, plate.height)
    shot = camera.Shot(camera.static_source(plate.path), size, prev_view)

    rows = _top_slice(plate.box("pitch_table"), 1250)
    shot.hold(0.8)
    shot.to(camera.view_box(rows, size, padding=1.05), 1.8, arc=0.10)
    shot.hold(1.4)
    # 移向 Video 欄：只做水平位移，垂直維持不動，讀表的視線才不會被打斷
    video = plate.box("video_col")
    right = camera.view_box(
        (video[0] - 1500, rows[1], video[2] + 1500, rows[3]), size, padding=1.02
    )
    shot.to(right, 1.6, arc=0.05)
    shot.hold(1.4)
    return shot


def shot_plot(plate, camera):
    """數據圖表：球種位移圖 → 對角線移向 Pitch Plinko → 拉遠收全貌。"""
    size = (plate.width, plate.height)
    shot = camera.Shot(
        camera.static_source(plate.path), size,
        camera.view_box(plate.box("movement"), size, padding=1.10),
    )
    shot.hold(1.0)
    shot.drift(1.5, dzoom=0.04)
    shot.to(camera.view_box(plate.box("plinko"), size, padding=1.06), 2.4, arc=0.14)
    shot.hold(1.8)
    shot.to(camera.view_box(plate.box("charts_panel"), size, padding=1.02), 1.8)
    shot.hold(1.5)
    return shot


# ── 幾何小工具 ──────────────────────────────────────────────────

def _merge(a: tuple[int, int, int, int], b: tuple[int, int, int, int]):
    """合併兩個區域的外接矩形。"""
    x = min(a[0], b[0])
    y = min(a[1], b[1])
    return (x, y, max(a[0] + a[2], b[0] + b[2]) - x, max(a[1] + a[3], b[1] + b[3]) - y)


def _top_slice(box: tuple[int, int, int, int], height: int):
    """取區域的上緣一段。長表格只需要看到開頭，不必把整張塞進畫面。"""
    x, y, w, h = box
    return (x, y, w, min(h, height))

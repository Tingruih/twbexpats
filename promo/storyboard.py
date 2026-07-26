"""分鏡 —— 全片唯一的「劇本」。

要改節奏、改文案、改鏡位，只需要動這個檔案。

全片沒有章節字卡。段落與段落之間的過場，靠的是**游標按下分頁按鈕**：
鏡頭停在「分頁列貼齊畫面上緣」的同一個鏡位（見 `tab_view`），只把底片換成另一個
分頁的底片，看起來就是「按下去，內容換了」。這比任何轉場特效都更像真的在操作網站。

時間結構（轉場採重疊模型，最終長度 = 段落總和 − 轉場總和）：

    段落總和 82.4s − 轉場總和 2.2s ≈ 80.2s

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

OUTRO_URL = "tingruih.github.io/twbexpats"
OUTRO_TAGLINE = "每一位旅美球員的完整數據"

# ── 段落長度（秒）──────────────────────────────────────────────

D_INTRO = 6.0
D_HOME = 7.0
D_HOME_RETURN = 0.9    # 首頁下滑到底後，快速回到頂部銜接排序段
D_HOME_SORT = 3.65     # 點擊 + 卡片重排完成後立刻接球員卡 zoom，不再額外下移
D_HOME_CLICK = 2.3     # 推近鄧愷威的卡片並點擊
D_PROFILE = 4.0        # 點入他的球員頁面，鏡頭拉遠露出完整資料
D_PROFILE_TAB = 2.2    # 鏡頭退到分頁列，游標按下「進階數據」
D_GAMELOGS_INTRO = 1.8  # 按下「比賽紀錄」之後的落點，鏡頭下移到比賽列
D_EXPAND = 3.4         # 展開動畫完成後立刻接逐球表運鏡，不再等待
D_PITCHLOG = 3.2       # 保持完整逐球表鏡位，游標直接移到 Video 鍵並點擊
D_PITCH_VIDEO = 4.8    # 看完這一球，再按 × 關掉彈窗
D_PLOT_TAB = 2.3       # 快速上滑回分頁列，游標按下「數據圖表」
D_PLOT_TREND = 4.5     # 賽季走勢圖，游標按一下「數據」下拉
D_PLOT = 9.6           # 換好數據的走勢圖 → 球種使用與位移 → Pitch Plinko
D_OUTRO = 5.5

# 進階數據段落：五個停留點 + 球種分析的連續下滑 + 快速上滑回分頁列。
# 每一次 to() 結束的時刻就是該區塊字卡的進場時刻，因此下面的抵達時間全部由這些
# 常數推出來，改節奏時字卡不可能跟鏡頭脫節。
ADV_SETTLE = 1.2         # 分頁剛切過來，先讓畫面站穩
ADV_MOVE = 1.3           # 表格與表格之間的推近
ADV_HOLD = 1.5           # 每張表格的閱讀時間
ADV_ARSENAL_MOVE = 1.5   # 跨進球種分析區塊的長距離移動
ADV_ARSENAL_HOLD = 1.4
ADV_SCROLL = 4.2         # 球種數據 → 對戰結果 → 各球數配球比例，一鏡緩慢下滑到底
ADV_RETURN = 0.95        # 快速上滑回分頁列（比照 D_HOME_RETURN 的收回速度）
ADV_TAB_CLICK = 1.7      # 游標移到「比賽紀錄」並按下

ADV_AT_YEARLY = ADV_SETTLE + ADV_MOVE
ADV_AT_STATCAST = ADV_AT_YEARLY + ADV_HOLD + ADV_MOVE
ADV_AT_DISCIPLINE = ADV_AT_STATCAST + ADV_HOLD + ADV_MOVE
ADV_AT_BATTED = ADV_AT_DISCIPLINE + ADV_HOLD + ADV_MOVE
ADV_AT_ARSENAL = ADV_AT_BATTED + ADV_HOLD + ADV_ARSENAL_MOVE
ADV_AT_RETURNED = ADV_AT_ARSENAL + ADV_ARSENAL_HOLD + ADV_SCROLL + ADV_RETURN

D_ADVANCED = ADV_AT_RETURNED + ADV_TAB_CLICK

# 數據圖表段落內部的分段（抵達時刻同樣用來對齊字卡）
TREND_SETTLE = 1.0
TREND_MOVE = 1.4
TREND_AT = TREND_SETTLE + TREND_MOVE

PLOT_SETTLE = 1.3        # 交叉溶接完成，讓換好數據的走勢圖站定
PLOT_GRID_MOVE = 1.5
PLOT_GRID_HOLD = 2.0
PLOT_PLINKO_MOVE = 1.6
PLOT_PLINKO_HOLD = 1.9
PLOT_PULLBACK = 1.3

PLOT_AT_GRID = PLOT_SETTLE + PLOT_GRID_MOVE
PLOT_AT_PLINKO = PLOT_AT_GRID + PLOT_GRID_HOLD + PLOT_PLINKO_MOVE

# ── 轉場 ────────────────────────────────────────────────────────
# 只剩四處需要轉場；分頁切換一律不轉場，那是同一個鏡位換底片。

T_HOME = Transition(transitions.slide_up_soft, 0.7)
T_PROFILE = Transition(transitions.crossfade, 0.35)
# 賽季走勢圖換數據：兩張底片除了圖表以外完全相同，短交叉溶接讀起來就是圖表重畫
T_TREND_SWAP = Transition(transitions.crossfade, 0.35)
T_OUTRO = Transition(transitions.pull_back_blur, 0.8)

# ── 說明條 ──────────────────────────────────────────────────────

CAPTIONS_HOME = [
    Caption("25 位旅美球員，一頁掌握", "MLB · AAA · AA · A+ · A · ROK", at=1.1, dur=4.4),
]
CAPTIONS_HOME_SORT = [
    # at 對齊 SORT_MOVE_AT（游標開始滑動的時刻）——說明條應與游標動作同時出現，
    # 不必等點擊、重排都結束才現身。
    Caption("一鍵切換排序", "依層級，或依最近出賽", at=1.4, dur=2.9),
]
CAPTIONS_PROFILE = [
    Caption("完整球員檔案", "個人資料 · 下場賽程 · 異動紀錄 · 生涯數據", at=0.5, dur=3.0),
]
# 進階數據的每一張說明條都掛在「鏡頭抵達該表格」的那一刻，不早也不晚。
CAPTIONS_ADVANCED = [
    Caption("歷年進階數據", "WHIP · K/9 · K% · BB% · BABIP · GO/AO",
            at=ADV_AT_YEARLY, dur=3.2),
    Caption("Statcast 進階指標", "FIP · xwOBA · Barrel% · 平均擊球初速",
            at=ADV_AT_STATCAST, dur=3.2),
    Caption("選球能力全解析", "Chase% · Whiff% · CSW%",
            at=ADV_AT_DISCIPLINE, dur=3.2),
    Caption("擊球型態", "滾地 · 平飛 · 飛球比例，以及拉打與反方向分布",
            at=ADV_AT_BATTED, dur=3.2),
    # 這一張要陪著鏡頭走完整段下滑（球種數據 → 對戰結果 → 各球數配球比例）
    Caption("投球球種分析", "用量 · 球速 · 位移 · 轉速 · 各球數配球比例",
            at=ADV_AT_ARSENAL, dur=4.4),
]
# 展開逐球紀錄時，游標一開始移動，說明條就同步進場。
CAPTIONS_EXPAND = [
    Caption("每一球的完整數據", "球種 · 球速 · 進壘區 · 位移 · 轉速", at=0.75, dur=2.5),
]

# 影片說明條與游標同時進場，並一路留到鏡頭停在播放視窗上 —— 它橫跨了
# 「逐球表」與「影片」兩個段落。
CAP_VIDEO = Caption("直接看該球影片", "站內直接播放 MLB 官方影片", at=1.8, dur=3.4)

CAPTIONS_PITCHLOG = [
    CAP_VIDEO,
]
# 同一條說明的下半截。段落交界把它切成兩段，用負的 at 表示「上一段就已進場」，
# 疊加時算出來的 elapsed 因此能跨過交界連續下去。
CAPTIONS_PITCH_VIDEO = [
    Caption(CAP_VIDEO.main, CAP_VIDEO.sub, at=CAP_VIDEO.at - D_PITCHLOG, dur=CAP_VIDEO.dur),
]

# 賽季走勢圖的說明條同樣跨段落：進場在「換數據前」，尾巴留到交叉溶接之後。
CAP_TREND = Caption("賽季走勢圖", "逐場數據走勢，十二項指標任意切換", at=TREND_AT, dur=3.6)

CAPTIONS_PLOT_TREND = [
    CAP_TREND,
]
CAPTIONS_PLOT = [
    Caption(CAP_TREND.main, CAP_TREND.sub, at=CAP_TREND.at - D_PLOT_TREND, dur=CAP_TREND.dur),
    # 使用率與位移兩張圖並排，共用一張說明條
    Caption("球種使用與位移", "對左右打的配球差異，以及每一球的位移分布",
            at=PLOT_AT_GRID, dur=3.4),
    Caption("Pitch Plinko", "球數推進過程中的配球變化",
            at=PLOT_AT_PLINKO, dur=3.2),
]

ALL_CAPTIONS = (
    CAPTIONS_HOME + CAPTIONS_HOME_SORT + CAPTIONS_PROFILE + CAPTIONS_ADVANCED
    + CAPTIONS_EXPAND + CAPTIONS_PITCHLOG + CAPTIONS_PITCH_VIDEO
    + CAPTIONS_PLOT_TREND + CAPTIONS_PLOT
)

# ── 互動時間點 ──────────────────────────────────────────────────

# 首頁排序：游標進場 → 移到「最近出賽」→ 點擊 → 卡片重排
SORT_MOVE_AT = 1.4
SORT_MOVE_DUR = 1.05
SORT_CLICK_AT = 2.45
SORT_ANIM_DUR = 1.2

# 首頁點擊球員卡：卡片重排底定後，游標移到鄧愷威的卡片並點擊，帶出他的頁面
CLICK_MOVE_AT = 0.5
CLICK_MOVE_DUR = 0.9
CLICK_CLICK_AT = 1.5

# 逐球展開：游標移到展開箭頭 → 點擊 → 表格展開
EXPAND_MOVE_AT = 0.75
EXPAND_MOVE_DUR = 1.0
EXPAND_CLICK_AT = 1.95
EXPAND_ANIM_DUR = 1.25

# 逐球影片：完整逐球表鏡位停定後，游標移到 ▶ 並按下，隨即切到影片段落
VIDEO_MOVE_AT = 1.8
VIDEO_MOVE_DUR = 0.8
VIDEO_CLICK_AT = 2.65

# 看完影片後，游標移到彈窗右上角的 × 把它關掉
CLOSE_MOVE_AT = 2.85
CLOSE_MOVE_DUR = 0.8
CLOSE_CLICK_AT = 3.8

# 三次分頁點擊。時間全部安排在鏡頭抵達分頁列鏡位「之後」——
# 按鈕要先在畫面上站定，游標才按得下去。
TAB_ADVANCED_AT = (0.30, 0.85, 1.35)    # (進場, 移動時長, 點擊)
TAB_GAMELOGS_AT = (ADV_AT_RETURNED + 0.05, 0.80, ADV_AT_RETURNED + 1.00)
TAB_PLOT_AT = (0.75, 0.80, 1.65)

# 賽季走勢圖：游標按一下「數據」下拉，圖表隨即換成另一項指標
TREND_MOVE_AT = 2.45
TREND_MOVE_DUR = 0.80
TREND_CLICK_AT = 3.40


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


# ── 游標軌跡 ────────────────────────────────────────────────────

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


def feature_click_cursor(card_box: tuple[int, int, int, int]) -> CursorTrack:
    """游標從左下方進場，移到鄧愷威的球員卡並點擊。"""
    bx, by, bw, bh = card_box
    target = (bx + bw / 2, by + bh / 2)
    start = (target[0] - 1300, target[1] + 950)
    return CursorTrack(
        start=start, end=target,
        move_at=CLICK_MOVE_AT, move_dur=CLICK_MOVE_DUR,
        click_at=CLICK_CLICK_AT, hold_after=0.3, bow=0.16,
    )


def tab_cursor(
    tab_box: tuple[int, int, int, int],
    timing: tuple[float, float, float],
    offset: tuple[float, float] = (-1400, 1050),
    bow: float = 0.16,
    hold_after: float = 0.25,
) -> CursorTrack:
    """游標移到某個分頁按鈕上並按下。

    三次分頁切換共用這個函式，只換進場方向與弧度 —— 動作一致，但不會看起來
    像同一段動畫被複製三次。
    """
    tx, ty, tw, th = tab_box
    target = (tx + tw / 2, ty + th / 2)
    move_at, move_dur, click_at = timing
    return CursorTrack(
        start=(target[0] + offset[0], target[1] + offset[1]), end=target,
        move_at=move_at, move_dur=move_dur,
        click_at=click_at, hold_after=hold_after, bow=bow,
    )


def pitch_video_cursor(btn_box: tuple[int, int, int, int]) -> CursorTrack:
    """游標從左下方進場，移到逐球表的 ▶ 鈕並按下，把影片叫出來。"""
    bx, by, bw, bh = btn_box
    target = (bx + bw / 2, by + bh / 2)
    start = (target[0] - 1600, target[1] + 1050)
    return CursorTrack(
        start=start, end=target,
        move_at=VIDEO_MOVE_AT, move_dur=VIDEO_MOVE_DUR,
        click_at=VIDEO_CLICK_AT, hold_after=0.1, bow=-0.14,
    )


def close_video_cursor(close_box: tuple[int, int, int, int]) -> CursorTrack:
    """看完球之後，游標從左下方移到彈窗右上角的 × 並按下。"""
    cx, cy, cw, ch = close_box
    target = (cx + cw / 2, cy + ch / 2)
    start = (target[0] - 1100, target[1] + 900)
    return CursorTrack(
        start=start, end=target,
        move_at=CLOSE_MOVE_AT, move_dur=CLOSE_MOVE_DUR,
        click_at=CLOSE_CLICK_AT, hold_after=0.2, bow=0.18,
    )


def trend_stat_cursor(select_box: tuple[int, int, int, int]) -> CursorTrack:
    """游標移到賽季走勢圖的「數據」下拉並按一下。"""
    sx, sy, sw, sh = select_box
    target = (sx + sw / 2, sy + sh / 2)
    start = (target[0] + 1200, target[1] + 950)
    return CursorTrack(
        start=start, end=target,
        move_at=TREND_MOVE_AT, move_dur=TREND_MOVE_DUR,
        click_at=TREND_CLICK_AT, hold_after=0.15, bow=-0.16,
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


# ── 共用鏡位 ────────────────────────────────────────────────────

# 分頁列上方留的空隙（底片像素）。分頁列剛好貼在畫面上緣下方一點點，
# 下方正好容得下一整張表格。
TAB_VIEW_LEAD = 46

# 下滑到表格底部時，底緣不要與畫面切齊，留一點餘裕
BOTTOM_MARGIN = 60


def page_top_view(camera):
    """頁面最頂端的取景：站台標頭 + 球員 hero + 分頁列 + 下方內容的開頭。

    這是「資料頁 → 進階數據」那一次分頁切換的會合鏡位。之所以不能沿用
    `tab_view`，是因為球員資料頁的長底片只有 2160 高（內容剛好一屏），
    `clamp_view` 會把任何低於頁首的鏡位夾回這裡；進階數據的長底片有 9468 高，
    夾不到。兩邊各自算的話就會在切換的瞬間跳掉半個畫面。

    這個鏡位完全不依賴底片尺寸，因此兩段必定對齊。
    """
    return camera.View(config.PLATE_W / 2, config.PLATE_H / 2, 1.0)


def tab_view(tab_nav_box: tuple[int, int, int, int], size, camera):
    """「分頁列貼齊畫面上緣」的取景 —— 兩次快速上滑的回程落點。

    分頁列在每一張球員頁底片上的 y 座標都相同（它在 hero 底下、分頁面板之上），
    所以這個鏡位在不同分頁的底片之間可以直接沿用，切換時完全不會位移。
    只用在夠長的底片上（進階數據、比賽紀錄、數據圖表），不會被夾。
    zoom 固定 1.0，取景框恰好等於一個 viewport，構圖與真的在瀏覽網站一致。
    """
    _, y, _, _ = tab_nav_box
    return camera.clamp_view(
        camera.View(config.PLATE_W / 2, y - TAB_VIEW_LEAD + config.PLATE_H / 2, 1.0),
        size,
    )


def expand_start_view(seq, camera):
    """逐球展開的鏡位：比賽表上緣。

    刻意算在**展開序列**（viewport 底片，只有一屏高）的座標系上。序列比長底片矮，
    `clamp_view` 的可動範圍也更窄；若改用長底片來算，兩者會夾出不同的結果，
    段落交界就會出現一次位移。反過來（用序列算、套到長底片上）則永遠安全。
    """
    size = (seq.width, seq.height)
    return camera.view_box(_top_slice(seq.boxes["table"], 1500), size, padding=1.08)


def pitch_rows_view(seq, camera):
    """按下 ▶ 之前的取景：完整逐球表前段，連同最右的 Video 欄。

    取景刻意算在**影片序列**（viewport 底片）的座標系上，再換算回長底片，
    讓點擊前後保持完全相同的鏡位，只切換影片彈窗的顯示狀態。
    """
    size = (seq.width, seq.height)
    rows = _top_slice(seq.boxes["pitch_table"], 1250)
    return camera.view_box(rows, size, padding=1.05)


def video_box_view(seq, camera):
    """播放視窗的取景。關掉彈窗之後的下一段要從這個位置接手，因此獨立成一個函式。"""
    size = (seq.width, seq.height)
    return camera.view_box(seq.boxes["video_box"], size, padding=1.08)


def trend_view(plate, camera):
    """賽季走勢圖的取景。換數據前後的兩張底片都用它，交叉溶接才不會位移。"""
    size = (plate.width, plate.height)
    return camera.view_box(plate.box("trend"), size, padding=1.06)


# ── 鏡頭編排 ────────────────────────────────────────────────────
# 每個函式接收已擷取的底片，回傳排好運動的 Shot。

def shot_home(plate, camera):
    """首頁：頂部全景起手，緩慢下移展示整面卡片牆，最後快速收回頂部。

    收回頂部不是裝飾，是接縫的必要條件：下一段「排序切換」用的是 viewport 底片，
    只涵蓋頁面最上面一屏。鏡頭若停在下滑後的位置，切段時取景會被強制夾回頂部，
    畫面就出現一次硬切。這裡自己走完回程，兩段的取景才完全對齊。
    """
    size = (plate.width, plate.height)
    # 起手即頁面頂部（PLATE_H / 2 是取景框貼齊上緣時的中心），也是回程的終點
    top = camera.View(config.PLATE_W / 2, config.PLATE_H / 2, 1.0)
    shot = camera.Shot(camera.static_source(plate.path), size, top)

    shot.hold(0.5)
    shot.drift(D_HOME - 0.5 - D_HOME_RETURN, dy=0.55, dzoom=0.05)   # Ken Burns：只給呼吸感
    # 回程比去程快六倍，讀起來是「一把收回」而非又一次緩慢運鏡；收尾速度為零，
    # 緊接著排序段的推近才不會有速度斷點。
    shot.to(top, D_HOME_RETURN)
    return shot


def shot_home_sort(seq, camera, prev_view):
    """排序切換：先退回看得見排序列的鏡位，點擊後看著卡片重排。"""
    size = (seq.width, seq.height)
    n = len(seq.paths)

    def source(t: float):
        return camera.load_plate(seq.paths[SORT_WINDOW.source_index(t, n)])

    shot = camera.Shot(source, size, prev_view)
    # 把排序列與前兩列卡片一起納入取景，點擊才有上下文
    frame_box = _merge(seq.boxes["sort_bar"], seq.boxes["card_3"])
    shot.to(camera.view_box(frame_box, size, padding=1.10), 1.2, arc=0.08)
    shot.hold(SORT_CLICK_AT + SORT_ANIM_DUR - 1.2)   # 游標移動 + 點擊 + 重排全程靜止鏡頭
    return shot


def shot_home_click(seq, camera, prev_view):
    """卡片重排底定後，鏡頭推近鄧愷威的卡片，準備點擊進入他的頁面。"""
    size = (seq.width, seq.height)
    shot = camera.Shot(camera.static_source(seq.paths[-1]), size, prev_view)
    shot.to(camera.view_box(seq.boxes["card_feature"], size, padding=1.2), 1.1, arc=0.06)
    shot.hold(D_HOME_CLICK - 1.1)
    return shot


def shot_profile_reveal(plate, camera):
    """點入球員頁面：鏡頭先貼著頭像特寫，隨後拉遠露出完整資料卡片牆。"""
    size = (plate.width, plate.height)
    start = camera.view_box(plate.box("avatar"), size, padding=1.5)
    shot = camera.Shot(camera.static_source(plate.path), size, start)

    frame_box = _merge(plate.box("hero"), plate.box("bio_grid"))
    shot.to(camera.view_box(frame_box, size, padding=1.08), 1.8, arc=0.05)
    shot.hold(D_PROFILE - 1.8)
    return shot


PROFILE_TAB_MOVE = 1.1


def shot_profile_tab(plate, camera, prev_view):
    """資料頁看完，鏡頭退到頁面頂端，游標按下「進階數據」。"""
    size = (plate.width, plate.height)
    shot = camera.Shot(camera.static_source(plate.path), size, prev_view)
    shot.to(page_top_view(camera), PROFILE_TAB_MOVE, arc=0.05)
    shot.hold(D_PROFILE_TAB - PROFILE_TAB_MOVE)
    return shot


def shot_advanced(plate, camera):
    """進階數據：五個表格逐一推近，再一鏡下滑走完球種分析，最後收回分頁列。

    全段落發生在同一張長底片上，鏡頭移動不涉及任何重繪，中途不可能卡頓。
    起手鏡位與上一段收尾完全相同（都是 `page_top_view`），所以兩段之間不需要轉場 ——
    觀眾看到的是「按下進階數據，同樣高度的畫面上內容換了」，接著才推近第一張表。
    """
    size = (plate.width, plate.height)
    shot = camera.Shot(camera.static_source(plate.path), size, page_top_view(camera))

    shot.hold(ADV_SETTLE)
    for key in ("yearly", "statcast", "discipline", "batted_ball"):
        shot.to(camera.view_box(plate.box(key), size), ADV_MOVE, arc=0.06)
        shot.hold(ADV_HOLD)

    # 球種分析：推近第一張表之後，維持同樣的縮放一路緩慢下滑，
    # 讓「球種數據 → 對戰結果 → 各球數配球比例」在同一次移動裡走完。
    arsenal = camera.view_box(plate.box("arsenal_pitch"), size, padding=1.06)
    shot.to(arsenal, ADV_ARSENAL_MOVE, arc=0.14)
    shot.hold(ADV_ARSENAL_HOLD)
    shot.to(_bottom_view(plate.box("arsenal_count"), arsenal, size, camera),
            ADV_SCROLL, ease=easing.smoothstep)

    # 比照首頁 0:12 的收回：回程遠快於去程，讀起來是「一把拉回頁首」。
    # 落點是分頁列貼齊上緣的鏡位 —— 下一段（比賽紀錄）也從這裡起手。
    shot.to(tab_view(plate.box("tab_nav"), size, camera), ADV_RETURN)
    shot.hold(ADV_TAB_CLICK)
    return shot


GAMELOGS_SETTLE = 0.5


def shot_gamelogs_intro(plate, seq, camera):
    """按下「比賽紀錄」之後的落點：鏡頭停在分頁列，再下移到比賽列。"""
    size = (plate.width, plate.height)
    shot = camera.Shot(
        camera.static_source(plate.path), size,
        tab_view(plate.box("tab_nav"), size, camera),
    )
    shot.hold(GAMELOGS_SETTLE)
    shot.to(expand_start_view(seq, camera), D_GAMELOGS_INTRO - GAMELOGS_SETTLE, arc=0.06)
    return shot


def shot_expand(seq, camera):
    """逐球展開：鏡頭守著比賽列不動，讓展開這件事自己成為主角。"""
    size = (seq.width, seq.height)
    n = len(seq.paths)

    def source(t: float):
        return camera.load_plate(seq.paths[EXPAND_WINDOW.source_index(t, n)])

    shot = camera.Shot(source, size, expand_start_view(seq, camera))
    shot.hold(EXPAND_CLICK_AT)                      # 游標進場並移動到箭頭
    shot.drift(EXPAND_ANIM_DUR + 0.2, dy=0.06, dzoom=-0.03)   # 展開時極輕地讓開
    return shot


def shot_pitchlog(plate, camera, prev_view, video_seq):
    """逐球表：展開後立即推近完整表格，保持鏡位並直接點擊 Video 鍵。"""
    size = (plate.width, plate.height)
    shot = camera.Shot(camera.static_source(plate.path), size, prev_view)

    target = _from_seq(pitch_rows_view(video_seq, camera), video_seq.origin_y, camera)
    shot.to(target, 1.8, arc=0.10)
    shot.hold(D_PITCHLOG - 1.8)   # 保持完整表格鏡位，游標移到 ▶ 並按下
    return shot


VIDEO_SETTLE = 0.4
VIDEO_MOVE = 1.5


def shot_pitch_video(seq, camera):
    """影片彈窗蓋上畫面後，鏡頭順著滑向左邊的播放視窗，把這一球看完。

    起手取景與上一段的收尾完全相同（同一個 pitch_rows_view），交界因此只換了
    底片、沒換鏡位 —— 觀眾看到的就是「按下去，影片跳出來」。收尾則停在播放視窗上
    讓游標去按 ×，關掉之後由下一段從同一個鏡位接手。
    """
    size = (seq.width, seq.height)
    shot = camera.Shot(camera.sequence_source(seq.paths), size, pitch_rows_view(seq, camera))

    shot.hold(VIDEO_SETTLE)                         # 彈窗剛蓋上，讓它站穩
    shot.to(video_box_view(seq, camera), VIDEO_MOVE, arc=0.06)
    shot.hold(D_PITCH_VIDEO - VIDEO_SETTLE - VIDEO_MOVE)   # 停住看球，最後按下 ×
    return shot


PLOT_TAB_RETURN = 0.95


def shot_plot_tab(plate, camera, video_seq):
    """× 按下、彈窗消失，鏡頭快速上滑回分頁列，游標按下「數據圖表」。

    起手鏡位就是上一段停住的播放視窗位置，只是底片換成了沒有彈窗的逐球表 ——
    彈窗因此是「被關掉」而不是「被切掉」。
    """
    size = (plate.width, plate.height)
    start = _from_seq(video_box_view(video_seq, camera), video_seq.origin_y, camera)
    shot = camera.Shot(camera.static_source(plate.path), size, start)

    shot.to(tab_view(plate.box("tab_nav"), size, camera), PLOT_TAB_RETURN)
    shot.hold(D_PLOT_TAB - PLOT_TAB_RETURN)
    return shot


def shot_plot_trend(plate, camera):
    """數據圖表：分頁切過來，推近賽季走勢圖，游標按一下「數據」下拉。"""
    size = (plate.width, plate.height)
    shot = camera.Shot(
        camera.static_source(plate.path), size,
        tab_view(plate.box("tab_nav"), size, camera),
    )
    shot.hold(TREND_SETTLE)
    shot.to(trend_view(plate, camera), TREND_MOVE, arc=0.06)
    shot.hold(D_PLOT_TREND - TREND_SETTLE - TREND_MOVE)
    return shot


def shot_plot(plate, camera):
    """換好數據的走勢圖 → 球種使用與位移（兩張圖一起）→ Pitch Plinko → 拉遠收全貌。

    起手鏡位與上一段完全相同，兩段之間只有一次 0.35 秒的交叉溶接，
    看起來就是同一個畫面上的圖表被重畫了。
    """
    size = (plate.width, plate.height)
    shot = camera.Shot(camera.static_source(plate.path), size, trend_view(plate, camera))

    shot.hold(PLOT_SETTLE)
    shot.to(camera.view_box(plate.box("chart_grid"), size, padding=1.04),
            PLOT_GRID_MOVE, arc=0.10)
    shot.hold(PLOT_GRID_HOLD)
    shot.to(camera.view_box(plate.box("plinko"), size, padding=1.06),
            PLOT_PLINKO_MOVE, arc=0.12)
    shot.hold(PLOT_PLINKO_HOLD)
    # 最後的拉遠不接 hold —— 收尾那 0.8 秒正好被結尾卡的轉場吃掉
    shot.to(camera.view_box(plate.box("charts_panel"), size, padding=1.02), PLOT_PULLBACK)
    return shot


# ── 幾何小工具 ──────────────────────────────────────────────────

def _merge(a: tuple[int, int, int, int], b: tuple[int, int, int, int]):
    """合併兩個區域的外接矩形。"""
    x = min(a[0], b[0])
    y = min(a[1], b[1])
    return (x, y, max(a[0] + a[2], b[0] + b[2]) - x, max(a[1] + a[3], b[1] + b[3]) - y)


def _from_seq(view, origin_y: int, camera):
    """把 viewport 序列座標系的取景位置，換算回同一頁長底片的座標系。"""
    return camera.View(view.cx, view.cy + origin_y, view.zoom)


def _top_slice(box: tuple[int, int, int, int], height: int):
    """取區域的上緣一段。長表格只需要看到開頭，不必把整張塞進畫面。"""
    x, y, w, h = box
    return (x, y, w, min(h, height))


def _bottom_view(box: tuple[int, int, int, int], ref, size, camera):
    """維持 `ref` 的水平位置與縮放，把取景框下緣對齊 `box` 的底部。

    縮放不變是關鍵：這樣從 `ref` 移動到這裡就是一次純粹的垂直平移，
    讀起來是「往下捲」，而不是又一次推近拉遠。
    """
    _, y, _, h = box
    _, ch = ref.crop_size()
    return camera.clamp_view(
        camera.View(ref.cx, y + h + BOTTOM_MARGIN - ch / 2, ref.zoom), size
    )

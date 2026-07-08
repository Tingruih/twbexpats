"""圖表主題 — 全站 matplotlib 圖表外觀的單一事實來源。

深色單一主題（網站無亮色模式）。色票取自 dataviz 參考色盤 dark 欄，
已驗證於本站表面 #18181b：全數 WCAG 對比 ≥3:1；相鄰 CVD ΔE 屬 floor
band，故散點圖一律以標記形狀作第二編碼。圖內文字一律英文
（CI 無 CJK 字型）。
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 必須在 pyplot import 之前；CI 無 display
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from ..constants import CALLED_STRIKE_CODES, WHIFF_CODES  # noqa: E402

CHART_DPI = 180

# ── 網站 tokens（src/static/css/base.css）──
SURFACE = "#18181b"
INK_1 = "#fafafa"
INK_2 = "#a1a1aa"
INK_3 = "#71717a"
GRID = "#27272a"
BASELINE = "#3f3f46"
ACCENT = "#14b8a6"
NEUTRAL = "#71717a"
MASK_FILL = "#232327"

# ── 類別色票（dataviz dark 欄，見 plan §0.5）──
SLOT_BLUE = "#3987e5"
SLOT_AQUA = "#199e70"
SLOT_YELLOW = "#c98500"
SLOT_GREEN = "#008300"
SLOT_VIOLET = "#9085e9"
SLOT_RED = "#e66767"
SLOT_MAGENTA = "#d55181"
SLOT_ORANGE = "#d95926"

# 球種→顏色固定註冊表：色跟實體走，全站一致（不按使用率輪派）。
PITCH_TYPE_COLORS = {
    "FF": SLOT_RED, "FA": SLOT_RED,
    "SI": SLOT_ORANGE, "FT": SLOT_ORANGE,
    "FC": SLOT_MAGENTA,
    "SL": SLOT_BLUE,
    "ST": SLOT_AQUA, "SV": SLOT_AQUA,
    "CU": SLOT_VIOLET, "KC": SLOT_VIOLET, "CS": SLOT_VIOLET,
    "CH": SLOT_GREEN, "SC": SLOT_GREEN,
    "FS": SLOT_YELLOW, "FO": SLOT_YELLOW,
}

TRAJECTORY_COLORS = {
    "gb": SLOT_YELLOW, "ld": SLOT_RED, "fb": SLOT_BLUE, "pu": SLOT_VIOLET,
}

# 順序色階：深色表面上高值＝亮端（plan §0.5）
SEQ_CMAP = LinearSegmentedColormap.from_list(
    "seq_dark",
    ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"],
)
DIV_CMAP = LinearSegmentedColormap.from_list(
    "div_dark", ["#3987e5", "#383835", "#e66767"]
)

# 結果→標記形狀固定表（散點圖的 CVD 第二編碼）
RESULT_MARKERS = (
    ("inplay", "D", "In play"),
    ("whiff", "X", "Whiff"),
    ("called", "s", "Called strike"),
    ("foul", "^", "Foul"),
    ("ball", "o", "Ball"),
)
FOUL_CODES = {"F", "L", "R"}

PA_EVENT_ABBREV = {
    "single": "1B", "double": "2B", "triple": "3B", "home_run": "HR",
    "strikeout": "K", "strikeout_double_play": "K",
    "walk": "BB", "intent_walk": "IBB", "hit_by_pitch": "HBP",
    "field_out": "OUT", "force_out": "OUT", "fielders_choice_out": "FC",
    "fielders_choice": "FC", "grounded_into_double_play": "GDP",
    "double_play": "DP", "sac_fly": "SF", "sac_bunt": "SAC",
    "field_error": "E",
}


def pitch_color(ptype) -> str:
    return PITCH_TYPE_COLORS.get(ptype or "", NEUTRAL)


def result_class(p: dict) -> str:
    if p.get("is_in_play"):
        return "inplay"
    code = p.get("result_code", "")
    if code in WHIFF_CODES:
        return "whiff"
    if code in CALLED_STRIKE_CODES:
        return "called"
    if code in FOUL_CODES:
        return "foul"
    return "ball"


def style_axes(ax):
    ax.set_facecolor(SURFACE)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.tick_params(colors=INK_3, labelsize=8)
    ax.xaxis.label.set_color(INK_2)
    ax.yaxis.label.set_color(INK_2)
    ax.title.set_color(INK_1)
    ax.title.set_fontsize(10)
    ax.grid(color=GRID, linewidth=0.6, alpha=0.6)


def new_fig(width: float = 6.0, height: float = 4.5):
    fig, ax = plt.subplots(figsize=(width, height), facecolor=SURFACE)
    style_axes(ax)
    return fig, ax


def styled_legend(ax, handles, loc: str, fontsize: int = 7):
    """統一圖例外觀（深色底、細框、次要墨色字）。"""
    leg = ax.legend(
        handles=handles, loc=loc, fontsize=fontsize,
        facecolor=SURFACE, edgecolor=GRID, labelcolor=INK_2,
        framealpha=0.9, borderpad=0.6,
    )
    return leg


def save_chart(fig, out_path: Path) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        out_path, dpi=CHART_DPI, facecolor=fig.get_facecolor(),
        bbox_inches="tight", pad_inches=0.2,
    )
    plt.close(fig)

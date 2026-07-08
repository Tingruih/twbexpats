"""本壘板視角（捕手方向）逐球位置圖。"""

from collections import Counter
from pathlib import Path

from matplotlib.lines import Line2D
from matplotlib.patches import Polygon, Rectangle

from ..stats.recent.derived import (
    DEFAULT_SZ_BOT,
    DEFAULT_SZ_TOP,
    PLATE_HALF_WIDTH_FT,
)
from ..util.numbers import float_or_none, mean
from .style import (
    GRID,
    INK_2,
    INK_3,
    PA_EVENT_ABBREV,
    RESULT_MARKERS,
    SURFACE,
    new_fig,
    pitch_color,
    result_class,
    save_chart,
    styled_legend,
)


def _zone_bounds(pitches):
    top = mean([float_or_none(p.get("strike_zone_top")) for p in pitches])
    bot = mean([float_or_none(p.get("strike_zone_bottom")) for p in pitches])
    return top or DEFAULT_SZ_TOP, bot or DEFAULT_SZ_BOT


def draw_strike_zone(ax, top: float, bot: float):
    half = PLATE_HALF_WIDTH_FT
    ax.add_patch(Rectangle((-half, bot), 2 * half, top - bot,
                           fill=False, edgecolor=INK_2, linewidth=1.4, zorder=2))
    for frac in (1 / 3, 2 / 3):
        x = -half + frac * 2 * half
        ax.plot([x, x], [bot, top], color=GRID, lw=0.8, zorder=1)
        y = bot + frac * (top - bot)
        ax.plot([-half, half], [y, y], color=GRID, lw=0.8, zorder=1)
    # 本壘板五邊形（尖端朝下＝朝捕手，定向用）
    plate = [(-half, 0.42), (half, 0.42), (half, 0.28), (0.0, 0.1), (-half, 0.28)]
    ax.add_patch(Polygon(plate, closed=True, facecolor=GRID,
                         edgecolor=INK_3, linewidth=0.8, zorder=1))


def render_game_pitch_map(pitches, out_path: Path, *, title: str = "") -> bool:
    pts = [
        p for p in pitches
        if float_or_none(p.get("px")) is not None
        and float_or_none(p.get("pz")) is not None
    ]
    if not pts:
        return False
    top, bot = _zone_bounds(pts)

    fig, ax = new_fig(5.4, 6.0)
    ax.grid(False)
    draw_strike_zone(ax, top, bot)

    type_counts = Counter(p.get("pitch_type") or "UN" for p in pts)
    for p in pts:
        color = pitch_color(p.get("pitch_type"))
        cls = result_class(p)
        marker = next(m for c, m, _ in RESULT_MARKERS if c == cls)
        if cls == "ball":
            ax.scatter(p["px"], p["pz"], marker=marker, s=52,
                       facecolors="none", edgecolors=color,
                       linewidths=1.2, zorder=3)
        else:
            ax.scatter(p["px"], p["pz"], marker=marker, s=58,
                       color=color, edgecolors=SURFACE,
                       linewidths=0.7, zorder=3)
        if p.get("is_pa_final") and p.get("is_in_play"):
            label = PA_EVENT_ABBREV.get(p.get("pa_event") or "", "")
            if label:
                ax.annotate(label, (p["px"], p["pz"]),
                            xytext=(5, 5), textcoords="offset points",
                            fontsize=7, color=INK_2, zorder=4)

    if len(pts) < len(pitches):
        ax.text(0.02, 0.02, f"{len(pts)}/{len(pitches)} pitches tracked",
                transform=ax.transAxes, fontsize=7, color=INK_3)

    type_handles = [
        Line2D([], [], marker="o", linestyle="", color=pitch_color(t),
               label=f"{t} ({n})")
        for t, n in type_counts.most_common()
    ]
    result_handles = [
        Line2D([], [], marker=m, linestyle="", color=INK_2, label=lab)
        for _, m, lab in RESULT_MARKERS
    ]
    leg1 = styled_legend(ax, type_handles, "upper left")
    ax.add_artist(leg1)
    styled_legend(ax, result_handles, "upper right")

    ax.set_xlim(-2.2, 2.2)
    ax.set_ylim(0.0, 4.8)
    ax.set_aspect("equal")
    ax.set_xlabel("Horizontal (ft, catcher's view)")
    ax.set_ylabel("Height (ft)")
    if title:
        ax.set_title(title)
    save_chart(fig, out_path)
    return True

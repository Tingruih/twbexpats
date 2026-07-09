"""單場 HB/IVB 位移圖，疊本季分佈 ghost（灰點＋每球種 2σ 橢圓）。"""

import math
from pathlib import Path

from matplotlib.lines import Line2D
from matplotlib.patches import Ellipse

from ..util.numbers import float_or_none
from .style import (
    BASELINE,
    INK_3,
    SURFACE,
    new_fig,
    pitch_color,
    save_chart,
    styled_legend,
)

MIN_ELLIPSE_N = 5


def _movement_points(pitches):
    pts = []
    for p in pitches:
        hb, ivb = float_or_none(p.get("hb")), float_or_none(p.get("ivb"))
        if hb is not None and ivb is not None:
            pts.append((p.get("pitch_type") or "UN", hb, ivb))
    return pts


def _mean_std(values):
    n = len(values)
    m = sum(values) / n
    var = sum((v - m) ** 2 for v in values) / n
    return m, math.sqrt(var)


def render_game_movement(game_pitches, season_pitches, out_path: Path, *,
                         title: str = "") -> bool:
    game_pts = _movement_points(game_pitches)
    if not game_pts:
        return False
    season_pts = _movement_points(season_pitches)

    fig, ax = new_fig(5.6, 5.2)
    ax.axhline(0, color=BASELINE, lw=0.9, zorder=1)
    ax.axvline(0, color=BASELINE, lw=0.9, zorder=1)

    if season_pts:
        ax.scatter([x for _, x, _ in season_pts], [y for _, _, y in season_pts],
                   s=7, color=INK_3, alpha=0.3, linewidths=0, zorder=2)
        by_type: dict[str, list[tuple[float, float]]] = {}
        for t, x, y in season_pts:
            by_type.setdefault(t, []).append((x, y))
        for t, pts in by_type.items():
            if len(pts) < MIN_ELLIPSE_N:
                continue
            mx, sx = _mean_std([x for x, _ in pts])
            my, sy = _mean_std([y for _, y in pts])
            ax.add_patch(Ellipse((mx, my), width=4 * sx or 1.0,
                                 height=4 * sy or 1.0, fill=False,
                                 edgecolor=pitch_color(t), ls="--",
                                 lw=1.0, alpha=0.55, zorder=3))

    seen: dict[str, int] = {}
    for t, x, y in game_pts:
        ax.scatter(x, y, s=44, color=pitch_color(t), edgecolors=SURFACE,
                   linewidths=0.7, zorder=4)
        seen[t] = seen.get(t, 0) + 1

    handles = [
        Line2D([], [], marker="o", linestyle="", color=pitch_color(t),
               label=f"{t} ({n})")
        for t, n in sorted(seen.items(), key=lambda kv: -kv[1])
    ]
    if season_pts:
        handles.append(Line2D([], [], marker="o", linestyle="",
                              color=INK_3, alpha=0.5, label="Season"))
    styled_legend(ax, handles, "upper left")

    lim = max(25.0, *(abs(v) + 2 for _, x, y in game_pts for v in (x, y)))
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal")
    ax.set_xlabel("Horizontal break (in)")
    ax.set_ylabel("Induced vertical break (in)")
    if title:
        ax.set_title(title)
    save_chart(fig, out_path)
    return True

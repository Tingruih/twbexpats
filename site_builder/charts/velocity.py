"""單場球速序列圖（逐球 start_speed，疊季均速基準線）。"""

from pathlib import Path

from matplotlib.lines import Line2D

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

MIN_TRACKED = 3


def render_velocity_sequence(pitches, out_path: Path, *,
                             season_arsenal=None, title: str = "") -> bool:
    seq = [
        (i + 1, p) for i, p in enumerate(pitches)
        if float_or_none(p.get("start_speed")) is not None
    ]
    if len(seq) < MIN_TRACKED:
        return False

    fig, ax = new_fig(6.6, 3.8)

    # 換局分隔線
    last_inning = None
    for i, p in enumerate(pitches, start=1):
        inning = p.get("inning")
        if inning is not None and inning != last_inning:
            if last_inning is not None:
                ax.axvline(i - 0.5, color=BASELINE, lw=0.8, zorder=1)
            ax.text(i, 1.015, f"INN {inning}", transform=ax.get_xaxis_transform(),
                    fontsize=6.5, color=INK_3, ha="left")
            last_inning = inning

    by_type: dict[str, list[tuple[int, float]]] = {}
    for n, p in seq:
        t = p.get("pitch_type") or "UN"
        by_type.setdefault(t, []).append((n, p["start_speed"]))

    handles = []
    for ptype, items in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        xs, ys = zip(*items)
        color = pitch_color(ptype)
        ax.plot(xs, ys, color=color, lw=1.1, alpha=0.5, zorder=2)
        ax.scatter(xs, ys, s=20, color=color, edgecolors=SURFACE,
                   linewidths=0.5, zorder=3)
        handles.append(Line2D([], [], marker="o", linestyle="-",
                              color=color, label=f"{ptype} ({len(items)})"))

    shown = 0
    for row in season_arsenal or []:
        ptype, velo = row.get("type"), float_or_none(row.get("velo"))
        if ptype not in by_type or velo is None or shown >= 4:
            continue
        ax.axhline(velo, color=pitch_color(ptype), ls="--", lw=1.0,
                   alpha=0.6, zorder=1)
        ax.annotate(f"{ptype} avg", xy=(1.0, velo), xycoords=("axes fraction", "data"),
                    xytext=(4, 0), textcoords="offset points",
                    fontsize=6.5, color=pitch_color(ptype), va="center")
        shown += 1

    if len(seq) < len(pitches):
        ax.text(0.02, 0.03, f"{len(seq)}/{len(pitches)} pitches tracked",
                transform=ax.transAxes, fontsize=7, color=INK_3)

    styled_legend(ax, handles, "lower left")
    ax.set_xlabel("Pitch # in game")
    ax.set_ylabel("Velocity (mph)")
    ax.set_xlim(0.5, len(pitches) + 0.5)
    if title:
        ax.set_title(title)
    save_chart(fig, out_path)
    return True

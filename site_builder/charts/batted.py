"""擊球品質圖：EV/LA 散點、spray chart、Tier 3 hardness/軌跡替代圖。"""

import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from ..constants import (
    FB_TRAJECTORIES,
    GAMEDAY_HOME_X,
    GAMEDAY_HOME_Y,
    GB_TRAJECTORIES,
    LD_TRAJECTORIES,
    PU_TRAJECTORIES,
)
from ..stats.batted_ball.barrel import is_barrel
from ..util.numbers import float_or_none, ratio
from .style import (
    ACCENT,
    BASELINE,
    GRID,
    INK_1,
    INK_3,
    NEUTRAL,
    SLOT_BLUE,
    SURFACE,
    TRAJECTORY_COLORS,
    new_fig,
    save_chart,
    style_axes,
    styled_legend,
)

SWEET_SPOT_LA = (8, 32)
HARD_HIT_EV = 95.0


def _bbe_points(pitches):
    return [
        p for p in pitches
        if p.get("is_in_play")
        and float_or_none(p.get("ev")) is not None
        and float_or_none(p.get("la")) is not None
    ]


def _traj_bucket(traj: str):
    if traj in GB_TRAJECTORIES:
        return "gb"
    if traj in LD_TRAJECTORIES:
        return "ld"
    if traj in FB_TRAJECTORIES:
        return "fb"
    if traj in PU_TRAJECTORIES:
        return "pu"
    return None


def render_ev_la(game_pitches, season_pitches, out_path: Path, *,
                 title: str = "") -> bool:
    game = _bbe_points(game_pitches)
    if not game:
        return False
    season = _bbe_points(season_pitches)

    fig, ax = new_fig(5.8, 4.4)
    ax.axvspan(*SWEET_SPOT_LA, color=GRID, alpha=0.35, zorder=1)
    ax.text(sum(SWEET_SPOT_LA) / 2, 0.02, "sweet spot",
            transform=ax.get_xaxis_transform(), fontsize=6.5,
            color=INK_3, ha="center")
    ax.axhline(HARD_HIT_EV, color=BASELINE, ls="--", lw=0.9, zorder=1)
    ax.annotate("hard-hit 95", xy=(1.0, HARD_HIT_EV),
                xycoords=("axes fraction", "data"), xytext=(4, 0),
                textcoords="offset points", fontsize=6.5, color=INK_3,
                va="center")

    if season:
        ax.scatter([p["la"] for p in season], [p["ev"] for p in season],
                   s=10, color=INK_3, alpha=0.35, linewidths=0, zorder=2)
    for p in game:
        barrel = is_barrel(p.get("ev"), p.get("la"))
        ax.scatter(p["la"], p["ev"], s=52, color=SLOT_BLUE,
                   edgecolors=ACCENT if barrel else SURFACE,
                   linewidths=1.6 if barrel else 0.7, zorder=3)

    handles = [
        Line2D([], [], marker="o", linestyle="", color=SLOT_BLUE, label="This game"),
        Line2D([], [], marker="o", linestyle="", color=SLOT_BLUE,
               markeredgecolor=ACCENT, markeredgewidth=1.6, label="Barrel"),
    ]
    if season:
        handles.append(Line2D([], [], marker="o", linestyle="", color=INK_3,
                              alpha=0.5, label="Season"))
    styled_legend(ax, handles, "lower left")
    ax.set_xlim(-40, 70)
    ax.set_ylim(40, 120)
    ax.set_xlabel("Launch angle (deg)")
    ax.set_ylabel("Exit velocity (mph)")
    if title:
        ax.set_title(title)
    save_chart(fig, out_path)
    return True


def _spray_xy(p):
    hx = float_or_none(p.get("hit_coord_x"))
    hy = float_or_none(p.get("hit_coord_y"))
    if hx is None or hy is None:
        return None
    return hx - GAMEDAY_HOME_X, GAMEDAY_HOME_Y - hy


def render_spray(game_pitches, season_pitches, out_path: Path, *,
                 title: str = "") -> bool:
    game = [(p, _spray_xy(p)) for p in game_pitches if p.get("is_in_play")]
    game = [(p, xy) for p, xy in game if xy is not None]
    if not game:
        return False
    season_xy = [
        (p, _spray_xy(p)) for p in season_pitches if p.get("is_in_play")
    ]
    season_xy = [(p, xy) for p, xy in season_xy if xy is not None]

    fig, ax = new_fig(5.4, 5.0)
    ax.grid(False)
    # 邊線（45°）與距離弧
    for sign in (-1, 1):
        ax.plot([0, sign * 160 / math.sqrt(2)], [0, 160 / math.sqrt(2)],
                color=BASELINE, lw=1.0, zorder=1)
    theta = [math.radians(d) for d in range(45, 136)]
    for r in (60, 110, 160):
        ax.plot([r * math.cos(t) for t in theta],
                [r * math.sin(t) for t in theta],
                color=GRID, lw=0.7, zorder=1)

    if season_xy:
        ax.scatter([xy[0] for _, xy in season_xy], [xy[1] for _, xy in season_xy],
                   s=9, color=INK_3, alpha=0.3, linewidths=0, zorder=2)
    seen = set()
    for p, (x, y) in game:
        bucket = _traj_bucket(p.get("trajectory", "")) or "gb"
        seen.add(bucket)
        ax.scatter(x, y, s=48, color=TRAJECTORY_COLORS[bucket],
                   edgecolors=SURFACE, linewidths=0.7, zorder=3)

    handles = [
        Line2D([], [], marker="o", linestyle="",
               color=TRAJECTORY_COLORS[b], label=b.upper())
        for b in ("gb", "ld", "fb", "pu") if b in seen
    ]
    if season_xy:
        handles.append(Line2D([], [], marker="o", linestyle="", color=INK_3,
                              alpha=0.5, label="Season"))
    styled_legend(ax, handles, "upper right")
    ax.set_xlim(-170, 170)
    ax.set_ylim(-15, 185)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    if title:
        ax.set_title(title)
    save_chart(fig, out_path)
    return True


def _dist_pcts(pitches, keys, getter):
    counts = {k: 0 for k in keys}
    total = 0
    for p in pitches:
        if not p.get("is_in_play"):
            continue
        k = getter(p)
        if k in counts:
            counts[k] += 1
            total += 1
    if not total:
        return None
    return {k: (ratio(v, total, digits=3) or 0) for k, v in counts.items()}


def render_quality_fallback(week_pitches, season_pitches, out_path: Path, *,
                            title: str = "") -> bool:
    hard_keys = ("soft", "medium", "hard")
    traj_keys = ("gb", "ld", "fb", "pu")
    week_h = _dist_pcts(week_pitches, hard_keys, lambda p: p.get("hardness"))
    week_t = _dist_pcts(week_pitches, traj_keys,
                        lambda p: _traj_bucket(p.get("trajectory", "")))
    if week_h is None and week_t is None:
        return False
    season_h = _dist_pcts(season_pitches, hard_keys, lambda p: p.get("hardness"))
    season_t = _dist_pcts(season_pitches, traj_keys,
                          lambda p: _traj_bucket(p.get("trajectory", "")))

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.4), facecolor=SURFACE)
    panels = (
        (axes[0], "Contact quality (scorer)", hard_keys, week_h, season_h),
        (axes[1], "Batted-ball type", traj_keys, week_t, season_t),
    )
    for ax, subtitle, keys, week, season in panels:
        style_axes(ax)
        ax.grid(axis="x", visible=False)
        xs = range(len(keys))
        if week:
            ax.bar([x - 0.18 for x in xs], [week[k] * 100 for k in keys],
                   width=0.36, color=SLOT_BLUE, zorder=2, label="Week")
            for x, k in zip(xs, keys):
                ax.text(x - 0.18, week[k] * 100 + 1, f"{week[k] * 100:.0f}",
                        ha="center", fontsize=7, color=INK_1)
        if season:
            ax.bar([x + 0.18 for x in xs], [season[k] * 100 for k in keys],
                   width=0.36, facecolor="none", edgecolor=NEUTRAL,
                   linewidth=1.2, zorder=2, label="Season")
            for x, k in zip(xs, keys):
                ax.text(x + 0.18, season[k] * 100 + 1, f"{season[k] * 100:.0f}",
                        ha="center", fontsize=7, color=INK_3)
        ax.set_xticks(list(xs), [k.upper() for k in keys])
        ax.set_ylim(0, 100)
        ax.set_ylabel("% of BBE")
        ax.set_title(subtitle)
        ax.legend(fontsize=7, facecolor=SURFACE, edgecolor=GRID,
                  labelcolor=INK_3)
    if title:
        fig.suptitle(title, color=INK_1, fontsize=10)
    fig.tight_layout()
    save_chart(fig, out_path)
    return True

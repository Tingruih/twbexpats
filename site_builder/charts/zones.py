"""好球帶熱區 heatmap（9 宮格 + 外側 11–14 L 形區）。

格座標系：帶內 3×3 佔 (0..3)×(0..3)，外側區延伸到 -1..4。
y 軸向上（zone 1 = 高內側在左上）。
"""

from pathlib import Path

from matplotlib.colors import Normalize
from matplotlib.patches import Polygon, Rectangle

from ..stats.recent.derived import normalized_location
from .style import (
    ACCENT,
    GRID,
    INK_1,
    INK_3,
    MASK_FILL,
    SEQ_CMAP,
    SURFACE,
    new_fig,
    save_chart,
)

# zone → (col, row)；row 0 在下（zone 7-8-9 為低位）
ZONE_CELLS = {
    1: (0, 2), 2: (1, 2), 3: (2, 2),
    4: (0, 1), 5: (1, 1), 6: (2, 1),
    7: (0, 0), 8: (1, 0), 9: (2, 0),
}
OUTER_POLYGONS = {
    11: [(-1, 4), (1.5, 4), (1.5, 3), (0, 3), (0, 1.5), (-1, 1.5)],
    12: [(4, 4), (1.5, 4), (1.5, 3), (3, 3), (3, 1.5), (4, 1.5)],
    13: [(-1, -1), (1.5, -1), (1.5, 0), (0, 0), (0, 1.5), (-1, 1.5)],
    14: [(4, -1), (1.5, -1), (1.5, 0), (3, 0), (3, 1.5), (4, 1.5)],
}
OUTER_LABEL_POS = {
    11: (-0.5, 3.5), 12: (3.5, 3.5), 13: (-0.5, -0.5), 14: (3.5, -0.5),
}
_DEN_KEY = {"avg": "ab", "whiff_pct": "swings", "swing_pct": "n"}


def _cell_ink(rgba) -> str:
    r, g, b = rgba[0], rgba[1], rgba[2]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#09090b" if lum > 0.5 else INK_1


def _fmt(metric: str, value: float) -> str:
    if metric == "avg":
        return f"{value:.3f}".lstrip("0")
    return f"{value * 100:.0f}%"


def overlay_points_from_pitches(pitches) -> list[tuple[float, float]]:
    pts = []
    for p in pitches:
        loc = normalized_location(p)
        if loc is None:
            continue
        # x_norm/z_norm ∈ [-1,1] 為帶內 → 映到 0..3；外側夾在 -0.95..3.95
        x = min(max((loc[0] + 1) * 1.5, -0.95), 3.95)
        y = min(max((loc[1] + 1) * 1.5, -0.95), 3.95)
        pts.append((x, y))
    return pts


def render_hot_zone(zone_stats, out_path: Path, *, metric: str = "avg",
                    min_n: int = 5, vmin: float = 0.15, vmax: float = 0.40,
                    overlay_points=None, title: str = "") -> bool:
    if not zone_stats:
        return False
    den_key = _DEN_KEY[metric]
    norm = Normalize(vmin=vmin, vmax=vmax, clip=True)

    fig, ax = new_fig(5.0, 5.4)
    ax.grid(False)

    def paint(zone, patch_xy_label):
        cell = zone_stats.get(zone)
        value = cell and cell.get(metric)
        den = (cell or {}).get(den_key, 0)
        if cell is None or value is None or den < min_n:
            face, text, ink = MASK_FILL, f"n={den}" if cell else "-", INK_3
        else:
            rgba = SEQ_CMAP(norm(value))
            face, text, ink = rgba, _fmt(metric, value), _cell_ink(rgba)
        patch_xy_label(face, text, ink)

    for zone, (col, row) in ZONE_CELLS.items():
        def _p(face, text, ink, col=col, row=row):
            ax.add_patch(Rectangle((col, row), 1, 1, facecolor=face,
                                   edgecolor=SURFACE, linewidth=2, zorder=2))
            ax.text(col + 0.5, row + 0.5, text, ha="center", va="center",
                    fontsize=9, color=ink, zorder=3)
        paint(zone, _p)

    for zone, poly in OUTER_POLYGONS.items():
        def _p(face, text, ink, poly=poly, zone=zone):
            ax.add_patch(Polygon(poly, closed=True, facecolor=face,
                                 edgecolor=SURFACE, linewidth=2, zorder=1))
            lx, ly = OUTER_LABEL_POS[zone]
            ax.text(lx, ly, text, ha="center", va="center",
                    fontsize=8, color=ink, zorder=3)
        paint(zone, _p)

    for x, y in overlay_points or []:
        ax.scatter(x, y, s=46, facecolors=ACCENT, edgecolors=SURFACE,
                   linewidths=1.0, zorder=4)

    ax.add_patch(Rectangle((0, 0), 3, 3, fill=False, edgecolor=GRID,
                           linewidth=1.2, zorder=3))
    ax.set_xlim(-1.05, 4.05)
    ax.set_ylim(-1.05, 4.05)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.text(1.5, -1.02, "Catcher's view", ha="center", va="top",
            fontsize=7, color=INK_3)
    if title:
        ax.set_title(title)
    save_chart(fig, out_path)
    return True

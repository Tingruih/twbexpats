"""場景擷取 — 把網站的各個功能畫面變成底片。

每個 `capture_*` 函式負責：把頁面設定到目標狀態 → 截底片 → 回報關鍵區域座標。
鏡頭邏輯完全不在這裡；這一層只交付「圖」與「圖上哪裡有什麼」。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Page

from promo import config
from promo.capture import browser

Box = tuple[int, int, int, int]   # (x, y, w, h) — 底片座標系


@dataclass
class Plate:
    """一張底片，附帶命名的關鍵區域供攝影機取景。"""

    name: str
    path: Path
    width: int
    height: int
    boxes: dict[str, Box] = field(default_factory=dict)

    def box(self, key: str) -> Box:
        if key not in self.boxes:
            raise KeyError(f"底片 {self.name} 沒有名為 {key!r} 的區域；可用：{sorted(self.boxes)}")
        return self.boxes[key]


@dataclass
class Sequence:
    """一段逐幀底片序列，用於捕捉真實 DOM 的互動過程。"""

    name: str
    paths: list[Path]
    width: int
    height: int
    boxes: dict[str, Box] = field(default_factory=dict)


def _size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as im:
        return im.size


def _collect(page: Page, selectors: dict[str, str]) -> dict[str, Box]:
    """批次取得多個元素的底片座標，略過找不到的。"""
    out: dict[str, Box] = {}
    for key, sel in selectors.items():
        box = browser.element_box(page, sel)
        if box:
            out[key] = box
    return out


# ── §1 首頁 ────────────────────────────────────────────────────

HOME_SELECTORS = {
    "sort_bar": "#sort-bar",
    "btn_recent": "#btn-recent",
    "btn_level": "#btn-level",
    "grid": "#player-grid",
    "card_1": "#player-grid .player-card:nth-child(1)",
    "card_2": "#player-grid .player-card:nth-child(2)",
    "card_3": "#player-grid .player-card:nth-child(3)",
    "row_1": "#player-grid",
}


def capture_home(page: Page) -> Plate:
    """首頁全長底片 —— 鏡頭可沿垂直方向遊走整面球員卡片牆。"""
    browser.goto(page, config.HOME_URL)
    page.evaluate("() => window.scrollTo(0, 0)")
    path = config.PLATE_DIR / "home.png"
    browser.shoot(page, path, full_page=True)
    w, h = _size(path)
    return Plate("home", path, w, h, _collect(page, HOME_SELECTORS))


# 在瀏覽器內補上 FLIP 重排動畫。
# 網站的 sortCards() 是直接 appendChild，卡片會瞬間跳位；宣傳片需要看得見的位移過程，
# 所以先記錄舊位置，重排後用 transform 把卡片推回原位，再由 Python 逐幀播放。
_FLIP_JS = """
() => {
    const grid = document.getElementById('player-grid');
    const cards = Array.from(grid.querySelectorAll('.player-card'));
    const btnLevel = document.getElementById('btn-level');
    const btnRecent = document.getElementById('btn-recent');
    const before = cards.map(c => c.getBoundingClientRect());

    window.sortCards('recent');

    const after = cards.map(c => c.getBoundingClientRect());
    const deltas = cards.map((c, i) => ({
        el: c,
        dx: before[i].left - after[i].left,
        dy: before[i].top - after[i].top,
    }));
    cards.forEach(c => { c.style.willChange = 'transform'; });

    window.__flip = (t) => {
        const k = 1 - t;
        for (const d of deltas) {
            if (t >= 1) { d.el.style.transform = ''; d.el.style.willChange = ''; }
            else { d.el.style.transform = `translate(${d.dx * k}px, ${d.dy * k}px)`; }
        }
        // sortCards() 會立刻把選中態切到「最近出賽」，但動畫的第 0 幀代表的是
        // 「游標尚未按下」的時刻 —— 此時按鈕必須仍停在「層級」，否則會出現
        // 還沒點擊按鈕就先亮起的穿幫。
        btnLevel.classList.toggle('sort-btn-active', t <= 0);
        btnRecent.classList.toggle('sort-btn-active', t > 0);
    };
    window.__flip(0);
    return deltas.filter(d => d.dx || d.dy).length;
}
"""


def capture_home_flip(page: Page, frames: int) -> Sequence:
    """排序切換的 FLIP 重排序列（在 viewport 範圍內，與首頁底片共用座標系）。"""
    browser.goto(page, config.HOME_URL)
    page.evaluate("() => window.scrollTo(0, 0)")
    boxes = _collect(page, HOME_SELECTORS)

    moved = page.evaluate(_FLIP_JS)
    if not moved:
        raise RuntimeError("FLIP 重排沒有任何卡片移動，排序功能可能已變更。")

    from promo.compose.easing import ease_in_out_cubic

    out_dir = config.PLATE_DIR / "home_flip"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i in range(frames):
        t = ease_in_out_cubic(i / max(1, frames - 1))
        page.evaluate("(t) => window.__flip(t)", t)
        # 按鈕的 active 狀態在動畫過半時切換，讓「點擊生效」的時間點看起來自然
        p = out_dir / f"{i:03d}.png"
        page.screenshot(path=str(p))
        paths.append(p)

    w, h = _size(paths[0])
    return Sequence("home_flip", paths, w, h, boxes)


# ── §3–4 進階數據與球種分析 ────────────────────────────────────

ADVANCED_SELECTORS = {
    "statcast": "#stats-table-sc",
    "statcast_section": "#stats-table-sc",
    "discipline": "#stats-table-pd",
    "batted_ball": "#stats-table-bb",
    "arsenal_pitch": "#panel-advanced .arsenal-subsection:nth-of-type(1)",
    "arsenal_result": "#panel-advanced .arsenal-subsection:nth-of-type(2)",
    "arsenal_count": "#panel-advanced .arsenal-subsection:nth-of-type(3)",
    "arsenal_all": "#panel-advanced .arsenal-table-stack",
}


def capture_advanced(page: Page) -> Plate:
    """進階數據分頁的全長底片。

    §3 與 §4 共用這一張 —— Statcast 概覽到球種分析之間的鏡頭移動因此
    是同一張圖上的一次連續平移，中途不需要重新截圖，也就不可能卡頓。
    """
    browser.goto(page, config.PLAYER_URL)
    page.click('.page-desktop .tab-label[data-tab="advanced"]')
    page.wait_for_timeout(1600)
    path = config.PLATE_DIR / "advanced.png"
    browser.shoot(page, path, full_page=True)
    w, h = _size(path)
    return Plate("advanced", path, w, h, _collect(page, ADVANCED_SELECTORS))


# ── §6 逐球紀錄 ────────────────────────────────────────────────

GAMELOG_SELECTORS = {
    "table": "#panel-gamelogs .data-table",
    "first_row": "#panel-gamelogs .game-row-expandable",
    "arrow": "#panel-gamelogs .game-row-expandable .toggle-arrow",
    "filter_bar": "#panel-gamelogs .log-filter-bar",
}

# 展開逐球區塊時，網站是直接 display='' 瞬間出現。這裡改成可由 Python 逐幀
# 驅動的高度揭露，下方的比賽列會被自然推開，箭頭同步旋轉。
_EXPAND_JS = """
async () => {
    const row = document.querySelector('#panel-gamelogs .game-row-expandable');
    const arrow = row.querySelector('.toggle-arrow');
    const logRow = row.nextElementSibling;
    const content = logRow.querySelector('.pitch-log-scroll');

    // 先讓資料載入並渲染完成，才能量到正確的全高
    logRow.style.display = '';
    const src = logRow.dataset.src;
    const res = await fetch(src);
    const data = await res.json();
    content.innerHTML = _buildPitchTable(data);
    content.dataset.rendered = '1';

    const full = content.scrollHeight;
    content.style.overflow = 'hidden';
    content.style.willChange = 'max-height';

    // 逐球表遠高於可視範圍。若動畫一路長到 full，後半段的高度變化全在畫面外，
    // 等於浪費一半動畫時間。只長到剛好超出視窗底部，整段過程就都看得見；
    // 收尾時再解除 max-height 還原完整高度，該跳變發生在畫面外，不會被察覺。
    const visibleTarget = Math.max(240, window.innerHeight - content.getBoundingClientRect().top + 80);
    const target = Math.min(full, visibleTarget);

    window.__expand = (t) => {
        if (t >= 1) {
            content.style.maxHeight = '';
            content.style.opacity = '1';
            content.style.willChange = '';
        } else {
            content.style.maxHeight = (target * t) + 'px';
            content.style.opacity = String(Math.min(1, t * 2.2));
        }
        if (arrow) arrow.style.transform = `rotate(${90 * t}deg)`;
    };
    window.__expand(0);
    return full;
}
"""


def capture_gamelogs_expand(page: Page, frames: int) -> tuple[Sequence, Plate]:
    """逐球區塊的展開序列，以及展開完成後的全長底片。"""
    browser.goto(page, config.PLAYER_URL)
    page.click('.page-desktop .tab-label[data-tab="gamelogs"]')
    page.wait_for_timeout(1200)
    page.evaluate("() => window.scrollTo(0, 0)")

    full_h = page.evaluate(_EXPAND_JS)
    if not full_h:
        raise RuntimeError("逐球資料未能載入，無法產生展開動畫。")
    page.wait_for_timeout(400)

    from promo.compose.easing import ease_out_cubic

    out_dir = config.PLATE_DIR / "gamelog_expand"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i in range(frames):
        t = ease_out_cubic(i / max(1, frames - 1))
        page.evaluate("(t) => window.__expand(t)", t)
        p = out_dir / f"{i:03d}.png"
        page.screenshot(path=str(p))
        paths.append(p)

    seq_w, seq_h = _size(paths[0])
    seq = Sequence("gamelog_expand", paths, seq_w, seq_h, _collect(page, GAMELOG_SELECTORS))

    # 展開完成後再截一張長底片，供鏡頭在逐球表格內遊走
    page.evaluate("() => window.__expand(1)")
    expanded_path = config.PLATE_DIR / "gamelog_expanded.png"
    browser.shoot(page, expanded_path, full_page=True)
    w, h = _size(expanded_path)
    boxes = _collect(page, GAMELOG_SELECTORS | {
        "pitch_table": "#panel-gamelogs .pitch-log-table",
        "pitch_head": "#panel-gamelogs .pitch-log-table thead",
        "video_col": "#panel-gamelogs .pitch-log-table tbody tr:nth-child(1) td:last-child",
        "pitch_rows": "#panel-gamelogs .pitch-log-table tbody",
    })
    plate = Plate("gamelog_expanded", expanded_path, w, h, boxes)
    return seq, plate


# ── §8 數據圖表 ────────────────────────────────────────────────

PLOT_SELECTORS = {
    "trend": "#panel-plot .pitcher-trend-wrap",
    "trend_canvas": "#performanceChart",
    "charts_panel": "#panel-plot .pitch-plinko-wrap",
    "usage": "#panel-plot .pitch-usage-hand-root",
    "movement": "#panel-plot .pitch-movement-root",
    "plinko": "#panel-plot .pitch-plinko-root",
}


def capture_plot(page: Page) -> Plate:
    """數據圖表分頁的全長底片（位移圖與 Pitch Plinko 在同一張上）。"""
    browser.goto(page, config.PLAYER_URL)
    page.click('.page-desktop .tab-label[data-tab="plot"]')
    page.wait_for_timeout(2200)   # Chart.js 與自繪 SVG 都要時間畫完
    path = config.PLATE_DIR / "plot.png"
    browser.shoot(page, path, full_page=True)
    w, h = _size(path)
    return Plate("plot", path, w, h, _collect(page, PLOT_SELECTORS))


# ── 統一入口 ────────────────────────────────────────────────────

MANIFEST = config.PLATE_DIR / "manifest.json"


def capture_all(flip_frames: int, expand_frames: int) -> dict[str, Plate | Sequence]:
    """擷取全片所需的所有底片，並寫出 manifest 供重複建置時檢視。"""
    result: dict[str, Plate | Sequence] = {}
    with browser.serve_dist():
        with browser.plate_page() as page:
            print("  · 首頁底片…")
            result["home"] = capture_home(page)
            print("  · 首頁排序重排序列…")
            result["home_flip"] = capture_home_flip(page, flip_frames)
            print("  · 進階數據長底片…")
            result["advanced"] = capture_advanced(page)
            print("  · 逐球展開序列…")
            seq, plate = capture_gamelogs_expand(page, expand_frames)
            result["gamelog_expand"] = seq
            result["gamelog_expanded"] = plate
            print("  · 數據圖表長底片…")
            result["plot"] = capture_plot(page)

    MANIFEST.write_text(
        json.dumps(
            {
                k: {
                    "type": type(v).__name__,
                    "size": [v.width, v.height],
                    "boxes": {bk: list(bv) for bk, bv in v.boxes.items()},
                    "frames": len(v.paths) if isinstance(v, Sequence) else 1,
                }
                for k, v in result.items()
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return result

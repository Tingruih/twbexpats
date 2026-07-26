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
    """一段逐幀底片序列，用於捕捉真實 DOM 的互動過程。

    `origin_y` 是這段底片在「同一頁的長底片」座標系中的上緣位置（底片像素）。
    viewport 序列只涵蓋頁面的一個橫帶，它自己的 y=0 對應長底片的 y=origin_y；
    鏡頭要從長底片無縫接到序列，就得靠這個位移換算取景位置。
    """

    name: str
    paths: list[Path]
    width: int
    height: int
    boxes: dict[str, Box] = field(default_factory=dict)
    origin_y: int = 0


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


# ── 分頁列 ──────────────────────────────────────────────────────
# 全片有三次「游標點擊分頁」的轉場。分頁列位在球員 hero 下方、各分頁面板之上，
# 因此**每一張球員頁底片上的 y 座標都相同** —— 鏡頭可以停在同一個鏡位，只把
# 底片換成另一個分頁，看起來就是「按下去，內容換了」，完全不需要轉場特效。
TAB_SELECTORS = {
    "tab_nav": ".page-desktop .tab-nav",
    "tab_gamelogs": '.page-desktop .tab-label[data-tab="gamelogs"]',
    "tab_advanced": '.page-desktop .tab-label[data-tab="advanced"]',
    "tab_plot": '.page-desktop .tab-label[data-tab="plot"]',
}


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

    # 重排底定後，補上鄧愷威（宣傳片主角）卡片的最終位置，供後續鏡頭推近點擊。
    # 用 href 選取而非 nth-child，才不受排序結果影響。
    feature_box = browser.element_box(
        page, f'#player-grid .player-card[href="/player/{config.FEATURE_PLAYER}/"]'
    )
    if feature_box:
        boxes = boxes | {"card_feature": feature_box}

    w, h = _size(paths[0])
    return Sequence("home_flip", paths, w, h, boxes)


# ── §2 球員資料頁 ──────────────────────────────────────────────

BIO_SELECTORS = {
    "hero": ".profile-hero",
    "avatar": ".hero-avatar",
    "hero_stats": ".hero-stats-strip",
    "bio_grid": "#panel-bio .bio-grid",
}


def capture_profile(page: Page) -> Plate:
    """球員頁面預設分頁（球員資料）的長底片 —— 頁面載入時已是啟用狀態，不需點擊分頁。"""
    browser.goto(page, config.PLAYER_URL)
    path = config.PLATE_DIR / "profile.png"
    browser.shoot(page, path, full_page=True)
    w, h = _size(path)
    return Plate("profile", path, w, h, _collect(page, BIO_SELECTORS | TAB_SELECTORS))


# ── §3 進階數據與球種分析 ──────────────────────────────────────

ADVANCED_SELECTORS = {
    "yearly": "#stats-table-adv",
    "statcast": "#stats-table-sc",
    "discipline": "#stats-table-pd",
    "batted_ball": "#stats-table-bb",
    "arsenal_pitch": "#panel-advanced .arsenal-subsection:nth-of-type(1)",
    "arsenal_result": "#panel-advanced .arsenal-subsection:nth-of-type(2)",
    "arsenal_count": "#panel-advanced .arsenal-subsection:nth-of-type(3)",
    "arsenal_all": "#panel-advanced .arsenal-table-stack",
}


def capture_advanced(page: Page) -> Plate:
    """進階數據分頁的全長底片。

    整個進階數據段落共用這一張 —— 歷年進階數據、Statcast、選球、擊球型態到球種
    分析之間的鏡頭移動因此是同一張圖上的連續平移，中途不需要重新截圖，也就不可能
    卡頓。段末快速上滑回分頁列時，鏡頭走的仍是同一張底片。
    """
    browser.goto(page, config.PLAYER_URL)
    page.click('.page-desktop .tab-label[data-tab="advanced"]')
    page.wait_for_timeout(1600)
    path = config.PLATE_DIR / "advanced.png"
    browser.shoot(page, path, full_page=True)
    w, h = _size(path)
    return Plate("advanced", path, w, h, _collect(page, ADVANCED_SELECTORS | TAB_SELECTORS))


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


def capture_gamelogs_expand(page: Page, frames: int) -> tuple[Plate, Sequence, Plate]:
    """逐球區塊的三張底片：分頁剛切過來的未展開全長底片、展開序列、展開後的全長底片。

    第一張是「游標按下『比賽紀錄』之後」的落點 —— 鏡頭停在分頁列的鏡位上，
    只把底片從進階數據換成這一張，切換就成立了。
    """
    browser.goto(page, config.PLAYER_URL)
    page.click('.page-desktop .tab-label[data-tab="gamelogs"]')
    page.wait_for_timeout(1200)
    page.evaluate("() => window.scrollTo(0, 0)")

    collapsed_path = config.PLATE_DIR / "gamelog_collapsed.png"
    browser.shoot(page, collapsed_path, full_page=True)
    cw, ch = _size(collapsed_path)
    collapsed = Plate(
        "gamelog_collapsed", collapsed_path, cw, ch,
        _collect(page, GAMELOG_SELECTORS | TAB_SELECTORS),
    )
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
    boxes = _collect(page, GAMELOG_SELECTORS | TAB_SELECTORS | {
        "pitch_table": "#panel-gamelogs .pitch-log-table",
        "pitch_head": "#panel-gamelogs .pitch-log-table thead",
        "video_col": "#panel-gamelogs .pitch-log-table tbody tr:nth-child(1) td:last-child",
        "pitch_rows": "#panel-gamelogs .pitch-log-table tbody",
    })
    plate = Plate("gamelog_expanded", expanded_path, w, h, boxes)
    return collapsed, seq, plate


# ── §7 逐球影片 ────────────────────────────────────────────────

# 點開影片後要抓的那一球。取第三球純粹是構圖考量：表頭下方第三列，
# 上下都還有資料列，游標落點不會貼在表格邊緣。
VIDEO_ROW = 3

# 影片彈窗是 position:fixed，因此頁面捲到哪裡，它就疊在哪一屏的正中央。
# 這裡刻意不把它改成 absolute —— 序列本來就是 viewport 截圖，維持 fixed
# 反而讓「彈窗永遠置中於畫面」這件事自動成立。
_OPEN_VIDEO_JS = """
async (row) => {
    const table = document.querySelector('#panel-gamelogs .pitch-log-table');
    // 讓逐球表頂端落在畫面上緣下方一點，表頭與前十餘列同時在鏡頭可及範圍內
    const top = table.getBoundingClientRect().top + window.scrollY;
    window.scrollTo(0, Math.max(0, Math.round(top - 150)));
    await new Promise(r => setTimeout(r, 120));

    const btn = document.querySelector(
        `#panel-gamelogs .pitch-log-table tbody tr:nth-child(${row}) .pitch-video-btn`);
    if (!btn) return null;
    btn.click();
    return {scrollY: window.scrollY};
}
"""

_VIDEO_READY_JS = """
() => {
    const box = document.querySelector('.pitch-video-box');
    if (!box) return {state: 'no-box'};
    const msg = box.querySelector('.pitch-video-message');
    if (msg) return {state: 'message', text: msg.textContent};
    const v = box.querySelector('video');
    if (!v) return {state: 'no-video'};
    return {state: 'video', ready: v.readyState, duration: v.duration || 0};
}
"""

# 播放控制列會依滑鼠活動自動顯隱，逐幀擷取時會忽隱忽現。拿掉 controls，
# 畫面只剩乾淨的影像與彈窗本身的關閉鈕，仍然讀得出這是一個播放視窗。
_VIDEO_PREPARE_JS = """
() => {
    const v = document.querySelector('.pitch-video-box video');
    v.pause();
    v.removeAttribute('controls');
    v.muted = true;
    return v.duration;
}
"""

_VIDEO_SEEK_JS = """
async (t) => {
    const v = document.querySelector('.pitch-video-box video');
    if (Math.abs(v.currentTime - t) < 1e-3) return v.currentTime;
    await new Promise(resolve => {
        v.addEventListener('seeked', resolve, {once: true});
        v.currentTime = t;
        setTimeout(resolve, 1500);   // 保險：seek 失敗也不要整段卡死
    });
    return v.currentTime;
}
"""


def capture_pitch_video(page: Page, frames: int, start_at: float = 0.15) -> Sequence:
    """點開逐球影片後的播放序列（viewport 底片）。

    需要頁面已停在 `capture_gamelogs_expand` 留下的「逐球表已展開」狀態。
    影片以逐格 seek 的方式擷取，播放速度因此完全由 Python 的幀率決定，
    不受瀏覽器實際解碼速度影響。
    """
    info = page.evaluate(_OPEN_VIDEO_JS, VIDEO_ROW)
    if not info:
        raise RuntimeError(f"逐球表第 {VIDEO_ROW} 列沒有影片按鈕，這場比賽可能不是 MLB 層級。")

    for _ in range(60):
        state = page.evaluate(_VIDEO_READY_JS)
        if state["state"] == "video" and (state.get("ready") or 0) >= 3:
            break
        if state["state"] == "message" and "載入" not in state.get("text", ""):
            raise RuntimeError(f"逐球影片載入失敗：{state['text']}")
        page.wait_for_timeout(500)
    else:
        raise RuntimeError(f"逐球影片逾時未就緒：{state}")

    duration = page.evaluate(_VIDEO_PREPARE_JS)
    span = frames / config.FPS
    if duration and duration < start_at + span:
        start_at = max(0.0, duration - span)

    out_dir = config.PLATE_DIR / "pitch_video"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()

    paths: list[Path] = []
    for i in range(frames):
        page.evaluate(_VIDEO_SEEK_JS, start_at + i / config.FPS)
        p = out_dir / f"{i:03d}.png"
        page.screenshot(path=str(p))
        paths.append(p)

    # 序列只涵蓋 scrollY 起算的一屏，區域一律換算成序列自己的座標系。
    # element_box 回傳的是「文件座標」，減去捲動量就是它在這一屏上的位置；
    # 影片彈窗雖是 fixed 定位，這條換算對它同樣成立（見 element_box）。
    origin_y = int(round(info["scrollY"] * config.PLATE_DPR))
    boxes = {
        k: (b[0], b[1] - origin_y, b[2], b[3])
        for k, b in _collect(page, {
            "video_box": ".pitch-video-box",
            # 看完這一球後，游標按這顆 × 把彈窗關掉，才接得上「上滑回分頁列」
            "video_close": ".pitch-video-close",
            "video_btn":
                f"#panel-gamelogs .pitch-log-table tbody tr:nth-child({VIDEO_ROW}) .pitch-video-btn",
            "pitch_table": "#panel-gamelogs .pitch-log-table",
            "video_col": "#panel-gamelogs .pitch-log-table tbody tr:nth-child(1) td:last-child",
        }).items()
    }

    w, h = _size(paths[0])
    return Sequence("pitch_video", paths, w, h, boxes, origin_y=origin_y)


# ── §5 數據圖表 ────────────────────────────────────────────────

PLOT_SELECTORS = {
    "trend": "#panel-plot .pitcher-trend-wrap",
    "trend_canvas": "#performanceChart",
    "trend_stat": "#trend-stat-select",
    "charts_panel": "#panel-plot .pitch-plinko-wrap",
    # 「對左右打球種使用率」與「球種位移」兩張圖並排在這個 grid 裡，
    # 宣傳片把它們當成同一件事介紹，因此取景直接框住整個 grid。
    "chart_grid": "#panel-plot .pitch-chart-grid",
    "usage": "#panel-plot .pitch-usage-hand-root",
    "movement": "#panel-plot .pitch-movement-root",
    "plinko": "#panel-plot .pitch-plinko-root",
}

# 賽季走勢圖預設顯示 ERA；游標按下「數據」下拉後換成這一項。
TREND_ALT_STAT = "k_pct"


def capture_plot(page: Page) -> tuple[Plate, Plate]:
    """數據圖表分頁的兩張全長底片：切換「數據」下拉之前與之後。

    macOS 原生 `<select>` 的下拉清單畫在瀏覽器視窗之外，截圖抓不到，所以不去
    模擬展開的選單。改成截「換數據前」與「換數據後」兩張除了走勢圖以外完全相同
    的底片，合成時在同一個鏡位上做一次 0.35 秒的交叉溶接 —— 觀眾看到的就是
    「按一下，圖表換成另一項數據」。
    """
    browser.goto(page, config.PLAYER_URL)
    page.click('.page-desktop .tab-label[data-tab="plot"]')
    page.wait_for_timeout(2200)   # Chart.js 與自繪 SVG 都要時間畫完
    path = config.PLATE_DIR / "plot.png"
    browser.shoot(page, path, full_page=True)
    w, h = _size(path)
    before = Plate("plot", path, w, h, _collect(page, PLOT_SELECTORS | TAB_SELECTORS))

    # select_option 會觸發 change 事件，charts.js 隨即銷毀舊圖表並重畫
    page.select_option("#trend-stat-select", TREND_ALT_STAT)
    page.wait_for_timeout(1600)
    alt_path = config.PLATE_DIR / "plot_alt.png"
    browser.shoot(page, alt_path, full_page=True)
    aw, ah = _size(alt_path)
    after = Plate("plot_alt", alt_path, aw, ah, _collect(page, PLOT_SELECTORS | TAB_SELECTORS))

    if (aw, ah) != (w, h):
        raise RuntimeError(
            f"換數據前後的底片尺寸不同（{w}×{h} vs {aw}×{ah}），交叉溶接會位移。"
        )
    return before, after


# ── 統一入口 ────────────────────────────────────────────────────

MANIFEST = config.PLATE_DIR / "manifest.json"


def capture_all(
    flip_frames: int, expand_frames: int, video_frames: int
) -> dict[str, Plate | Sequence]:
    """擷取全片所需的所有底片，並寫出 manifest 供重複建置時檢視。"""
    result: dict[str, Plate | Sequence] = {}
    with browser.serve_dist():
        with browser.plate_page() as page:
            print("  · 首頁底片…")
            result["home"] = capture_home(page)
            print("  · 首頁排序重排序列…")
            result["home_flip"] = capture_home_flip(page, flip_frames)
            print("  · 球員資料頁底片…")
            result["profile"] = capture_profile(page)
            print("  · 進階數據長底片…")
            result["advanced"] = capture_advanced(page)
            print("  · 逐球展開序列…")
            collapsed, seq, plate = capture_gamelogs_expand(page, expand_frames)
            result["gamelog_collapsed"] = collapsed
            result["gamelog_expand"] = seq
            result["gamelog_expanded"] = plate
            print("  · 逐球影片播放序列…")
            result["pitch_video"] = capture_pitch_video(page, video_frames)
            print("  · 數據圖表長底片（換數據前後各一張）…")
            result["plot"], result["plot_alt"] = capture_plot(page)

    MANIFEST.write_text(
        json.dumps(
            {
                k: {
                    "type": type(v).__name__,
                    "size": [v.width, v.height],
                    "boxes": {bk: list(bv) for bk, bv in v.boxes.items()},
                    "frames": len(v.paths) if isinstance(v, Sequence) else 1,
                    "origin_y": v.origin_y if isinstance(v, Sequence) else 0,
                }
                for k, v in result.items()
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return result

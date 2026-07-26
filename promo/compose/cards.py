"""字卡渲染 —— 開場卡與結尾卡。

全片只有頭尾兩張字卡。中段的分頁切換一律由游標點擊分頁按鈕完成，
不再插入章節卡把畫面切斷。

所有文字一律交給瀏覽器排版後逐幀截圖。中文字距、字重與抗鋸齒交給 CSS 處理，
遠比在 Pillow 裡拼字可靠；Python 端只負責驅動動畫進度。

以 2× 解析度截圖再縮到輸出尺寸，等同 2×2 超取樣，文字邊緣更乾淨。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page

from promo import config

_SS = 2   # 超取樣倍率

# 字卡的版面永遠以 1920×1080 設計，不隨輸出解析度改變 —— 改變的是渲染 DPR。
# 若跟著把 viewport 放大到 4K，所有以 px 指定的字級會相對縮成一半。
CARD_VIEWPORT_W = 1920
CARD_VIEWPORT_H = 1080


def card_dpr() -> float:
    """字卡的渲染 DPR：輸出倍率再乘上超取樣，得到乾淨的文字邊緣。"""
    return (config.WIDTH / CARD_VIEWPORT_W) * _SS


def _base_css() -> str:
    return f"""
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{
    width: {CARD_VIEWPORT_W}px; height: {CARD_VIEWPORT_H}px;
    background: #000; overflow: hidden;
    font-family: 'Inter', 'PingFang TC', 'Helvetica Neue', sans-serif;
    -webkit-font-smoothing: antialiased;
}}
.stage {{
    width: 100%; height: 100%;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    will-change: transform, opacity;
}}
.rule {{ height: 2px; background: {config.TEAL_HEX}; width: 0; }}
"""


def _html(body: str, css: str, script: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{_base_css()}{css}</style></head><body>{body}"
        f"<script>{script}</script></body></html>"
    )


# ── 開場卡 ──────────────────────────────────────────────────────

def intro_html(logo_svg: str, title: str, subtitle: str) -> str:
    css = """
    .logo { width: 210px; height: 182px; margin-bottom: 34px; }
    .logo path { fill: none; stroke: #F5F5F5; stroke-width: 34;
                 stroke-linecap: round; stroke-linejoin: round; }
    .title { font-size: 92px; font-weight: 700; color: #F5F5F5;
             letter-spacing: 0.06em; display: flex; align-items: center;
             height: 116px; }
    .caret { display: inline-block; width: 4px; height: 74px;
             background: %s; margin-left: 10px; }
    .sub { font-size: 27px; color: #8A8F98; margin-top: 26px;
           white-space: nowrap; }
    """ % config.ACCENT_LINE_HEX
    body = f"""
    <div class='stage' id='stage'>
      <div class='logo' id='logo'>{logo_svg}</div>
      <div class='title'><span id='typed'></span><span class='caret' id='caret'></span></div>
      <div class='sub' id='sub'>{subtitle}</div>
    </div>
    """
    script = f"""
    const TITLE = {title!r};
    const paths = [...document.querySelectorAll('#logo path')];
    const lens = paths.map(p => {{
        const L = p.getTotalLength();
        p.style.strokeDasharray = L; p.style.strokeDashoffset = L;
        return L;
    }});
    const typed = document.getElementById('typed');
    const caret = document.getElementById('caret');
    const sub = document.getElementById('sub');
    const stage = document.getElementById('stage');

    const seg = (t, a, b) => Math.max(0, Math.min(1, (t - a) / (b - a)));
    const easeOut = t => 1 - Math.pow(1 - t, 3);

    window.__card = (t) => {{
        // 0.00-0.13  logo 依序描繪
        const dl = seg(t, 0.0, 0.133);
        paths.forEach((p, i) => {{
            const share = 1 / paths.length;
            const local = Math.max(0, Math.min(1, (dl - i * share * 0.75) / share));
            p.style.strokeDashoffset = lens[i] * (1 - easeOut(local));
        }});

        // 0.13-0.33  標題逐字浮現，游標在打字期間閃爍
        const tp = seg(t, 0.133, 0.333);
        typed.textContent = TITLE.slice(0, Math.round(tp * TITLE.length));
        const blink = t < 0.36 ? (Math.floor(t * 36) % 2 ? 0.25 : 1) : 0;
        caret.style.opacity = String(blink);

        // 0.33-0.50  副標字距收攏並淡入（放慢一些，補上原本細線展開佔的時間）
        const sp = seg(t, 0.333, 0.50);
        sub.style.opacity = String(easeOut(sp));
        sub.style.letterSpacing = (0.5 - 0.38 * easeOut(sp)).toFixed(3) + 'em';

        // 0.83-1.00  整體淡出並輕微上移
        const out = seg(t, 0.833, 1.0);
        stage.style.opacity = String(1 - out);
        stage.style.transform = `translateY(${{-26 * out}}px)`;
    }};
    window.__card(0);
    """
    return _html(body, css, script)


# ── 結尾卡 ──────────────────────────────────────────────────────

def outro_html(logo_svg: str, url: str, tagline: str) -> str:
    css = """
    .logo { width: 150px; height: 130px; margin-bottom: 30px; }
    .logo path { fill: none; stroke: #F5F5F5; stroke-width: 34;
                 stroke-linecap: round; stroke-linejoin: round; }
    .url { font-size: 46px; font-weight: 600; color: #F5F5F5;
           letter-spacing: 0.02em; }
    .tag { font-size: 25px; color: #8A8F98; margin-top: 24px;
           letter-spacing: 0.16em; text-indent: 0.08em; }
    """
    body = f"""
    <div class='stage' id='stage'>
      <div class='logo' id='logo'>{logo_svg}</div>
      <div class='url' id='url'>{url}</div>
      <div class='tag' id='tag'>{tagline}</div>
    </div>
    """
    script = """
    const stage = document.getElementById('stage');
    const url = document.getElementById('url');
    const tag = document.getElementById('tag');
    const logo = document.getElementById('logo');
    const seg = (t, a, b) => Math.max(0, Math.min(1, (t - a) / (b - a)));
    const easeOut = t => 1 - Math.pow(1 - t, 3);

    window.__card = (t) => {
        // 各元素依序收斂到中心：logo → 網址 → 標語 → 細線
        const lp = easeOut(seg(t, 0.0, 0.30));
        logo.style.opacity = String(lp);
        logo.style.transform = `scale(${0.90 + 0.10 * lp})`;

        const up = easeOut(seg(t, 0.14, 0.46));
        url.style.opacity = String(up);
        url.style.transform = `translateY(${(1 - up) * 16}px)`;

        const gp = easeOut(seg(t, 0.28, 0.62));
        tag.style.opacity = String(gp);
        tag.style.letterSpacing = (0.34 - 0.18 * gp).toFixed(3) + 'em';
        // 結尾卡刻意不自行淡出 —— 收尾由整片統一的 fade to black 處理，
        // 讓最後的網址在畫面上完整停留到最後一刻。
    };
    window.__card(0);
    """
    return _html(body, css, script)


# ── 渲染 ────────────────────────────────────────────────────────

@dataclass
class CardClip:
    """一張字卡渲染出的幀序列。"""

    name: str
    paths: list[Path]

    def __len__(self) -> int:
        return len(self.paths)


def load_logo() -> str:
    """讀入站方 logo。它本來就是純描邊路徑，天生適合做逐段描繪動畫。"""
    svg = config.LOGO_SVG.read_text(encoding="utf-8")
    # 移除內嵌 style，改由字卡 CSS 控制描邊顏色與粗細
    start, end = svg.find("<style>"), svg.find("</style>")
    if start != -1 and end != -1:
        svg = svg[:start] + svg[end + len("</style>"):]
    return svg


def render_card(page: Page, html: str, frames: int, out_dir: Path, name: str) -> CardClip:
    """把一張字卡渲染成 `frames` 張畫面。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = config.WORK_DIR / f"_card_{name}.html"
    tmp.write_text(html, encoding="utf-8")
    page.goto(tmp.as_uri())
    page.wait_for_timeout(280)   # 等字體與 SVG 就緒

    paths: list[Path] = []
    for i in range(frames):
        t = i / max(1, frames - 1)
        page.evaluate("(t) => window.__card(t)", t)
        p = out_dir / f"{name}_{i:04d}.png"
        page.screenshot(path=str(p))
        paths.append(p)
    return CardClip(name, paths)


def downscale(path: Path) -> Image.Image:
    """把 2× 超取樣的字卡縮到輸出尺寸。"""
    with Image.open(path) as im:
        return im.convert("RGB").resize(
            (config.WIDTH, config.HEIGHT), resample=Image.LANCZOS
        )

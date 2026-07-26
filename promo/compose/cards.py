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


# ── 手繪筆觸引擎 ────────────────────────────────────────────────
# logo.svg 的每一條 path 就是原稿的一筆。要讓它「像手畫出來的」，難處不在描繪本身
# ——`stroke-dashoffset` 誰都會寫——而在**筆的節奏**。以下六件事各自對應真人的一個習慣：
#
#   1. 先畫撐起形體的長筆，再補細節。手不會先點眼睛才畫身體。
#   2. 細節筆依「離上一筆落點最近」排序。這是手最省力的移動路徑，同一區的碎筆
#      因此自然連成一串，讀起來就是一區一區補完。
#   3. **時間跟著「新墨跡」走，不跟著長度走。** 這一條是關鍵。原稿的外框是兩趟
#      對描（一趟順走、一趟逆走），第二趟幾乎完全疊在第一趟上；若按長度配時間，
#      畫面會出現整整 0.4s 筆尖在跑、卻沒有任何東西長出來的空窗。真人遇到已經
#      畫過的線是直接掃過去的，所以這裡沿著每一筆取樣，落在既有線條上的取樣點
#      只計 RETRACE_COST 的時間成本 —— 重描的段落自動加速，新線條維持原速。
#   4. 每筆的時長再取成本的 SPEED_EXP 次方。長掃筆下手快、短碎筆慢而慎重，這才是
#      真人的筆速；純比例會讓七筆細節在三幀內閃完。
#   5. 筆與筆之間留停頓，長度正比於提筆移動的距離。跨區換手時停久一點。
#   6. 筆尖光點跟著描繪位置走，提筆時消失。這是「有人正在畫」最直接的線索。
#
# 全部從 SVG 自身量出來，沒有寫死任何一筆的索引 —— 換 logo 也不會壞。

_SPEED_EXP = 0.55    # 配時對筆的成本取此次方；1.0 = 等速，越小則短筆越慎重
_LIFT_BUDGET = 0.14  # 提筆停頓合計佔描繪總時長的比例
_STRUCTURE_AT = 0.25  # 達到最長筆這個比例以上者視為「撐形體的長筆」
_SAMPLE = 14.0       # 沿筆取樣的間距（SVG 使用者座標）
_NEAR = 30.0         # 與既有線條的距離小於此值即視為重描；略小於 stroke-width 34
_RETRACE_COST = 0.22  # 重描既有線條時的時間成本倍率 —— 手會直接掃過去
# 每一筆的成本下限，以「全部筆長總和」的比例表示（與 viewBox 尺度無關）。
# 有幾筆細節幾乎整條疊在外框上，成本被壓到只剩一幀，會像瑕疵一樣彈出來；
# 真人再怎麼掃，一個刻意落下的筆畫都有最短節拍。刻意不寫成筆長的比例 ——
# 那會把外框第二趟也一起墊回去，等於抵銷 RETRACE_COST。
_MIN_COST_SHARE = 0.006

_PEN_JS_TEMPLATE = """
// 回傳 draw(u)：u 為 0→1 的描繪進度，內部自行換算成第幾筆、畫到哪。
function makePen(root, ink, tip) {
    const svg = root.querySelector('svg');
    svg.insertAdjacentHTML('afterbegin',
        "<defs><radialGradient id='nibGlow'>" +
        "<stop offset='0%' stop-color='" + ink + "' stop-opacity='0.42'/>" +
        "<stop offset='55%' stop-color='" + ink + "' stop-opacity='0.13'/>" +
        "<stop offset='100%' stop-color='" + ink + "' stop-opacity='0'/>" +
        "</radialGradient></defs>");

    const strokes = [...root.querySelectorAll('path')].map(p => {
        const len = p.getTotalLength();
        p.style.strokeDasharray = len;
        p.style.strokeDashoffset = len;
        return { p, len, head: p.getPointAtLength(0), tail: p.getPointAtLength(len) };
    });

    // ① 長筆先畫，維持原稿順序（原稿的兩道外框本來就是一前一後的兩趟）
    const longest = Math.max(...strokes.map(s => s.len));
    const order = strokes.filter(s => s.len >= __STRUCTURE__ * longest);
    const rest = strokes.filter(s => s.len < __STRUCTURE__ * longest);

    // ② 細節筆貪心取最近者，等同手的移動路徑
    let at = order.length ? order[order.length - 1].tail : { x: 0, y: 0 };
    while (rest.length) {
        let best = 0, bestD = Infinity;
        rest.forEach((s, i) => {
            const d = Math.hypot(s.head.x - at.x, s.head.y - at.y);
            if (d < bestD) { bestD = d; best = i; }
        });
        const s = rest.splice(best, 1)[0];
        order.push(s);
        at = s.tail;
    }

    // ③ 沿每一筆取樣，算出「新墨跡成本」——落在既有線條上的段落只計零頭。
    //    空間雜湊格寬取 NEAR，查一個點只需看鄰近九格。
    const grid = new Map();
    const key = (p) => Math.floor(p.x / __NEAR__) + ',' + Math.floor(p.y / __NEAR__);
    const remember = (p) => {
        const k = key(p);
        let bucket = grid.get(k);
        if (!bucket) grid.set(k, bucket = []);
        bucket.push(p);
    };
    const isRetrace = (p) => {
        const i = Math.floor(p.x / __NEAR__), j = Math.floor(p.y / __NEAR__);
        for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
            const bucket = grid.get((i + a) + ',' + (j + b));
            if (!bucket) continue;
            for (const q of bucket) {
                if (Math.hypot(p.x - q.x, p.y - q.y) < __NEAR__) return true;
            }
        }
        return false;
    };

    for (const s of order) {
        const n = Math.max(2, Math.ceil(s.len / __SAMPLE__));
        const step = s.len / n;
        // 原稿好幾筆是「畫出去再描回來」，自我重疊也該加速。因此取樣點是邊走邊
        // 記進格子的，但刻意落後 lag 個取樣 —— 否則一筆會把自己剛走過的鄰近點
        // 當成既有線條，整筆都被判定為重描。
        const lag = Math.ceil(2.5 * __NEAR__ / step);
        const pts = [s.head];
        s.cum = [0];
        let cost = 0;
        for (let k = 1; k <= n; k++) {
            const pt = s.p.getPointAtLength(k * step);
            cost += step * (isRetrace(pt) ? __RETRACE__ : 1);
            s.cum.push(cost);
            pts.push(pt);
            if (k - lag >= 0) remember(pts[k - lag]);
        }
        for (let k = Math.max(0, n - lag + 1); k <= n; k++) remember(pts[k]);
        s.cost = cost;
    }

    // 成本下限只作用在配時上（beat），不動 cost —— cost 還要拿去做弧長映射，
    // 墊高它會讓筆畫在時段結束前就畫完。被墊到的筆等於整條放慢，正是要的效果。
    const totalLen = order.reduce((a, s) => a + s.len, 0);
    for (const s of order) s.beat = Math.max(s.cost, __MINCOST__ * totalLen);

    // ④⑤ 排出每一筆的 [t0, t1]：時長靠成本的 SPEED_EXP 次方，間隔靠提筆距離
    const draw = order.map(s => Math.pow(s.beat, __EXP__));
    const lift = order.map((s, i) => i === 0 ? 0
        : Math.sqrt(Math.hypot(s.head.x - order[i - 1].tail.x,
                               s.head.y - order[i - 1].tail.y)));
    const dSum = draw.reduce((a, b) => a + b, 0);
    const lSum = lift.reduce((a, b) => a + b, 0) || 1;

    let cursor = 0;
    order.forEach((s, i) => {
        cursor += __LIFTS__ * lift[i] / lSum;
        s.t0 = cursor;
        cursor += (1 - __LIFTS__) * draw[i] / dSum;
        s.t1 = cursor;
    });

    // 筆內進度 → 弧長：cum 是單調遞增的累積成本，二分搜尋回推再線性內插，
    // 筆尖才不會在取樣點之間跳動。重描段落的成本斜率低，同樣的時間走更長的弧。
    const arcAt = (s, r) => {
        const want = r * s.cost;
        let lo = 1, hi = s.cum.length - 1;
        while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (s.cum[mid] < want) lo = mid + 1; else hi = mid;
        }
        const c0 = s.cum[lo - 1], c1 = s.cum[lo];
        const f = c1 > c0 ? (want - c0) / (c1 - c0) : 0;
        return (lo - 1 + f) * s.len / (s.cum.length - 1);
    };

    // ⑥ 筆尖：外圈柔光 + 內圈實心點，半徑以 SVG 使用者座標計，隨版面自動縮放
    const NS = 'http://www.w3.org/2000/svg';
    const dot = (r, fill) => {
        const c = document.createElementNS(NS, 'circle');
        c.setAttribute('r', r);
        c.setAttribute('fill', fill);
        c.style.opacity = '0';
        svg.appendChild(c);
        return c;
    };
    const glow = dot(tip * 2.7, 'url(#nibGlow)');
    const nib = dot(tip, ink);

    // 筆畫內的極輕微加減速：起筆與收筆略慢，中段略快。幅度刻意壓在 ±35%，
    // 長掃筆才不會在中途頓一下。速度 v(t)=1-k·cos(2πt) 的積分。
    const hand = t => t - 0.35 * Math.sin(2 * Math.PI * t) / (2 * Math.PI);

    return (u) => {
        let live = null, liveLen = 0;
        for (const s of order) {
            const raw = (u - s.t0) / (s.t1 - s.t0);
            if (raw <= 0) { s.p.style.strokeDashoffset = s.len; continue; }
            if (raw >= 1) { s.p.style.strokeDashoffset = 0; continue; }
            const arc = arcAt(s, hand(raw));
            s.p.style.strokeDashoffset = s.len - arc;
            live = s; liveLen = arc;
        }
        if (live) {
            const pt = live.p.getPointAtLength(liveLen);
            for (const c of [glow, nib]) {
                c.setAttribute('cx', pt.x);
                c.setAttribute('cy', pt.y);
            }
            nib.style.opacity = '1';
            glow.style.opacity = '1';
        } else {
            // 提筆離紙，或全部畫完 —— 筆尖不該留在畫面上
            nib.style.opacity = '0';
            glow.style.opacity = '0';
        }
    };
}
"""

# 用 token 替換而非 %-formatting：JS 裡的 gradient offset 帶著 0% / 100%，
# 走 %-formatting 就得記得把每個字面百分號跳脫，換一次顏色就踩一次。
_PEN_JS = (
    _PEN_JS_TEMPLATE
    .replace("__EXP__", str(_SPEED_EXP))
    .replace("__LIFTS__", str(_LIFT_BUDGET))
    .replace("__STRUCTURE__", str(_STRUCTURE_AT))
    .replace("__SAMPLE__", str(_SAMPLE))
    .replace("__NEAR__", str(_NEAR))
    .replace("__RETRACE__", str(_RETRACE_COST))
    .replace("__MINCOST__", str(_MIN_COST_SHARE))
)


# ── 開場卡 ──────────────────────────────────────────────────────

def intro_html(logo_svg: str, title: str, subtitle: str) -> str:
    css = """
    .logo { width: 210px; height: 182px; margin-bottom: 34px; }
    /* 筆尖光點會探出 viewBox 邊界一點，不能讓它被裁掉 */
    .logo svg { width: 100%; height: 100%; overflow: visible; }
    .logo path { fill: none; stroke: #F5F5F5; stroke-width: 34;
                 stroke-linecap: round; stroke-linejoin: round; }
    .title { font-size: 92px; font-weight: 700; color: #F5F5F5;
             letter-spacing: 0.06em; display: flex; align-items: center;
             height: 116px; }
    .caret { display: inline-block; width: 4px; height: 74px;
             background: __ACCENT__; margin-left: 10px; }
    .sub { font-size: 27px; color: #8A8F98; margin-top: 26px;
           white-space: nowrap; }
    """.replace("__ACCENT__", config.ACCENT_LINE_HEX)
    body = f"""
    <div class='stage' id='stage'>
      <div class='logo' id='logo'>{logo_svg}</div>
      <div class='title'><span id='typed'></span><span class='caret' id='caret'></span></div>
      <div class='sub' id='sub'>{subtitle}</div>
    </div>
    """
    script = f"""
    {_PEN_JS}
    const TITLE = {title!r};
    // 筆尖半徑用 SVG 使用者座標：logo 的 stroke-width 是 34，取 0.7 倍讓筆尖
    // 略粗於線條，看得出是「筆」而不是線頭。
    const pen = makePen(document.getElementById('logo'), '#F5F5F5', 24);
    const typed = document.getElementById('typed');
    const caret = document.getElementById('caret');
    const sub = document.getElementById('sub');
    const stage = document.getElementById('stage');

    const seg = (t, a, b) => Math.max(0, Math.min(1, (t - a) / (b - a)));
    const easeOut = t => 1 - Math.pow(1 - t, 3);

    window.__card = (t) => {{
        // 0.00-0.35  一筆一筆手繪出 logo（6s 段落中的 2.1s）
        // 這裡刻意不套 easeOut —— 筆速的變化已經由 makePen 內部依筆長與提筆
        // 距離排定，外面再壓一層整體加減速只會把節奏抹平。
        pen(seg(t, 0.0, 0.35));

        // 0.37-0.56  標題逐字浮現，游標在打字期間閃爍
        const tp = seg(t, 0.37, 0.56);
        typed.textContent = TITLE.slice(0, Math.round(tp * TITLE.length));
        // 游標只在打字期間現身：logo 還在畫的時候讓它閃，會跟筆尖搶注意力
        const typing = t >= 0.36 && t < 0.60;
        caret.style.opacity = typing ? (Math.floor(t * 36) % 2 ? '0.25' : '1') : '0';

        // 0.57-0.71  副標字距收攏並淡入
        const sp = seg(t, 0.57, 0.71);
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

// stats-tooltip.js — 表格欄位說明 Tooltip（position:fixed，不受 overflow 裁切）
(function () {
    const tip = document.createElement('div');
    Object.assign(tip.style, {
        position:     'fixed',
        background:   'rgba(12,12,28,0.97)',
        color:        '#dde',
        fontSize:     '0.73rem',
        lineHeight:   '1.4',
        padding:      '5px 10px',
        borderRadius: '6px',
        border:       '1px solid ' + window.TW.primaryAlpha(0.12),
        boxShadow:    '0 4px 14px rgba(0,0,0,0.45)',
        pointerEvents:'none',
        zIndex:       '9999',
        maxWidth:     'min(380px, calc(100vw - 16px))',
        whiteSpace:   'normal',
        overflowWrap: 'break-word',
        visibility:   'hidden',
        opacity:      '0',
        transition:   'opacity 0.12s',
        textAlign:    'center',
    });
    document.body.appendChild(tip);

    var SVG_NS = 'http://www.w3.org/2000/svg';

    function svgEl(name, attrs, text) {
        var el = document.createElementNS(SVG_NS, name);
        for (var key in attrs) el.setAttribute(key, attrs[key]);
        if (text != null) el.textContent = text;
        return el;
    }

    // 好球帶區域圖：內圈 1–9 為好球帶九宮格，外圈 11–14 為好球帶外四象限（捕手視角）
    function buildZoneDiagram() {
        var OUT = { x: 6, y: 6, w: 168, h: 188 };
        var CELL_W = 32, CELL_H = 36;
        var IN_X = 42, IN_Y = 46;          // 九宮格左上角
        var IN_W = CELL_W * 3, IN_H = CELL_H * 3;
        var MID_X = IN_X + IN_W / 2, MID_Y = IN_Y + IN_H / 2;
        var outerStroke = window.TW.primaryAlpha(0.30);
        var innerStroke = window.TW.primaryAlpha(0.55);

        var svg = svgEl('svg', {
            viewBox: '0 0 180 200',
            width: '144',
            height: '160',
            role: 'img',
            'aria-label': '好球帶區域編號圖：中央九宮格 1 至 9，外圈四象限 11 至 14',
        });

        svg.appendChild(svgEl('rect', {
            x: OUT.x, y: OUT.y, width: OUT.w, height: OUT.h, rx: 3,
            fill: window.TW.primaryAlpha(0.04), stroke: outerStroke, 'stroke-width': 1.5,
        }));

        // 外圈四象限的分隔線（避開中央九宮格）
        [
            [MID_X, OUT.y, MID_X, IN_Y],
            [MID_X, IN_Y + IN_H, MID_X, OUT.y + OUT.h],
            [OUT.x, MID_Y, IN_X, MID_Y],
            [IN_X + IN_W, MID_Y, OUT.x + OUT.w, MID_Y],
        ].forEach(function (line) {
            svg.appendChild(svgEl('line', {
                x1: line[0], y1: line[1], x2: line[2], y2: line[3],
                stroke: outerStroke, 'stroke-width': 1.5,
            }));
        });

        // 中央九宮格 1–9
        for (var row = 0; row < 3; row++) {
            for (var col = 0; col < 3; col++) {
                var x = IN_X + col * CELL_W;
                var y = IN_Y + row * CELL_H;
                svg.appendChild(svgEl('rect', {
                    x: x, y: y, width: CELL_W, height: CELL_H,
                    fill: window.TW.primaryAlpha(0.08), stroke: innerStroke, 'stroke-width': 1.5,
                }));
                svg.appendChild(svgEl('text', {
                    x: x + CELL_W / 2, y: y + CELL_H / 2,
                    'text-anchor': 'middle', 'dominant-baseline': 'central',
                    fill: '#fff', 'font-size': '15', 'font-weight': '700',
                }, String(row * 3 + col + 1)));
            }
        }

        // 外圈 11–14
        [
            [11, OUT.x + 22, OUT.y + 24],
            [12, OUT.x + OUT.w - 22, OUT.y + 24],
            [13, OUT.x + 22, OUT.y + OUT.h - 24],
            [14, OUT.x + OUT.w - 22, OUT.y + OUT.h - 24],
        ].forEach(function (label) {
            svg.appendChild(svgEl('text', {
                x: label[1], y: label[2],
                'text-anchor': 'middle', 'dominant-baseline': 'central',
                fill: 'rgba(221,221,238,0.72)', 'font-size': '13', 'font-weight': '600',
            }, String(label[0])));
        });

        var wrap = document.createElement('div');
        Object.assign(wrap.style, { marginTop: '4px' });
        wrap.appendChild(svg);

        var caption = document.createElement('div');
        caption.textContent = '1–9 好球帶內 · 11–14 好球帶外（捕手視角）';
        Object.assign(caption.style, {
            marginTop: '2px',
            fontSize: '0.66rem',
            color: 'rgba(221,221,238,0.7)',
        });
        wrap.appendChild(caption);
        return wrap;
    }

    // data-diagram="<key>" 對應的示意圖產生器
    var DIAGRAMS = { zone: buildZoneDiagram };

    // data-legend='[["原值","中文"], ...]'：兩欄式對照表（無中文對照者顯示破折號）
    function buildLegend(raw) {
        var rows;
        try {
            rows = JSON.parse(raw);
        } catch (err) {
            return null;
        }
        if (!Array.isArray(rows) || !rows.length) return null;

        var grid = document.createElement('div');
        Object.assign(grid.style, {
            display: 'grid',
            gridTemplateColumns: 'auto auto',
            columnGap: '10px',
            rowGap: '2px',
            marginTop: '5px',
            textAlign: 'left',
            justifyContent: 'center',
        });
        rows.forEach(function (row) {
            if (!Array.isArray(row)) return;
            var term = document.createElement('div');
            term.textContent = String(row[0] == null ? '' : row[0]);
            Object.assign(term.style, {
                color: 'rgba(221,221,238,0.7)',
                whiteSpace: 'nowrap',
            });
            var zh = document.createElement('div');
            zh.textContent = row[1] ? String(row[1]) : '—';
            Object.assign(zh.style, { color: '#fff', whiteSpace: 'nowrap' });
            grid.appendChild(term);
            grid.appendChild(zh);
        });
        return grid.childElementCount ? grid : null;
    }

    var activeHeader = null;

    function positionTip(header) {
        var rect = header.getBoundingClientRect();
        var tipWidth = tip.offsetWidth;
        var tipHeight = tip.offsetHeight;
        var left = rect.left + rect.width / 2 - tipWidth / 2;
        var top = rect.top - tipHeight - 6;

        // 超出左右視窗邊界時夾住
        left = Math.max(4, Math.min(left, window.innerWidth - tipWidth - 4));
        // 若頂部空間不足則改為顯示在下方
        if (top < 4) top = rect.bottom + 6;

        tip.style.left = left + 'px';
        tip.style.top = top + 'px';
    }

    function showTip(header) {
        activeHeader = header;
        tip.textContent = '';
        var label = header.dataset.tooltip;
        var formula = header.dataset.formula;
        if (label) {
            var title = document.createElement('div');
            // Jinja strings commonly render "\\n" as two literal characters.
            // Normalize those escapes, then preserve both escaped and real
            // newlines without allowing arbitrary HTML in tooltip content.
            title.textContent = label.replace(/\\n/g, '\n');
            Object.assign(title.style, {
                fontWeight: '700',
                marginBottom: formula ? '4px' : '0',
                whiteSpace: 'pre-line',
            });
            tip.appendChild(title);
        }
        if (formula) {
            var formulaEl = document.createElement('div');
            Object.assign(formulaEl.style, {
                color: '#fff',
                fontSize: '0.82rem',
            });
            if (window.katex && typeof window.katex.render === 'function') {
                window.katex.render(formula, formulaEl, {
                    throwOnError: false,
                    displayMode: false,
                });
            } else {
                formulaEl.textContent = formula;
            }
            tip.appendChild(formulaEl);
        }
        var diagram = header.dataset.diagram;
        if (diagram && DIAGRAMS[diagram]) {
            tip.appendChild(DIAGRAMS[diagram]());
        }
        if (header.dataset.legend) {
            var legendEl = buildLegend(header.dataset.legend);
            if (legendEl) tip.appendChild(legendEl);
        }
        tip.style.visibility = 'visible';
        tip.style.opacity = '1';
        positionTip(header);
    }

    function hideTip() {
        activeHeader = null;
        tip.style.opacity = '0';
        tip.style.visibility = 'hidden';
    }

    document.addEventListener('mouseover', function (event) {
        var header = event.target.closest && event.target.closest('th[data-tooltip], th[data-formula]');
        if (!header || header === activeHeader || header.contains(event.relatedTarget)) return;
        showTip(header);
    });

    document.addEventListener('mouseout', function (event) {
        if (!activeHeader || activeHeader.contains(event.relatedTarget)) return;
        hideTip();
    });

    window.addEventListener('resize', function () {
        if (activeHeader) positionTip(activeHeader);
    });
}());

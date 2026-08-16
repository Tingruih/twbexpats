/**
 * pitch-plinko.js — Pitch Plinko 逐球球數分布圖
 * 載入於：tab_plot.j2（圖表 Tab）
 *
 * 作用：渲染「Pitch Plinko」互動式 SVG 圖表，
 * 以鑽石形節點圖呈現投手在各球數（0-0 到 3-2）投出各球種的分布比例：
 *  - 節點：每個球數對應一個圓形節點，大小代表到達次數，外環彩色圓弧代表球種比例
 *  - 邊線：代表球數轉換路徑（好球 or 壞球），粗細代表通過頻率
 *  - Tooltip：點擊節點或邊線時顯示詳細數據
 *  - 篩選：年份 + 聯盟層級，共用自 filters.js::createTieredLevelFilter
 *          （對稱：手機版見 mobile/m-charts.js::initMobilePlinkoFilters）
 *
 * 位置：圖表 Tab 的「Pitch Plinko」區塊（#plinko-root）
 *
 * 資料來源：partials/chart_data.j2 只渲染一次的 <script type="application/json"
 * id="chart-data-plinko-{year}-{index}">，經 window.TW.readJsonScript() 讀取
 * （單一真相來源，desktop/mobile 共用同一份，見 util.js）。
 *
 * 球種顏色／英文名經 window.TW.pitchTypeInfo() 讀 base.j2 注入的
 * #pitch-type-data（單一真相來源＝constants.py 的 PITCH_TYPES）。
 */
(function() {
    // 節點 ID 對應表（球數組合，從 0-0 到 3-2）
    var NODE_IDS = [
        "0-0",
        "0-1", "1-0",
        "0-2", "1-1", "2-0",
        "1-2", "2-1", "3-0",
        "2-2", "3-1",
        "3-2",
    ];
    var PLINKO_LAYOUT = {
        originX: 180,
        originY: 72,
        step: 64,
        viewBox: "0 0 424 452",
    };
    var EDGE_LAYOUT = [
        ["0-0", "0-1"], ["0-0", "1-0"],
        ["0-1", "0-2"], ["0-1", "1-1"],
        ["1-0", "1-1"], ["1-0", "2-0"],
        ["0-2", "1-2"],
        ["1-1", "1-2"], ["1-1", "2-1"],
        ["2-0", "2-1"], ["2-0", "3-0"],
        ["1-2", "2-2"],
        ["2-1", "2-2"], ["2-1", "3-1"],
        ["3-0", "3-1"],
        ["2-2", "3-2"], ["3-1", "3-2"],
    ];
    var NODE_LAYOUT = NODE_IDS.map(function(id) {
        var parts = String(id).split("-");
        var balls = Number(parts[0] || 0);
        var strikes = Number(parts[1] || 0);
        return {
            id: id,
            x: PLINKO_LAYOUT.originX + (balls - strikes) * PLINKO_LAYOUT.step,
            y: PLINKO_LAYOUT.originY + (balls + strikes) * PLINKO_LAYOUT.step,
        };
    });

    // XSS 防護
    var escapeHtml = window.TW.escapeHtml;  // 共用於 util.js（單一真相來源）

    function pct(value, digits) {
        if (value == null || value === "") return "-";
        var n = Number(value);
        return Number.isFinite(n) ? (n * 100).toFixed(digits == null ? 1 : digits) + "%" : "-";
    }

    function wholePct(value) {
        var n = Number(value || 0);
        return Math.round(n * 100) + "%";
    }

    function pitchName(pt) {
        var type = pt && pt.type ? String(pt.type).toUpperCase() : "UN";
        var info = window.TW.pitchTypeInfo(type);
        return (info && info.en) || type;
    }

    // #pitch-type-data（base.j2 注入，來源 constants.py）涵蓋所有會走到這裡
    // 的球種代碼（非球種代碼已在 Python 端由 filter_known_pitch_events 濾
    // 掉），所以 fallback 照理不會觸發。真的漏了就回傳純白 —— 刻意選一個明
    // 顯到不可能被當成正常球種色的值，讓缺漏當場現形，而不是像舊的循環色
    // 盤那樣悄悄借用別的球種色。
    function pitchColor(type) {
        var info = window.TW.pitchTypeInfo(type);
        return (info && info.bg) || "#ffffff";
    }

    function mapById(items, idField) {
        var out = Object.create(null);
        (items || []).forEach(function(item) {
            out[item[idField]] = item;
        });
        return out;
    }

    // 渲染球種圖例列（彩色圓點 + 名稱 + 投球數/比例）
    function renderLegend(data) {
        return (data.pitch_types || []).map(function(pt) {
            var type = pt.type || "UN";
            var color = pitchColor(type);
            return '<div class="pitch-plinko-legend-item">' +
                '<span class="pitch-plinko-swatch" style="background:' + color + '"></span>' +
                '<span>' + escapeHtml(pitchName(pt)) + ' (' + escapeHtml(pt.count || 0) + ', ' + pct(pt.pct, 1) + ')</span>' +
                '</div>';
        }).join("");
    }

    // 將 edge 陣列轉成以 "from>to" 為鍵的 map，方便快速查找
    function edgeMap(split) {
        var out = Object.create(null);
        (split.edges || []).forEach(function(edge) {
            out[edge.from + ">" + edge.to] = edge;
        });
        return out;
    }

    // 依投球數由大到小排序球種
    function sortPitchTypes(pitchTypes) {
        return (pitchTypes || []).slice().sort(function(a, b) {
            return Number(b.count || 0) - Number(a.count || 0);
        });
    }

    function edgeOutcomeLabel(fromCount, toCount) {
        var from = String(fromCount || "0-0").split("-").map(Number);
        var to = String(toCount || "0-0").split("-").map(Number);
        if (to[1] > from[1]) return "Strike";
        if (to[0] > from[0]) return "Ball";
        return "Count Change";
    }

    // 渲染所有邀線（球數轉換路徑），線寬/透明度代表通過頻率
    function renderEdges(split, nodeLayoutById, maxEdge) {
        var edges = edgeMap(split);
        return EDGE_LAYOUT.map(function(edgeDef) {
            var from = nodeLayoutById[edgeDef[0]];
            var to = nodeLayoutById[edgeDef[1]];
            var edge = edges[edgeDef[0] + ">" + edgeDef[1]] || { pitches: 0 };
            var count = Number(edge.pitches || 0);
            var ratio = count && maxEdge ? count / maxEdge : 0;
            var width = count ? 1.8 + Math.pow(ratio, 0.62) * 10.4 : 1.15;
            var opacity = count ? 0.34 + Math.pow(ratio, 0.55) * 0.54 : 0.18;
            var hitWidth = Math.max(16, width + 12);
            return '<g class="pitch-plinko-edge-group">' +
                '<line x1="' + from.x + '" y1="' + from.y + '" x2="' + to.x + '" y2="' + to.y + '" ' +
                'class="pitch-plinko-edge" stroke-width="' + width.toFixed(2) + '" opacity="' + opacity + '" />' +
                '<line x1="' + from.x + '" y1="' + from.y + '" x2="' + to.x + '" y2="' + to.y + '" ' +
                'class="pitch-plinko-edge-hit" stroke-width="' + hitWidth.toFixed(2) + '" data-split-key="' + escapeHtml(split.key || "") + '" ' +
                'data-from="' + escapeHtml(edgeDef[0]) + '" data-to="' + escapeHtml(edgeDef[1]) + '" />' +
                '</g>';
        }).join("");
    }

    // 渲染單一節點：園形大小=到達次數，外圈彩弧=球種比例
    function renderNode(nodeDef, node, splitKey) {
        var count = Number(node.pitches || 0);
        var fraction = Number(node.pct || 0);
        var radius = count ? Math.max(15, Math.min(35, 12 + Math.sqrt(fraction) * 46)) : 12;
        var ringWidth = count ? Math.max(7, Math.min(11, radius * 0.34)) : 2;
        var circumference = 2 * Math.PI * radius;
        var offset = 0;
        var sortedPitchTypes = sortPitchTypes(node.pitch_types || []);
        var segments = sortedPitchTypes.map(function(pt) {
            var seg = Math.max(0, Math.min(1, Number(pt.pct || 0)));
            var dash = seg * circumference;
            var dashOffset = -offset;
            offset += dash;
            return '<circle cx="' + nodeDef.x + '" cy="' + nodeDef.y + '" r="' + radius.toFixed(2) + '" ' +
                'fill="none" stroke="' + pitchColor(pt.type) + '" ' +
                'stroke-width="' + ringWidth.toFixed(2) + '" stroke-dasharray="' + dash.toFixed(2) + ' ' + (circumference - dash).toFixed(2) + '" ' +
                'stroke-dashoffset="' + dashOffset.toFixed(2) + '" transform="rotate(-90 ' + nodeDef.x + ' ' + nodeDef.y + ')" />';
        }).join("");
        var labelColor = count ? "#ff006f" : "#b8bec7";
        var nodeClass = count ? "pitch-plinko-node" : "pitch-plinko-node pitch-plinko-node-empty";
        return '<g class="' + nodeClass + '">' +
            '<text x="' + nodeDef.x + '" y="' + (nodeDef.y - radius - 10).toFixed(1) + '" class="pitch-plinko-count-label" fill="' + labelColor + '">' + escapeHtml(nodeDef.id) + '</text>' +
            '<circle cx="' + nodeDef.x + '" cy="' + nodeDef.y + '" r="' + radius.toFixed(2) + '" class="pitch-plinko-ring-bg" stroke-width="' + ringWidth.toFixed(2) + '" />' +
            segments +
            '<circle cx="' + nodeDef.x + '" cy="' + nodeDef.y + '" r="' + Math.max(3, radius - ringWidth / 2).toFixed(2) + '" class="pitch-plinko-node-center" />' +
            (count ? '<text x="' + nodeDef.x + '" y="' + nodeDef.y + '" class="pitch-plinko-node-pct">' + wholePct(fraction) + '</text>' : '') +
            '<circle cx="' + nodeDef.x + '" cy="' + nodeDef.y + '" r="' + (radius + 9).toFixed(2) + '" class="pitch-plinko-node-hit" data-split-key="' + escapeHtml(splitKey) + '" data-count="' + escapeHtml(nodeDef.id) + '" />' +
            '</g>';
    }

    // 渲染單一分組（左打/右打/全部）的完整 SVG
    function renderSplit(split, maxEdge) {
        var nodes = mapById(split.nodes || [], "count");
        var nodeLayoutById = mapById(NODE_LAYOUT, "id");
        var nodeSvg = NODE_LAYOUT.map(function(nodeDef) {
            return renderNode(nodeDef, nodes[nodeDef.id] || { count: nodeDef.id, pitches: 0, pct: null, pitch_types: [] }, split.key || "");
        }).join("");
        return '<section class="pitch-plinko-split">' +
            '<h4>' + escapeHtml(split.label || "") + ' <span>(' + escapeHtml(split.pitches || 0) + ' pitches, ' + pct(split.pct, 1) + ')</span></h4>' +
            '<svg class="pitch-plinko-svg" viewBox="' + PLINKO_LAYOUT.viewBox + '" role="img" aria-label="' + escapeHtml(split.label || "Pitch Plinko") + '">' +
                renderEdges(split, nodeLayoutById, maxEdge) + nodeSvg +
            '</svg>' +
            '</section>';
    }

    function findNode(data, splitKey, count) {
        var split = (data.splits || []).find(function(item) { return String(item.key || "") === String(splitKey || ""); });
        if (!split) return null;
        return (split.nodes || []).find(function(node) { return String(node.count) === String(count); }) || null;
    }

    function findEdge(data, splitKey, fromCount, toCount) {
        var split = (data.splits || []).find(function(item) { return String(item.key || "") === String(splitKey || ""); });
        if (!split) return null;
        return (split.edges || []).find(function(edge) {
            return String(edge.from) === String(fromCount) && String(edge.to) === String(toCount);
        }) || null;
    }

    function tooltipHtml(node) {
        var rows = sortPitchTypes(node.pitch_types || []).map(function(pt) {
            return '<div class="pitch-plinko-tooltip-row">' +
                '<span class="pitch-plinko-tooltip-dot" style="background:' + pitchColor(pt.type) + '"></span>' +
                '<span class="pitch-plinko-tooltip-name">' + escapeHtml(pitchName(pt)) + '</span>' +
                '<strong>' + escapeHtml(pt.count || 0) + '</strong>' +
                '<span>' + pct(pt.pct, 1) + '</span>' +
                '</div>';
        }).join("");
        return '<div class="pitch-plinko-tooltip-title"><strong>' + escapeHtml(node.count) + ' Count</strong> <span>' + escapeHtml(node.pitches || 0) + ' pitches</span></div>' + rows;
    }

    function edgeTooltipHtml(edge) {
        var outcome = edgeOutcomeLabel(edge.from, edge.to);
        var accentClass = "pitch-plinko-tooltip-accent" + (outcome === "Ball" ? " pitch-plinko-tooltip-accent--ball" : "");
        return '<div class="pitch-plinko-tooltip-title pitch-plinko-tooltip-title--stacked">' +
            '<strong>' + escapeHtml(edge.from) + ' → ' + escapeHtml(edge.to) + '</strong>' +
            '<span class="' + accentClass + '">' + escapeHtml(outcome) + '</span>' +
            '<span>' + escapeHtml(edge.pitches || 0) + ' pitches</span>' +
            '</div>';
    }

    // Tooltip 定位邏輯共用於 pitcher-charts.js（球種位移圖），見 util.js 的
    // TW.positionTooltipNearPointer。舊版永遠貼在指標右側，游標右邊的節點/邊線
    // 會被 tooltip 蓋住；共用版依指標所在左右半邊決定貼左或貼右，避免擋道。
    var moveTooltip = window.TW.positionTooltipNearPointer;

    function bindTooltips(root, data) {
        var tooltip = root.querySelector(".pitch-plinko-tooltip");
        if (!tooltip) return;
        root.querySelectorAll(".pitch-plinko-node-hit").forEach(function(hit) {
            hit.addEventListener("pointerenter", function(event) {
                var node = findNode(data, hit.dataset.splitKey, hit.dataset.count);
                if (!node || !node.pitches) return;
                tooltip.innerHTML = tooltipHtml(node);
                tooltip.classList.add("pitch-plinko-tooltip--visible");
                moveTooltip(root, tooltip, event);
            });
            hit.addEventListener("pointermove", function(event) {
                if (tooltip.classList.contains("pitch-plinko-tooltip--visible")) {
                    moveTooltip(root, tooltip, event);
                }
            });
            hit.addEventListener("pointerleave", function() {
                tooltip.classList.remove("pitch-plinko-tooltip--visible");
            });
        });
        root.querySelectorAll(".pitch-plinko-edge-hit").forEach(function(hit) {
            hit.addEventListener("pointerenter", function(event) {
                var edge = findEdge(data, hit.dataset.splitKey, hit.dataset.from, hit.dataset.to);
                if (!edge || !edge.pitches) return;
                tooltip.innerHTML = edgeTooltipHtml(edge);
                tooltip.classList.add("pitch-plinko-tooltip--visible");
                moveTooltip(root, tooltip, event);
            });
            hit.addEventListener("pointermove", function(event) {
                if (tooltip.classList.contains("pitch-plinko-tooltip--visible")) {
                    moveTooltip(root, tooltip, event);
                }
            });
            hit.addEventListener("pointerleave", function() {
                tooltip.classList.remove("pitch-plinko-tooltip--visible");
            });
        });
    }

    function renderPitchPlinko(root, data) {
        if (!root) return;
        if (!data || !data.total_pitches || !Array.isArray(data.splits) || !data.splits.length) {
            root.innerHTML = '<div class="pitch-plinko-empty">尚無逐球數資料</div>';
            return;
        }
        var maxEdge = 1;
        (data.splits || []).forEach(function(split) {
            (split.edges || []).forEach(function(edge) {
                maxEdge = Math.max(maxEdge, Number(edge.pitches || 0));
            });
        });
        root.innerHTML = '<div class="pitch-plinko-card">' +
            '<div class="pitch-plinko-heading"><h3>球種逐球數分布圖</h3></div>' +
            '<div class="pitch-plinko-grid">' +
                (data.splits || []).map(function(split) { return renderSplit(split, maxEdge); }).join("") +
            '</div>' +
            '<div class="pitch-plinko-legend">' + renderLegend(data) + '</div>' +
            '<div class="pitch-plinko-tooltip"></div>' +
            '</div>';
        bindTooltips(root, data);
    }

    function initPitchPlinkoCharts() {
        document.querySelectorAll(".pitch-plinko-level-container").forEach(function(container) {
            var root = container.querySelector(".pitch-plinko-root");
            var data = window.TW.readJsonScript("chart-data-plinko-" + container.dataset.chartKey, {});
            renderPitchPlinko(root, data);
        });
    }

    function initPitchPlinkoFilters() {
        window.TWFilters.createTieredLevelFilter({
            yearSelectId: "plinko-year-select",
            levelSelectId: "plinko-level-select",
            yearContainerPrefix: "plinko-",
            levelContainerSelector: ".pitch-plinko-level-container",
            hideYearContainers: function () {
                document.querySelectorAll(".pitch-plinko-year-container").forEach(function (c) {
                    c.style.display = "none";
                });
            },
        });
    }

    document.addEventListener("DOMContentLoaded", function() {
        initPitchPlinkoCharts();
        initPitchPlinkoFilters();
    });
})();

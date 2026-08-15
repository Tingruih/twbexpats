/**
 * pitcher-charts.js — 投手球種 SVG 圖表渲染
 * 載入於：tab_plot.j2（圖表 Tab）
 *
 * 作用：讀取嵌入頁面的 JSON 資料，渲染兩種 SVG 圖表：
 *  1. renderUsageByHand(root, data)
 *     對左打/右打的球種使用率橫條圖（左右對稱棒狀圖）
 *     位置：圖表 Tab 的「對左右打球種使用率」區塊
 *
 *  2. renderMovement(root, data)
 *     球種位移散點圖（水平/垂直位移的 x-y scatter plot）
 *     位置：圖表 Tab 的「球種位移」區塊，滑鼠移入圓點顯示 tooltip
 *
 * 依賴：partials/chart_data.j2 只渲染一次的 <script type="application/json"
 * id="chart-data-{kind}-{year}-{index}"> 資料，經 window.TW.readJsonScript() 讀取
 * （單一真相來源，desktop/mobile 共用同一份，見 util.js）；
 * 球種顏色／英文名經 window.TW.pitchTypeInfo() 讀 base.j2 注入的
 * #pitch-type-data（單一真相來源＝constants.py 的 PITCH_TYPES）。
 */
(function() {
    // XSS 防護：將字串中的 HTML 特殊字元做 escape
    var escapeHtml = window.TW.escapeHtml;  // 共用於 util.js（單一真相來源）

    function num(value) {
        if (value == null || value === "") return null;
        var n = Number(value);
        return Number.isFinite(n) ? n : null;
    }

    // 格式化百分比（0~1 的小數 → "12.3%" 字串）
    function fmtPct(value, digits) {
        var n = num(value);
        return n == null ? "-" : (n * 100).toFixed(digits == null ? 1 : digits) + "%";
    }

    // 格式化一般數值（速度/轉速等），null 回傳 '-'
    function fmtStat(value, digits) {
        var n = num(value);
        if (n == null) return "-";
        return digits == null ? String(Math.round(n)) : n.toFixed(digits);
    }

    function pitchName(item) {
        var type = item && item.type ? String(item.type).toUpperCase() : "UN";
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

    function splitArsenal(data, key) {
        var split = data && data[key] ? data[key] : null;
        return split && Array.isArray(split.pitch_arsenal) ? split.pitch_arsenal : [];
    }

    function mapPitchRows(rows) {
        var out = Object.create(null);
        (rows || []).forEach(function(row) {
            var type = row.type || "UN";
            out[type] = row;
        });
        return out;
    }

    function sumCounts(rows) {
        return (rows || []).reduce(function(total, row) {
            return total + Number(row.count || 0);
        }, 0);
    }

    function emptyChart(root, message) {
        if (!root) return;
        root.innerHTML = '<div class="pitch-chart-empty">' + escapeHtml(message) + '</div>';
    }

    // 渲染「對左右打球種使用率」橫條圖 SVG
    function renderUsageByHand(root, data) {
        if (!root) return;
        var leftRows = splitArsenal(data, "L");
        var rightRows = splitArsenal(data, "R");
        var leftByType = mapPitchRows(leftRows);
        var rightByType = mapPitchRows(rightRows);
        var types = [];
        Object.keys(leftByType).concat(Object.keys(rightByType)).forEach(function(type) {
            if (types.indexOf(type) === -1) types.push(type);
        });
        types.sort(function(a, b) {
            var ac = Number((leftByType[a] && leftByType[a].count) || 0) + Number((rightByType[a] && rightByType[a].count) || 0);
            var bc = Number((leftByType[b] && leftByType[b].count) || 0) + Number((rightByType[b] && rightByType[b].count) || 0);
            return bc - ac;
        });

        if (!types.length) {
            emptyChart(root, "尚無左右打配球資料");
            return;
        }

        var width = 760;
        var minHeight = 516;
        var top = 18;
        var bottom = 78;
        var left = 116;
        var right = 54;
        var plotWidth = width - left - right;
        var center = left + plotWidth / 2;
        var half = plotWidth / 2;
        var height = Math.max(minHeight, top + bottom + types.length * 52);
        var rowStep = (height - top - bottom) / types.length;
        var ticks = [-1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1];
        var grid = ticks.map(function(tick) {
            var x = center + tick * half;
            var gridLine = tick === 0 ? "" :
                '<line class="pitch-chart-gridline" x1="' + x.toFixed(1) + '" y1="' + top + '" x2="' + x.toFixed(1) + '" y2="' + (height - bottom + 12) + '" />';
            return gridLine +
                '<text class="pitch-chart-tick-label" x="' + x.toFixed(1) + '" y="' + (height - 42) + '">' + Math.round(Math.abs(tick) * 100) + '%</text>';
        }).join("");
        var centerLine = '<line class="pitch-chart-zero-line pitch-chart-zero-line--foreground" x1="' + center.toFixed(1) + '" y1="' + top + '" x2="' + center.toFixed(1) + '" y2="' + (height - bottom + 12) + '" />';

        var rows = types.map(function(type, index) {
            var leftRow = leftByType[type] || null;
            var rightRow = rightByType[type] || null;
            var leftPct = Math.max(0, Math.min(1, num(leftRow && leftRow.pct) || 0));
            var rightPct = Math.max(0, Math.min(1, num(rightRow && rightRow.pct) || 0));
            var y = top + index * rowStep + rowStep / 2;
            var barHeight = Math.min(34, Math.max(24, rowStep - 18));
            var color = pitchColor(type);
            var labelItem = leftRow || rightRow || { type: type };
            var leftWidth = leftPct * half;
            var rightWidth = rightPct * half;
            var leftLabelX = Math.max(10, center - leftWidth - 9);
            var rightLabelX = Math.min(width - 10, center + rightWidth + 9);
            return '<g>' +
                '<text class="pitch-chart-row-label" x="' + (left - 18) + '" y="' + y.toFixed(1) + '">' + escapeHtml(pitchName(labelItem)) + '</text>' +
                (leftWidth ? '<rect class="pitch-usage-bar" x="' + (center - leftWidth).toFixed(1) + '" y="' + (y - barHeight / 2).toFixed(1) + '" width="' + leftWidth.toFixed(1) + '" height="' + barHeight + '" fill="' + color + '" />' : '') +
                (rightWidth ? '<rect class="pitch-usage-bar" x="' + center.toFixed(1) + '" y="' + (y - barHeight / 2).toFixed(1) + '" width="' + rightWidth.toFixed(1) + '" height="' + barHeight + '" fill="' + color + '" />' : '') +
                (leftRow ? '<text class="pitch-usage-value-label pitch-usage-value-label--left" x="' + leftLabelX.toFixed(1) + '" y="' + y.toFixed(1) + '">' + fmtPct(leftPct, 1) + '</text>' : '') +
                (rightRow ? '<text class="pitch-usage-value-label" x="' + rightLabelX.toFixed(1) + '" y="' + y.toFixed(1) + '">' + fmtPct(rightPct, 1) + '</text>' : '') +
                '</g>';
        }).join("");

        var leftTotal = sumCounts(leftRows);
        var rightTotal = sumCounts(rightRows);
        root.innerHTML = '<div class="pitch-chart-heading"><h3>對左右打球種使用率</h3></div>' +
            '<svg class="pitch-chart-svg pitch-usage-hand-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="Pitch Usage by Batter Hand">' +
            grid + rows +
            '<text class="pitch-chart-axis-label" x="' + center + '" y="' + (height - 16) + '">Usage %</text>' +
            '<text class="pitch-chart-hand-label" x="' + (center - half * 0.5) + '" y="' + (height - 16) + '">vs LHH (' + leftTotal + ')</text>' +
            '<text class="pitch-chart-hand-label" x="' + (center + half * 0.5) + '" y="' + (height - 16) + '">vs RHH (' + rightTotal + ')</text>' +
            centerLine +
            '</svg>';
    }

    function ceilStep(value, step) {
        return Math.ceil(value / step) * step;
    }

    function floorStep(value, step) {
        return Math.floor(value / step) * step;
    }

    function ticks(min, max, step) {
        var out = [];
        for (var v = min; v <= max + 0.0001; v += step) out.push(v);
        return out;
    }

    // Tooltip 定位邏輯共用於 pitch-plinko.js，見 util.js 的
    // TW.positionTooltipNearPointer
    var moveTooltip = window.TW.positionTooltipNearPointer;

    function movementTooltipHtml(el) {
        return '<div class="pitch-chart-tooltip-title">' + escapeHtml(el.dataset.name || el.dataset.type || "Pitch") + '</div>' +
            '<div class="pitch-chart-tooltip-row"><span>Velo</span><strong>' + escapeHtml(fmtStat(el.dataset.velo, 1)) + '</strong></div>' +
            '<div class="pitch-chart-tooltip-row"><span>Spin</span><strong>' + escapeHtml(fmtStat(el.dataset.spin)) + '</strong></div>' +
            '<div class="pitch-chart-tooltip-row"><span>HB</span><strong>' + escapeHtml(fmtStat(el.dataset.hb, 1)) + '</strong></div>' +
            '<div class="pitch-chart-tooltip-row"><span>iVB</span><strong>' + escapeHtml(fmtStat(el.dataset.ivb, 1)) + '</strong></div>';
    }

    function bindMovementTooltips(root) {
        var tooltip = root.querySelector(".pitch-chart-tooltip");
        if (!tooltip) return;
        root.querySelectorAll(".pitch-movement-point").forEach(function(point) {
            point.addEventListener("pointerenter", function(event) {
                tooltip.innerHTML = movementTooltipHtml(point);
                tooltip.classList.add("pitch-chart-tooltip--visible");
                moveTooltip(root, tooltip, event);
            });
            point.addEventListener("pointermove", function(event) {
                if (tooltip.classList.contains("pitch-chart-tooltip--visible")) {
                    moveTooltip(root, tooltip, event);
                }
            });
            point.addEventListener("pointerleave", function() {
                tooltip.classList.remove("pitch-chart-tooltip--visible");
            });
        });
    }

    // \u6e32\u67d3\u300c\u7403\u7a2e\u4f4d\u79fb\u6563\u9ede\u5716\u300d SVG\uff08\u6c34\u5e73\u4f4d\u79fb HB vs. \u5782\u76f4\u4f4d\u79fb iVB\uff09
    function renderMovement(root, data) {
        if (!root) return;
        // 每點是 Python 端輸出的 [type, hb, ivb, velo, spin] 定長陣列（省 payload），
        // 這裡先還原成物件，下面的繪點/tooltip 才能照舊用具名欄位。
        var points = ((data && data.points) || []).map(function(p) {
            return { type: p[0], hb: p[1], ivb: p[2], velo: p[3], spin: p[4] };
        }).filter(function(point) {
            return num(point.hb) != null && num(point.ivb) != null;
        });
        if (!points.length) {
            emptyChart(root, "尚無投球位移資料");
            return;
        }

        var width = 760;
        var height = 520;
        var left = 74;
        var right = 28;
        var top = 18;
        var bottom = 82;
        var plotWidth = width - left - right;
        var plotHeight = height - top - bottom;
        var xs = points.map(function(point) { return num(point.hb) || 0; });
        var ys = points.map(function(point) { return num(point.ivb) || 0; });
        var maxAbsX = Math.max(10, ceilStep(Math.max.apply(null, xs.map(Math.abs)), 5));
        var minY = Math.min.apply(null, ys);
        var maxY = Math.max.apply(null, ys);
        var yMin = Math.min(-10, floorStep(minY, 5));
        var yMax = Math.max(10, ceilStep(maxY, 5));
        if (yMax - yMin < 20) {
            yMin -= 5;
            yMax += 5;
        }
        var xStep = maxAbsX > 20 ? 10 : 5;
        var yStep = (yMax - yMin) > 30 ? 10 : 5;
        var xTicks = ticks(-maxAbsX, maxAbsX, xStep);
        var yTicks = ticks(yMin, yMax, yStep);

        function xScale(value) {
            return left + ((value + maxAbsX) / (maxAbsX * 2)) * plotWidth;
        }

        function yScale(value) {
            return top + ((yMax - value) / (yMax - yMin)) * plotHeight;
        }

        var grid = xTicks.map(function(tick) {
            var x = xScale(tick);
            var cls = tick === 0 ? "pitch-chart-zero-line" : "pitch-chart-gridline";
            return '<line class="' + cls + '" x1="' + x.toFixed(1) + '" y1="' + top + '" x2="' + x.toFixed(1) + '" y2="' + (height - bottom) + '" />' +
                '<text class="pitch-chart-tick-label" x="' + x.toFixed(1) + '" y="' + (height - bottom + 25) + '">' + tick + '</text>';
        }).join("") + yTicks.map(function(tick) {
            var y = yScale(tick);
            var cls = tick === 0 ? "pitch-chart-zero-line pitch-chart-zero-line--horizontal" : "pitch-chart-gridline";
            return '<line class="' + cls + '" x1="' + left + '" y1="' + y.toFixed(1) + '" x2="' + (width - right) + '" y2="' + y.toFixed(1) + '" />' +
                '<text class="pitch-chart-y-tick-label" x="' + (left - 12) + '" y="' + y.toFixed(1) + '">' + tick + '</text>';
        }).join("");

        var pointSvg = points.map(function(point) {
            var type = point.type || "UN";
            var color = pitchColor(type);
            return '<circle class="pitch-movement-point" cx="' + xScale(num(point.hb)).toFixed(1) + '" cy="' + yScale(num(point.ivb)).toFixed(1) + '" r="4.6" fill="' + color + '" ' +
                'data-type="' + escapeHtml(type) + '" data-name="' + escapeHtml(pitchName(point)) + '" data-velo="' + escapeHtml(point.velo == null ? "" : point.velo) + '" ' +
                'data-spin="' + escapeHtml(point.spin == null ? "" : point.spin) + '" data-hb="' + escapeHtml(point.hb) + '" data-ivb="' + escapeHtml(point.ivb) + '" />';
        }).join("");

        var legend = '<div class="pitch-chart-legend">' + ((data && data.pitch_types) || []).map(function(pt) {
            return '<span class="pitch-chart-legend-item"><i style="background:' + pitchColor(pt.type) + '"></i>' + escapeHtml(pitchName(pt)) + '</span>';
        }).join("") + '</div>';

        root.innerHTML = '<div class="pitch-chart-heading"><h3>球種位移</h3></div>' +
            '<svg class="pitch-chart-svg pitch-movement-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="Pitch Movement">' +
            grid + pointSvg +
            '<text class="pitch-chart-axis-label" x="' + (left + plotWidth / 2) + '" y="' + (height - 20) + '">Horizontal Break (in)</text>' +
            '<text class="pitch-chart-axis-label pitch-chart-axis-label--vertical" x="22" y="' + (top + plotHeight / 2) + '" transform="rotate(-90 22 ' + (top + plotHeight / 2) + ')">Induced Vertical Break (in)</text>' +
            '</svg>' + legend + '<div class="pitch-chart-tooltip"></div>';
        bindMovementTooltips(root);
    }

    function initPitcherCharts() {
        document.querySelectorAll(".pitch-plinko-level-container").forEach(function(container) {
            var key = container.dataset.chartKey;
            var usageRoot = container.querySelector(".pitch-usage-hand-root");
            if (usageRoot) renderUsageByHand(usageRoot, window.TW.readJsonScript("chart-data-usage-" + key, {}));
            var movementRoot = container.querySelector(".pitch-movement-root");
            if (movementRoot) renderMovement(movementRoot, window.TW.readJsonScript("chart-data-movement-" + key, {}));
        });
    }

    document.addEventListener("DOMContentLoaded", initPitcherCharts);
})();

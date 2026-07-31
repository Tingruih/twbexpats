/**
 * util.js — 全站共用前端小工具（單一真相來源）
 * 載入於：base.j2（於所有其他腳本之前，defer 保證執行順序）
 *
 * 對外暴露 window.TW：
 *  - TW.escapeHtml(value)                    ：HTML 轉義，供動態 innerHTML 防注入
 *  - TW.populateLevelSelect(sel, items, opts)：填充聯盟層級 <select>
 *  - TW.levelItemsFromContainers(list)       ：把 .*-level-container NodeList
 *                                              轉成 populateLevelSelect 需要的陣列
 *  - TW.trendStatConfig                      ：賽季走勢圖「數據」下拉選單的
 *                                              顯示設定（百分比/小數位數/單位）
 *  - TW.buildTrendChartData(games, statKey)
 *                                             ：把某層級的 games 陣列轉成
 *                                              {labels, values, average}，供
 *                                              charts.js / m-charts.js 共用
 *  - TW.hasTrendStat(games, statKey)           ：判斷一組比賽是否至少有一筆指定數據
 *  - TW.formatTrendValue(cfg, v)             ：依走勢圖設定格式化數值
 *  - TW.renderTrendLegend(legendEl, datasets)：把走勢圖圖例畫成 HTML（非 Chart.js
 *                                              canvas 圖例），避免自訂 generateLabels
 *                                              導致文字顏色跑掉的問題
 *  - TW.trendTooltipLabelPointStyle(item)    ：tooltip callbacks.labelPointStyle，把
 *                                              色塊畫成跟圖例一致的線段樣式（實線/虛線）
 *  - TW.pitchTypeInfo(code)                  ：查球種代碼的中英文名／配色
 *                                              （{zh,en,family,group,bg,text}），
 *                                              讀 base.j2 注入的 #pitch-type-data，
 *                                              查無資料回傳 null
 *
 * 過去 escapeHtml 在 pitcher-charts.js / pitch-plinko.js 各有一份、
 * level-select 填充邏輯散落 6 個檔案；集中於此後「改一處即全站生效」。
 * 球種中英文名／配色同理：過去兩份圖表腳本各自手抄一份 PITCH_COLORS /
 * PITCH_NAMES，跟 constants.py 的中文譯名分開維護，容易分歧（見
 * constants.py 頂部 PITCH_TYPES 的說明）。
 */
window.TW = (function () {
    "use strict";

    // HTML 轉義：把 & < > " ' 轉成 entity，避免動態插入時被當成標籤/屬性
    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    // 惰性讀取＋快取 #pitch-type-data（base.j2 注入的 JSON），查無該代碼
    // 或找不到 script tag 時回傳 null，呼叫端各自決定 fallback。
    var _pitchTypeData = null;
    function pitchTypeInfo(code) {
        if (_pitchTypeData === null) {
            var script = document.getElementById("pitch-type-data");
            try { _pitchTypeData = script ? JSON.parse(script.textContent || "{}") : {}; }
            catch (err) { _pitchTypeData = {}; }
        }
        return _pitchTypeData[String(code || "").toUpperCase()] || null;
    }

    /**
     * 以一組選項填充聯盟層級 <select>。
     * @param {HTMLSelectElement} sel  目標 <select>（null 時安全略過）
     * @param {Array<{value:string,label:string,selected?:boolean}>} items 選項
     * @param {{allOption?:boolean, allLabel?:string, allValue?:string}} [opts]
     *        allOption 為 true 時，最前面插入一個「All Levels」彙總選項
     */
    function populateLevelSelect(sel, items, opts) {
        if (!sel) return;
        opts = opts || {};
        sel.innerHTML = "";
        if (opts.allOption) {
            var all = document.createElement("option");
            all.value = opts.allValue || "_all";
            all.textContent = opts.allLabel || "All Levels";
            sel.appendChild(all);
        }
        (items || []).forEach(function (it) {
            var opt = document.createElement("option");
            opt.value = it.value;
            opt.textContent = it.label;
            if (it.selected) opt.selected = true;
            sel.appendChild(opt);
        });
    }

    /**
     * 把一組 .*-level-container 元素（帶 data-level / data-level-label）
     * 轉成 populateLevelSelect 的 items；預設第一個為選中。
     * @param {NodeList|Array} containers
     * @returns {Array<{value:string,label:string,selected:boolean}>}
     */
    function levelItemsFromContainers(containers) {
        var items = [];
        Array.prototype.forEach.call(containers, function (c, i) {
            items.push({
                value: c.dataset.level,
                label: c.dataset.levelLabel,
                selected: i === 0,
            });
        });
        return items;
    }

    // 賽季走勢圖「數據」選單設定：isPercent 決定要不要 ×100，decimals/suffix
    // 供 tooltip、Y 軸、標題顯示格式化用。
    var TREND_STAT_CONFIG = {
        era: { label: "ERA", isPercent: false, decimals: 2 },
        avg: { label: "AVG", isPercent: false, decimals: 3 },
        woba: { label: "wOBA", isPercent: false, decimals: 3 },
        k_pct: { label: "K%", isPercent: true, decimals: 1 },
        bb_pct: { label: "BB%", isPercent: true, decimals: 1 },
        whiff_pct: { label: "Whiff%", isPercent: true, decimals: 1 },
        csw_pct: { label: "CSW%", isPercent: true, decimals: 1 },
        swstr_pct: { label: "SwStr%", isPercent: true, decimals: 1 },
        chase_pct: { label: "Chase%", isPercent: true, decimals: 1 },
        z_contact_pct: { label: "Z-Contact%", isPercent: true, decimals: 1 },
        hard_hit_pct: { label: "HardHit%", isPercent: true, decimals: 1 },
        barrel_pct: { label: "Barrel%", isPercent: true, decimals: 1 },
        exit_velocity: { label: "Exit Velocity", isPercent: false, decimals: 1, suffix: " mph" },
        sweet_spot_pct: { label: "SweetSpot%", isPercent: true, decimals: 1 },
    };

    /**
     * 把某層級（或前端合併多層級後）的 games 陣列轉成 Chart.js 要的資料。
     * @param {Array<Object>} games   後端 trend builder 的 games 陣列
     * @param {string} statKey        TREND_STAT_CONFIG 的 key
     * @returns {{labels:string[], values:(number|null)[], average:number|null}}
     *          average 是「賽季至今」數據：每個 g[statKey] 本身已經是累計到
     *          該場為止的season-to-date值（見 season_trend.py 的計算註解），
     *          所以賽季平均＝最後一個非 null 值，而不是把每場的累計值再平均
     *          一次（那樣早期樣本數小、還不穩定的快照會被賦予跟最後一筆同樣
     *          的權重，算出來的數字沒有意義）。全為 null 時回傳 null。
     */
    function buildTrendChartData(games, statKey) {
        var cfg = TREND_STAT_CONFIG[statKey] || { isPercent: false };
        var labels = [];
        var values = [];
        var average = null;
        (games || []).forEach(function (g) {
            labels.push(g.date);
            var raw = g[statKey];
            var v = raw == null ? null : (cfg.isPercent ? raw * 100 : raw);
            values.push(v);
            if (v != null) average = v;
        });
        return { labels: labels, values: values, average: average };
    }

    function hasTrendStat(games, statKey) {
        return (games || []).some(function (game) {
            return game[statKey] != null;
        });
    }

    // 依「數據」設定格式化數值（小數位數 / 百分比或自訂單位後綴）
    function formatTrendValue(cfg, v) {
        if (v == null) return "-";
        cfg = cfg || {};
        var decimals = cfg.decimals != null ? cfg.decimals : 2;
        var suffix = cfg.suffix || (cfg.isPercent ? "%" : "");
        return v.toFixed(decimals) + suffix;
    }

    /**
     * 走勢圖圖例：畫成 HTML（線段樣式的色條 + 文字），取代 Chart.js 內建 canvas
     * 圖例。避免自訂 generateLabels + pointStyle:'line' 時文字顏色無法正確套用
     * labels.color（在 Chart.js 4 上會退回畫布預設黑色）的問題，同時方便控制
     * 字體大小與項目間距。
     * @param {HTMLElement} legendEl
     * @param {Array<{label:string, borderColor:string, borderDash?:number[]}>} datasets
     */
    function renderTrendLegend(legendEl, datasets) {
        if (!legendEl) return;
        legendEl.innerHTML = "";
        (datasets || []).forEach(function (ds) {
            var isDashed = !!(ds.borderDash && ds.borderDash.length);
            var item = document.createElement("span");
            item.className = "trend-chart-legend-item" + (isDashed ? " trend-chart-legend-item--dashed" : "");
            var swatch = document.createElement("i");
            swatch.className = "trend-chart-legend-swatch";
            swatch.style.borderColor = ds.borderColor;
            var text = document.createElement("span");
            text.textContent = ds.label;
            item.appendChild(swatch);
            item.appendChild(text);
            legendEl.appendChild(item);
        });
    }

    // 走勢圖 tooltip 色塊：預先畫好的線段小 canvas（實線／虛線），依 borderColor
    // ＋borderDash 快取。用它當 tooltip 的 pointStyle，而不是靠 Chart.js 預設的
    // boxHeight:0 + strokeRect——後者把「零高度矩形」的路徑來回描一次，虛線的
    // 空隙會被回程那趟填滿，賽季平均線在 tooltip 裡就會退化成實線。直接用 canvas
    // 畫一條線只描一次，實線/虛線都能忠實呈現。
    var trendSwatchCache = {};
    function trendSwatchCanvas(color, dash) {
        var key = color + "|" + (dash || []).join(",");
        if (trendSwatchCache[key]) return trendSwatchCache[key];
        var w = 22, h = 4;
        var cvs = document.createElement("canvas");
        cvs.width = w;
        cvs.height = h;
        var c = cvs.getContext("2d");
        c.strokeStyle = color;
        c.lineWidth = 2;
        if (dash && dash.length) c.setLineDash(dash);
        c.beginPath();
        c.moveTo(0, h / 2);
        c.lineTo(w, h / 2);
        c.stroke();
        trendSwatchCache[key] = cvs;
        return cvs;
    }

    /**
     * Chart.js tooltip 的 callbacks.labelPointStyle：把色塊畫成跟圖例一樣的線段
     * 樣式（實線／虛線）。搭配 tooltip 的 usePointStyle:true，Chart.js 會把回傳的
     * canvas 直接畫在色塊位置，虛線因此能忠實呈現（不受 strokeRect 退化矩形影響）。
     * @param {Object} item  Chart.js tooltip context 的 TooltipItem
     * @returns {{pointStyle:HTMLCanvasElement, rotation:number}}
     */
    function trendTooltipLabelPointStyle(item) {
        var ds = item.dataset;
        var isDashed = !!(ds.borderDash && ds.borderDash.length);
        return {
            pointStyle: trendSwatchCanvas(ds.borderColor, isDashed ? ds.borderDash : null),
            rotation: 0,
        };
    }

    return {
        escapeHtml: escapeHtml,
        populateLevelSelect: populateLevelSelect,
        levelItemsFromContainers: levelItemsFromContainers,
        trendStatConfig: TREND_STAT_CONFIG,
        buildTrendChartData: buildTrendChartData,
        hasTrendStat: hasTrendStat,
        formatTrendValue: formatTrendValue,
        renderTrendLegend: renderTrendLegend,
        trendTooltipLabelPointStyle: trendTooltipLabelPointStyle,
        pitchTypeInfo: pitchTypeInfo,
    };
})();

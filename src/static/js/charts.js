/**
 * charts.js — Chart.js 折線圖初始化
 * 載入於：tab_plot.j2（圖表 Tab）
 *
 * 讀 #player-trend-data（<script type="application/json">，由
 * site_builder/graph/season_trend.py 產生），
 *    依「數據／年度／層級」三個 <select>（#trend-stat-select 等）重繪，並疊一條
 *    賽季平均虛線。
 */
document.addEventListener("DOMContentLoaded", function () {
    var canvas = document.getElementById("performanceChart");
    if (!canvas || typeof Chart === "undefined") return;

    var trendByYear = window.TW.readJsonScript("player-trend-data");
    if (trendByYear) {
        initTrendChart(canvas, trendByYear);
    }
});

/**
 * 球員賽季走勢圖：數據／年度／層級三選單 + 賽季平均虛線。
 * @param {HTMLCanvasElement} canvas
 * @param {Object} trendByYear  season_trend.py builder 的輸出
 */
function initTrendChart(canvas, trendByYear) {
    var statSel = document.getElementById("trend-stat-select");
    var yearSel = document.getElementById("trend-year-select");
    var levelSel = document.getElementById("trend-level-select");
    var legendEl = document.getElementById("trend-chart-legend");
    var emptyEl = document.getElementById("trend-chart-empty");
    if (!statSel || !yearSel || !levelSel) return;

    var ctx = canvas.getContext("2d");
    var chart = null;
    var availableLevelKeys = [];

    function levelsForYear() {
        return trendByYear[yearSel.value] || {};
    }

    // "_all" 是後端算好的跨層級累計序列（見 season_trend.py::_build_all_levels_entry），
    // 這裡的 <select> 選項改用 TW.populateLevelSelect 自己生成的 "_all" 項目，
    // 所以要把後端字典裡同名的 "_all" 排除，避免下拉選單重複出現兩個 All Levels。
    function realLevelKeys(levels) {
        return Object.keys(levels).filter(function (k) { return k !== "_all"; });
    }

    function updateLevelOptions() {
        var levels = levelsForYear();
        var statKey = statSel.value;
        var allLevelKeys = realLevelKeys(levels);
        availableLevelKeys = allLevelKeys.filter(function (k) {
            return window.TW.hasTrendStat(levels[k].games, statKey);
        });
        var items = availableLevelKeys.map(function (k) {
            return { value: k, label: levels[k].level_label, selected: false };
        });
        window.TW.populateLevelSelect(levelSel, items, {
            allOption: availableLevelKeys.length > 1,
            allLabel: availableLevelKeys.length === allLevelKeys.length
                ? "All Levels"
                : items.map(function (item) { return item.label; }).join(" + "),
            allValue: "_all",
        });
        levelSel.disabled = availableLevelKeys.length === 0;
        if (levelSel.options.length) levelSel.selectedIndex = 0;
    }

    // "_all"：直接讀後端算好的跨層級累計序列（同一組分子/分母合併累計，不是
    // 把每個層級各自累計、歸零重來的線拼接起來），曲線在升降級時不會跳動。
    function currentGames() {
        var levels = levelsForYear();
        var games;
        if (levelSel.value === "_all") {
            var all = levels["_all"];
            games = all ? all.games.filter(function (game) {
                return availableLevelKeys.indexOf(game.level_label) !== -1;
            }) : [];
        } else {
            var lvl = levels[levelSel.value];
            games = lvl ? lvl.games : [];
        }
        return games.filter(function (game) {
            return game[statSel.value] != null;
        });
    }

    function formatValue(cfg, v) {
        return window.TW.formatTrendValue(cfg, v);
    }

    function render() {
        var statKey = statSel.value;
        var cfg = window.TW.trendStatConfig[statKey] || {};
        var games = currentGames();
        var built = window.TW.buildTrendChartData(games, statKey);
        var showLevelBadge = levelSel.value === "_all";

        if (chart) chart.destroy();
        chart = null;

        if (!availableLevelKeys.length || built.average == null) {
            canvas.hidden = true;
            legendEl.hidden = true;
            if (emptyEl) {
                emptyEl.textContent = yearSel.value + " 年度所有層級皆無 " + (cfg.label || statKey) + " 數據";
                emptyEl.hidden = false;
            }
            window.TW.renderTrendLegend(legendEl, []);
            return;
        }

        canvas.hidden = false;
        legendEl.hidden = false;
        if (emptyEl) emptyEl.hidden = true;

        var grad = ctx.createLinearGradient(0, 0, 0, 300);
        grad.addColorStop(0, "rgba(20,184,166,0.35)");
        grad.addColorStop(1, "rgba(20,184,166,0.0)");

        var datasets = [{
            label: cfg.label || statKey,
            data: built.values,
            borderColor: "#14b8a6",
            backgroundColor: grad,
            borderWidth: 2.5,
            pointBackgroundColor: "#14b8a6",
            pointBorderColor: "#09090b",
            pointBorderWidth: 2,
            pointRadius: 4,
            pointHoverRadius: 6,
            fill: true,
            tension: 0.35,
        }];

        // 賽季平均虛線：跟主線同一組資料算出來的常數線，全為 null 時不畫。
        // pointRadius:0 讓虛線本身不畫出圓點，但 pointHitRadius 保留一段可以
        // hover 到的判定範圍，這樣才能單獨 hover 到虛線觸發它自己的 tooltip。
        if (built.average != null) {
            datasets.push({
                label: "賽季平均",
                data: built.labels.map(function () { return built.average; }),
                borderColor: "#f59e0b",
                borderWidth: 1.5,
                borderDash: [6, 4],
                pointRadius: 0,
                pointHitRadius: 8,
                fill: false,
                tension: 0,
            });
        }

        chart = new Chart(ctx, {
            type: "line",
            data: { labels: built.labels, datasets: datasets },
            options: {
                responsive: true,
                // mode:"nearest" + intersect:true：只有滑鼠實際落在某條線的資料點
                // 判定範圍內才顯示 tooltip，且只顯示「該條線」自己的數值——實線與
                // 虛線（賽季平均）彼此獨立，不會互相顯示對方的數據。
                interaction: { mode: "nearest", intersect: true },
                plugins: {
                    // 圖例改用 TW.renderTrendLegend 畫成 HTML（見下方 legendEl 更新），
                    // 不用 Chart.js 內建 canvas 圖例：自訂 generateLabels 搭配
                    // pointStyle:'line' 在 Chart.js 4 上文字顏色會退回畫布預設黑色，
                    // 且不易控制字體大小與項目間距。
                    legend: { display: false },
                    // usePointStyle:true 讓色塊改用 labelPointStyle 回傳的線段
                    // canvas（實線/主線、虛線/賽季平均），忠實呈現虛線；boxWidth
                    // 對齊 canvas 寬度，boxHeight:0 不額外佔垂直空間（色塊仍會垂直置中）。
                    tooltip: {
                        usePointStyle: true,
                        boxWidth: 22,
                        boxHeight: 0,
                        callbacks: {
                            label: function (item) {
                                var line = item.dataset.label + ": " + formatValue(cfg, item.parsed.y);
                                // 只在主線（datasetIndex 0）標層級徽章，賽季平均虛線
                                // 本身沒有對應到單一場比賽，不需要（也不該）顯示層級
                                if (showLevelBadge && item.datasetIndex === 0) {
                                    var g = games[item.dataIndex];
                                    if (g && g.level_label) line += "  [" + g.level_label + "]";
                                }
                                return line;
                            },
                            labelPointStyle: window.TW.trendTooltipLabelPointStyle,
                        },
                    },
                },
                scales: {
                    x: { grid: { color: window.TW.primaryAlpha(0.05) }, ticks: { color: "#94a3b8" } },
                    y: {
                        grid: { color: window.TW.primaryAlpha(0.05) },
                        ticks: {
                            color: "#94a3b8",
                            callback: function (value) { return formatValue(cfg, Number(value)); },
                        },
                    },
                },
            },
        });

        window.TW.renderTrendLegend(legendEl, datasets);
    }

    yearSel.addEventListener("change", function () {
        updateLevelOptions();
        render();
    });
    levelSel.addEventListener("change", render);
    statSel.addEventListener("change", function () {
        updateLevelOptions();
        render();
    });

    updateLevelOptions();
    render();
}

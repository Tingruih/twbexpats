/**
 * filters.js — 球員詳細頁「年份 / 聯盟 / 對戰打者」篩選的共用引擎
 * 載入於：player_detail.j2（於 gamelogs.js / arsenal-filters.js /
 *          m-gamelogs.js / m-advanced.js 之前，defer 保證順序）
 * 依賴：util.js（window.TW）
 *
 * 過去桌機版與手機版各自複製一份幾乎相同的篩選邏輯（gamelogs.js↔m-gamelogs.js、
 * arsenal-filters.js↔m-advanced.js）。此檔把核心邏輯集中為兩個工廠函式，
 * 桌機/手機只需傳入各自的「設定」即可，改一次行為兩邊同步。
 *
 * 重要：桌機與手機的 DOM 同時存在於同一頁（.page-desktop / .page-mobile
 * 以 CSS 切換），且部分 class（如 .arsenal-table-container）兩邊共用，
 * 因此各平台的「隱藏所有年份容器」與「空 level 是否顯示」等差異，
 * 一律透過 config 逐平台保留，本引擎不擅自統一，確保行為與重構前一致。
 */
window.TWFilters = (function () {
    "use strict";

    var byId = function (id) { return document.getElementById(id); };

    /**
     * 純函式：給定資料項的 level 與目前選取的 level，決定是否顯示。
     * @param {string} itemLevel      資料項的 data-level
     * @param {string} selectedLevel  下拉選取值（"_all"/""/具體 level）
     * @param {boolean} showEmpty     為 true 時，itemLevel 為空一律顯示
     *                                 （桌機逐場表行為；手機卡片為 false）
     */
    function shouldShow(itemLevel, selectedLevel, showEmpty) {
        if (selectedLevel === "_all" || selectedLevel === "") return true;
        if (itemLevel === selectedLevel) return true;
        return !!showEmpty && itemLevel === "";
    }

    /**
     * 建立「年份 + 聯盟」篩選器（逐場紀錄：桌機表格列 / 手機卡片共用）。
     * @param {Object} cfg
     *   yearSelectId, levelSelectId : <select> 的 id
     *   yearContainerPrefix         : 年份容器 id 前綴（如 "gamelogs-"）
     *   hideYearContainers()        : 隱藏所有年份容器（逐平台，避免跨 DOM 誤傷）
     *   itemSelector                : 年份容器內資料項的選擇器
     *   activeDisplay               : 顯示年份容器時的 display 值（'block'/'flex'）
     *   showEmptyLevel              : 空 level 是否一律顯示
     *   allLevelsOption             : level 數 > 1 時是否提供 "All Levels"
     *   onHideItem(item)            : 某項被隱藏時的額外處理（如收合逐球面板）
     *   onAfterFilter()、onAfterShowYear() : 篩選 / 切年份後的 hook（如預載）
     */
    function createLevelFilter(cfg) {
        var yearSel = byId(cfg.yearSelectId);
        var levelSel = byId(cfg.levelSelectId);

        function activeContainer() {
            return yearSel ? byId(cfg.yearContainerPrefix + yearSel.value) : null;
        }

        function activeItems() {
            var c = activeContainer();
            return c ? c.querySelectorAll(cfg.itemSelector) : [];
        }

        function updateLevelOptions() {
            if (!levelSel) return;
            var levels = [];
            Array.prototype.forEach.call(activeItems(), function (item) {
                var lv = item.dataset.level;
                if (lv && levels.indexOf(lv) === -1) levels.push(lv);
            });
            window.TW.populateLevelSelect(
                levelSel,
                levels.map(function (lv) { return { value: lv, label: lv }; }),
                { allOption: cfg.allLevelsOption && levels.length > 1 }
            );
        }

        function filter() {
            if (!levelSel) return;
            var lv = levelSel.value;
            Array.prototype.forEach.call(activeItems(), function (item) {
                var show = shouldShow(item.dataset.level, lv, cfg.showEmptyLevel);
                item.style.display = show ? "" : "none";
                if (!show && cfg.onHideItem) cfg.onHideItem(item);
            });
            if (cfg.onAfterFilter) cfg.onAfterFilter();
        }

        function showYear() {
            if (!yearSel) return;
            cfg.hideYearContainers();
            var c = activeContainer();
            if (c) c.style.display = cfg.activeDisplay;
            updateLevelOptions();
            filter();
            if (cfg.onAfterShowYear) cfg.onAfterShowYear();
        }

        if (yearSel) yearSel.addEventListener("change", showYear);
        if (levelSel) levelSel.addEventListener("change", filter);
        if (yearSel) showYear();

        return { showYear: showYear, filter: filter };
    }

    /**
     * 建立「年份 + 聯盟 + 對戰打者」篩選器（球種使用率表：桌機 / 手機共用）。
     * @param {Object} cfg
     *   yearSelectId, levelSelectId, batSideSelectId : <select> 的 id
     *   yearContainerPrefix : 年份容器 id 前綴（如 "arsenal-"）
     *   hideYearContainers() : 隱藏所有年份容器（逐平台）
     */
    function createArsenalFilter(cfg) {
        var yrSel = byId(cfg.yearSelectId);
        var lvSel = byId(cfg.levelSelectId);
        var batSel = byId(cfg.batSideSelectId);

        function yearContainer() {
            return yrSel ? byId(cfg.yearContainerPrefix + yrSel.value) : null;
        }

        function updateLevelOptions() {
            var yc = yearContainer();
            if (!yc || !lvSel) return;
            window.TW.populateLevelSelect(
                lvSel,
                window.TW.levelItemsFromContainers(yc.querySelectorAll(".arsenal-level-container"))
            );
        }

        function showBatSide(scope) {
            if (!batSel) return;
            var side = batSel.value || "all";
            var root = scope || document;
            root.querySelectorAll(".arsenal-split-container").forEach(function (c) {
                c.style.display = c.dataset.batSide === side ? "block" : "none";
            });
        }

        function showLevel() {
            var yc = yearContainer();
            if (!yc || !lvSel) return;
            var active = null;
            yc.querySelectorAll(".arsenal-level-container").forEach(function (c) {
                var on = c.dataset.level === lvSel.value;
                c.style.display = on ? "block" : "none";
                if (on) active = c;
            });
            showBatSide(active);
        }

        function showYear() {
            if (!yrSel) return;
            cfg.hideYearContainers();
            var yc = yearContainer();
            if (yc) yc.style.display = "block";
            updateLevelOptions();
            showLevel();
        }

        if (yrSel) yrSel.addEventListener("change", showYear);
        if (lvSel) lvSel.addEventListener("change", showLevel);
        if (batSel) batSel.addEventListener("change", function () { showLevel(); });
        if (yrSel) showYear();

        return { showYear: showYear, showLevel: showLevel };
    }

    return {
        shouldShow: shouldShow,
        createLevelFilter: createLevelFilter,
        createArsenalFilter: createArsenalFilter,
    };
})();

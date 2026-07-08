/**
 * util.js — 全站共用前端小工具（單一真相來源）
 * 載入於：base.j2（於所有其他腳本之前，defer 保證執行順序）
 *
 * 對外暴露 window.TW：
 *  - TW.escapeHtml(value)                    ：HTML 轉義，供動態 innerHTML 防注入
 *  - TW.populateLevelSelect(sel, items, opts)：填充聯盟層級 <select>
 *  - TW.levelItemsFromContainers(list)       ：把 .*-level-container NodeList
 *                                              轉成 populateLevelSelect 需要的陣列
 *
 * 過去 escapeHtml 在 pitcher-charts.js / pitch-plinko.js 各有一份、
 * level-select 填充邏輯散落 6 個檔案；集中於此後「改一處即全站生效」。
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

    return {
        escapeHtml: escapeHtml,
        populateLevelSelect: populateLevelSelect,
        levelItemsFromContainers: levelItemsFromContainers,
    };
})();

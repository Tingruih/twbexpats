/**
 * role-toggle.js — 球員詳細頁投手／打者切換
 * 載入於：player_detail.j2，只在投打兩個角色都有出賽的球員頁（page_roles 非空）；
 *         刻意不用 defer，放在所有 defer 腳本之前（見下方「網址帶 ?role=」）
 *
 * 內容怎麼換：
 *  - 主要角色的內容照常渲染在頁面上；次要角色的內容在
 *    <template data-role-view="{role}" data-role-target="{容器 id}">
 *    裡（partials/role_alt_views.j2）。template 內容不在 document 裡，所以
 *    兩個角色可以用同一組 id，各分頁的 JS 仍然用 getElementById 找得到「目前這個
 *    角色」的元素，不需要為角色加 id 前綴。
 *  - 切換時把每個容器目前的子節點搬進該角色的 DocumentFragment 暫存，再放入目標
 *    角色的子節點（第一次從 template 複製，之後從暫存搬回）。搬移而非重建，
 *    展開中的逐球紀錄、篩選選單的選擇、已畫好的圖表都保留原狀。
 *  - 容器本身（#panel-*、#m-panel-* 等）不動：tabs.js 快取了 #panel-* 元素、
 *    分頁的 active class 也掛在容器上，切換角色不會跳回別的分頁。
 *
 * 通知其他模組：
 *  - 切換完成後發送 player-role-change 事件，detail = { role, fresh }。
 *    fresh 為 true 表示這批元素第一次放進 document、還沒被任何模組初始化，
 *    各模組（gamelogs.js、charts.js、m-charts.js 等）據此對 document 重跑一次
 *    自己的初始化；此時另一個角色的元素已經搬離 document，不會被重複綁定。
 *
 * 網址帶 ?role=：
 *  - 本檔在頁面內容解析完、DOMContentLoaded 之前執行，直接把內容換成該角色，
 *    其他模組的 DOMContentLoaded 初始化就會作用在該角色上，不需要 fresh 事件；
 *    被換下來的主要角色則標記為尚未初始化，之後切回時才以 fresh 事件初始化。
 *  - 切換時以 history.replaceState 同步 ?role=（主要角色時移除參數），保留
 *    m-tabs.js 寫入的 ?tab=。
 */
(function () {
    "use strict";

    var toggles = document.querySelectorAll("[data-role-toggle]");
    if (!toggles.length) return;

    var primary = toggles[0].dataset.role;
    var current = primary;
    var templates = document.querySelectorAll("template[data-role-view]");
    // 各角色被搬離 document 的內容：{ role: { targetId: DocumentFragment } }
    var stash = {};
    // 已被各模組初始化過的角色
    var initialized = {};
    initialized[primary] = true;

    var roles = [primary];
    var targetIds = [];
    Array.prototype.forEach.call(templates, function (tpl) {
        if (roles.indexOf(tpl.dataset.roleView) === -1) roles.push(tpl.dataset.roleView);
        if (targetIds.indexOf(tpl.dataset.roleTarget) === -1) targetIds.push(tpl.dataset.roleTarget);
    });

    function findTemplate(role, targetId) {
        for (var i = 0; i < templates.length; i++) {
            var tpl = templates[i];
            if (tpl.dataset.roleView === role && tpl.dataset.roleTarget === targetId) return tpl;
        }
        return null;
    }

    function takeChildren(el) {
        var frag = document.createDocumentFragment();
        while (el.firstChild) frag.appendChild(el.firstChild);
        return frag;
    }

    // 目標角色某個容器的內容：先找暫存，沒有就從 template 複製（template 的根元素
    // 只是外殼，放進容器的是它的子節點）
    function contentFor(role, targetId) {
        if (stash[role] && stash[role][targetId]) {
            var saved = stash[role][targetId];
            delete stash[role][targetId];
            return saved;
        }
        var tpl = findTemplate(role, targetId);
        if (!tpl) return null;
        var root = document.importNode(tpl.content, true).firstElementChild;
        return root ? takeChildren(root) : null;
    }

    function swapContent(role) {
        stash[current] = stash[current] || {};
        targetIds.forEach(function (targetId) {
            var el = document.getElementById(targetId);
            if (!el) return;
            var next = contentFor(role, targetId);
            // 目標角色在這個容器沒有內容（樣板沒輸出）時保留原內容，避免整塊變空
            if (!next) return;
            stash[current][targetId] = takeChildren(el);
            el.appendChild(next);
        });
    }

    function syncToggles(role) {
        Array.prototype.forEach.call(toggles, function (toggle) {
            toggle.dataset.role = role;
            toggle.querySelectorAll("[data-set-role]").forEach(function (btn) {
                btn.setAttribute("aria-pressed", btn.dataset.setRole === role ? "true" : "false");
            });
        });
    }

    function syncUrl(role) {
        if (!window.history || !window.URL) return;
        var url = new URL(window.location.href);
        if (role === primary) url.searchParams.delete("role");
        else url.searchParams.set("role", role);
        window.history.replaceState(null, "", url.toString());
    }

    // 搬回 document 的 Chart.js 圖表在搬離期間量不到尺寸，重新量一次
    function resizeCharts() {
        if (typeof window.Chart === "undefined" || !window.Chart.getChart) return;
        document.querySelectorAll("canvas").forEach(function (canvas) {
            var chart = window.Chart.getChart(canvas);
            if (chart && canvas.offsetParent !== null) chart.resize();
        });
    }

    function switchRole(role, options) {
        if (role === current || roles.indexOf(role) === -1) return;
        var notify = !options || options.notify !== false;
        swapContent(role);
        current = role;
        syncToggles(role);
        if (!notify) {
            // 頁面載入時就切換：DOMContentLoaded 的初始化會作用在這個角色上
            initialized = {};
            initialized[role] = true;
            return;
        }
        syncUrl(role);
        var fresh = !initialized[role];
        initialized[role] = true;
        document.dispatchEvent(new CustomEvent("player-role-change", {
            detail: { role: role, fresh: fresh }
        }));
        resizeCharts();
    }

    Array.prototype.forEach.call(toggles, function (toggle) {
        toggle.addEventListener("click", function (event) {
            var btn = event.target.closest("[data-set-role]");
            if (btn) switchRole(btn.dataset.setRole);
        });
    });

    var requested = new URLSearchParams(window.location.search).get("role");
    if (requested && requested !== primary) switchRole(requested, { notify: false });
})();

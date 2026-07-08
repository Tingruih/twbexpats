/**
 * m-gamelogs.js — 手機版逐場紀錄年份/聯盟篩選
 * 對應 m_gamelogs.j2；依賴 filters.js（window.TWFilters）
 *
 * 核心篩選共用自 filters.js::createLevelFilter；本檔僅保留手機專屬的
 * pitch log 預熱串接（切到逐場 Tab 時）。手機卡片不套用「空 level 一律顯示」。
 */
(function () {
    function warmupVisiblePitchLogs() {
        if (typeof window.prefetchMobilePitchLogs !== 'function') return;
        window.prefetchMobilePitchLogs();
    }

    function init() {
        window.TWFilters.createLevelFilter({
            yearSelectId: "m-gamelog-year-select",
            levelSelectId: "m-gamelog-level-select",
            yearContainerPrefix: "m-gamelogs-",
            hideYearContainers: function () {
                document.querySelectorAll(".m-gamelog-year").forEach(function (c) {
                    c.style.display = "none";
                });
            },
            itemSelector: ".m-gamelog-card",
            activeDisplay: "flex",
            showEmptyLevel: false,
            allLevelsOption: true,
            // 隱藏卡片時，一併收合其內的逐球面板
            onHideItem: function (card) {
                var panel = card.querySelector(".m-pitch-log-panel");
                if (panel) panel.style.display = "none";
            },
        });

        document.addEventListener('player-mobile-tab-change', function (event) {
            if (event.detail && event.detail.tab === 'gamelogs') warmupVisiblePitchLogs();
        });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();

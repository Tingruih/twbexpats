/**
 * arsenal-filters.js — 進階數據 Tab 球種使用率篩選（桌機版）
 * 載入於：player_detail.j2；依賴 filters.js（window.TWFilters）
 *
 * 三層篩選（年份 / 聯盟層級 / 對左右打）共用自 filters.js::createTieredLevelFilter。
 * 桌機以 .arsenal-table-container class 隱藏年份容器（與重構前一致）。
 */
document.addEventListener("DOMContentLoaded", function () {
    window.TWFilters.createTieredLevelFilter({
        yearSelectId: "arsenal-year-select",
        levelSelectId: "arsenal-level-select",
        batSideSelectId: "arsenal-bat-side-select",
        yearContainerPrefix: "arsenal-",
        hideYearContainers: function () {
            document.querySelectorAll(".arsenal-table-container").forEach(function (t) {
                t.style.display = "none";
            });
        },
    });
});

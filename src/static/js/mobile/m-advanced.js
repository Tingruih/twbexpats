/**
 * m-advanced.js — 手機版進階數據 Tab 球種篩選
 * 對應 m_advanced.j2 中的 m-arsenal-* 選單與容器；依賴 filters.js。
 *
 * 三層篩選共用自 filters.js::createArsenalFilter。手機以 id 前綴（m-arsenal-YYYY）
 * 隱藏年份容器 —— 因 .arsenal-table-container class 與桌機共用，用 class 會誤傷桌機。
 */
document.addEventListener("DOMContentLoaded", function () {
    window.TWFilters.createArsenalFilter({
        yearSelectId: "m-arsenal-year-select",
        levelSelectId: "m-arsenal-level-select",
        batSideSelectId: "m-arsenal-bat-side-select",
        yearContainerPrefix: "m-arsenal-",
        hideYearContainers: function () {
            document.querySelectorAll("[id^='m-arsenal-']").forEach(function (t) {
                if (/^m-arsenal-\d{4}$/.test(t.id)) t.style.display = "none";
            });
        },
    });
});

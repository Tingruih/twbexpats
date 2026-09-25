/**
 * arsenal-filters.js — 進階數據 Tab 球種使用率篩選（桌機版）
 * 載入於：player_detail.j2；依賴 filters.js（window.TWFilters）
 *
 * 三層篩選（年份 / 聯盟層級 / 對左右打）共用自 filters.js::createTieredLevelFilter。
 * 桌機以 .arsenal-table-container class 隱藏年份容器（與重構前一致）。
 */
(function () {
    function init() {
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
    }

    document.addEventListener("DOMContentLoaded", init);
    // 雙角色球員頁切到另一個角色時，對新放進來的選單重新綁定（見 role-toggle.js）
    window.TW.onRoleViewInit(init);
})();

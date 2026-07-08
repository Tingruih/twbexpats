/**
 * gamelogs.js — 逐場紀錄 Tab 年份/聯盟篩選（桌機版）
 * 載入於：player_detail.j2（逐場紀錄 Tab）
 * 依賴：filters.js（window.TWFilters）、pitch-log.js（預載 API）
 *
 * 核心的「年份 + 聯盟」篩選邏輯共用自 filters.js::createLevelFilter；
 * 本檔僅保留桌機專屬的 Pitch Log 預載入串接（滑鼠按下 / 切 Tab 時預熱）。
 */
document.addEventListener("DOMContentLoaded", function () {
    var prefetchScheduled = false;

    // 判斷目前是否正在看逐場紀錄 Tab（pitch log 預載前先確認）
    function isGamelogsPanelActive() {
        var panel = document.getElementById("panel-gamelogs");
        return !!panel && panel.classList.contains("tab-panel--active");
    }

    // 在瀏覽器閒置時觸發所有可見比賽列的 pitch log 預載（減少點開時的等待）
    function schedulePitchLogWarmup() {
        if (!isGamelogsPanelActive() || prefetchScheduled || typeof prefetchFilteredPitchLogs !== 'function') return;
        prefetchScheduled = true;
        var run = function () {
            prefetchScheduled = false;
            if (isGamelogsPanelActive()) prefetchFilteredPitchLogs();
        };
        if ('requestIdleCallback' in window) {
            window.requestIdleCallback(run, { timeout: 900 });
        } else {
            window.setTimeout(run, 150);
        }
    }

    // 使用者按下比賽列時，立即預載對應的 pitch log（降低展開延遲）
    function prefetchRowFromGameRow(gameRow) {
        if (!gameRow || typeof prefetchPitchLogRow !== 'function') return;
        var detailRow = gameRow.nextElementSibling;
        if (detailRow && detailRow.classList.contains("pitch-log-row")) {
            prefetchPitchLogRow(detailRow);
        }
    }

    // 年份 + 聯盟篩選（共用引擎）；桌機空 level 的列一律顯示（showEmptyLevel）
    window.TWFilters.createLevelFilter({
        yearSelectId: "gamelog-year-select",
        levelSelectId: "gamelog-level-select",
        yearContainerPrefix: "gamelogs-",
        hideYearContainers: function () {
            document.querySelectorAll(".gamelog-table-container").forEach(function (t) {
                t.style.display = "none";
            });
        },
        itemSelector: "tbody tr.gamelog-data-row",
        activeDisplay: "block",
        showEmptyLevel: true,
        allLevelsOption: true,
        // 隱藏某列時，一併收合其下方對應的逐球（pitch-log）展開列
        onHideItem: function (row) {
            var next = row.nextElementSibling;
            if (next && next.classList.contains("pitch-log-row")) next.style.display = "none";
        },
        onAfterFilter: schedulePitchLogWarmup,
        onAfterShowYear: schedulePitchLogWarmup,
    });

    // 滑鼠按下比賽列時觸發 pitch log 預載
    document.querySelectorAll(".game-row-expandable").forEach(function (row) {
        row.addEventListener("pointerdown", function () {
            prefetchRowFromGameRow(row);
        });
    });

    // 切換到逐場紀錄 Tab 時也觸發預載
    document.addEventListener("player-tab-change", function (event) {
        if (event.detail && event.detail.tab === "gamelogs") {
            schedulePitchLogWarmup();
        }
    });
});

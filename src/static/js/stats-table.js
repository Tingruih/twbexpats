/**
 * stats-table.js — 賽季數據年份組展開/收合
 * 載入於：tab_stats.j2（賽季數據 Tab）
 *
 * 作用：當球員同一年效力多支球隊時，數據表格會有「年份匯總列」
 * 可以點擊展開/收合該年度各球隊的細節列。
 *
 * toggleYearGroup(tableId, yr)
 *   tableId : 對應 stats-table-{tableId} 的表格 id
 *   yr      : 年份字串，控制 data-grp="{yr}" 的列
 *             開合判斷與箭頭旋轉共用 util.js::TW.toggleCollapseGroup
 *             （對稱：手機版見 mobile/m-tabs.js::toggleMobileYearGroup）
 */
function toggleYearGroup(tableId, yr) {
    // Find all detail rows for this table + year
    const table = document.getElementById('stats-table-' + tableId);
    if (!table) return;
    const rows = table.querySelectorAll('tr[data-tbl="' + tableId + '"][data-grp="' + yr + '"]');
    const arrow = document.getElementById('arrow-' + tableId + '-' + yr);
    window.TW.toggleCollapseGroup(rows, arrow);
}

(function() {
    function prefetchPanel(panel) {
        if (!panel || !panel.dataset.src) return Promise.resolve(null);
        return _loadPitchLogData(panel.dataset.src).catch(function() { return null; });
    }

    // 開合判斷與箭頭旋轉共用 util.js::TW.toggleCollapseGroup
    // （對稱：桌機版見 pitch-log.js::togglePitchLog）
    function toggleMobilePitchLog(id) {
        var panel = document.getElementById(id);
        if (!panel) return;
        var arrow = document.getElementById('m-arrow-' + id.replace(/^m-/, ''));
        var nowOpen = window.TW.toggleCollapseGroup(panel, arrow, 'block');

        if (!nowOpen) return;
        var container = document.getElementById(id.replace('m-pitchlog-', 'm-pitchlog-content-'));
        if (!container || container.dataset.rendered || container.dataset.loading) return;

        container.dataset.loading = '1';
        container.innerHTML = '<div class="pitch-log-loading">載入逐球資料中...</div>';
        _loadPitchLogData(panel.dataset.src)
            .then(function(entry) { _renderPitchLog(container, entry); })
            .catch(function() { container.innerHTML = '<div class="pitch-log-loading">逐球資料載入失敗</div>'; })
            .finally(function() { delete container.dataset.loading; });
    }

    // 目前顯示中的年份容器由 #m-gamelog-year-select 的值直接決定（單一真相
    // 來源，見 m-gamelogs.js 的 yearContainerPrefix），可見卡片則直接讀
    // card.style.display 屬性值判斷——兩者皆不比對 inline style 字串，
    // 避免寫法（如 "display: flex;" vs "display:none"）一旦跑掉就悄悄失準。
    function prefetchMobilePitchLogs() {
        var yearSel = document.getElementById('m-gamelog-year-select');
        var activeYear = yearSel ? document.getElementById('m-gamelogs-' + yearSel.value) : null;
        if (!activeYear) return Promise.resolve([]);
        var panels = Array.prototype.slice.call(activeYear.querySelectorAll('.m-gamelog-card'))
            .filter(function (card) { return card.style.display !== 'none'; })
            .map(function (card) { return card.querySelector('.m-pitch-log-panel'); })
            .filter(Boolean);
        return Promise.all(panels.slice(0, 8).map(prefetchPanel));
    }

    window.toggleMobilePitchLog = toggleMobilePitchLog;
    window.prefetchMobilePitchLogs = prefetchMobilePitchLogs;
})();

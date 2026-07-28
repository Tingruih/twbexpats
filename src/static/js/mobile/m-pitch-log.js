(function() {
    function prefetchPanel(panel) {
        if (!panel || !panel.dataset.src) return Promise.resolve(null);
        return _loadPitchLogData(panel.dataset.src).catch(function() { return null; });
    }

    function toggleMobilePitchLog(id) {
        var panel = document.getElementById(id);
        if (!panel) return;
        var open = panel.style.display !== 'none';
        panel.style.display = open ? 'none' : 'block';

        var arrow = document.getElementById('m-arrow-' + id.replace(/^m-/, ''));
        if (arrow) arrow.style.transform = open ? '' : 'rotate(90deg)';

        if (open) return;
        var container = document.getElementById(id.replace('m-pitchlog-', 'm-pitchlog-content-'));
        if (!container || container.dataset.rendered || container.dataset.loading) return;

        container.dataset.loading = '1';
        container.innerHTML = '<div class="pitch-log-loading">載入逐球資料中...</div>';
        _loadPitchLogData(panel.dataset.src)
            .then(function(entry) { _renderPitchLog(container, entry); })
            .catch(function() { container.innerHTML = '<div class="pitch-log-loading">逐球資料載入失敗</div>'; })
            .finally(function() { delete container.dataset.loading; });
    }

    function prefetchMobilePitchLogs() {
        var activeYear = document.querySelector('.m-gamelog-year[style="display: flex;"], .m-gamelog-year:not([style*="display:none"]):not([style*="display: none"])');
        var panels = activeYear ? Array.prototype.slice.call(activeYear.querySelectorAll('.m-gamelog-card:not([style*="display: none"]) .m-pitch-log-panel')) : [];
        return Promise.all(panels.slice(0, 8).map(prefetchPanel));
    }

    window.toggleMobilePitchLog = toggleMobilePitchLog;
    window.prefetchMobilePitchLogs = prefetchMobilePitchLogs;
})();
